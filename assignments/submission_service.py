"""Immutable submission snapshots; callers serialize writes with the course lock."""
import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max, Q
from .models import GroupMember, SubmitAssignment, SubmissionAttachment

MATERIAL_LABELS = dict(SubmissionAttachment.CATEGORY)


def visible_to(user):
    return Q(author=user) | Q(group__memberships__user=user)


def group_for(user, assignment):
    if assignment.submission_mode != 'group':
        return None
    membership = GroupMember.objects.select_related('group').filter(course_id=assignment.course_id, user=user).first()
    if not membership:
        raise PermissionDenied('请先由课程教师将你加入实验小组。')
    return membership.group


def submission_series(submission):
    if not submission.assignment_ques_id:
        return SubmitAssignment.objects.filter(pk=submission.pk)
    queryset = SubmitAssignment.objects.filter(assignment_ques_id=submission.assignment_ques_id)
    queryset = queryset.filter(group_id=submission.group_id) if submission.group_id else queryset.filter(author_id=submission.author_id, group__isnull=True)
    return queryset.order_by('-version_number', '-pk')


def current_for(user, assignment, group=None):
    queryset = SubmitAssignment.objects.filter(assignment_ques=assignment, current_slot=1)
    return queryset.filter(group=group).first() if group else queryset.filter(author=user, group__isnull=True).first()


def attachment_list(submission):
    items = list(submission.attachments.all())
    if items or not submission.assignment_file:
        return items
    try:
        size = submission.assignment_file.size
    except (OSError, ValueError):
        size = 0
    return [SimpleNamespace(pk=0, file=submission.assignment_file, name=Path(submission.assignment_file.name).name,
                            category=infer_category(submission.assignment_file.name), size=size, checksum='')]


def infer_category(name):
    from .code_review import CODE_EXTENSIONS, TEXT_NAMES
    suffix = Path(name).suffix.lower()
    if suffix == '.zip' or suffix in CODE_EXTENSIONS or Path(name).name in TEXT_NAMES:
        return 'code'
    if suffix in ('.png', '.jpg', '.jpeg'):
        return 'screenshots'
    return 'report'


def materials_for(submission):
    present = {item.category for item in attachment_list(submission)}
    required = submission.assignment_ques.required_materials if submission.assignment_ques_id else []
    return [{'key': key, 'label': label, 'present': key in present, 'required': key in required}
            for key, label in SubmissionAttachment.CATEGORY]


def save_version(user, assignment, group, previous, cleaned):
    all_previous = SubmitAssignment.objects.filter(assignment_ques=assignment)
    all_previous = all_previous.filter(group=group) if group else all_previous.filter(author=user, group__isnull=True)
    version = (all_previous.aggregate(number=Max('version_number'))['number'] or 0) + 1
    participants = list(group.memberships.select_related('user').order_by('user__username')) if group else []
    if group and assignment.course.students.filter(pk__in=[m.user_id for m in participants]).count() != len(participants):
        raise PermissionDenied('小组有成员已退出课程，请确认其重新加入课程后再提交。')
    users = [membership.user for membership in participants] if group else [user]
    snapshot = [{'id': member.pk, 'username': member.username, 'name': str(member)} for member in users]
    retained = attachment_list(previous) if previous and cleaned.get('keep_existing') else []
    files = {item.name: {'name': item.name, 'category': item.category, 'size': item.size,
                        'checksum': item.checksum, 'stored': item.file.name} for item in retained}
    for upload, category in cleaned['uploads']:
        files[Path(upload.name).name] = {'name': Path(upload.name).name, 'category': category, 'size': upload.size, 'upload': upload}
    categories = {item['category'] for item in files.values()}
    missing = [MATERIAL_LABELS[key] for key in assignment.required_materials if key not in categories]
    if missing:
        raise ValidationError('缺少必交材料：' + '、'.join(missing))
    if not files:
        raise ValidationError('请至少上传一个附件，或保留上一版附件。')
    if len(files) > 20 or sum(item['size'] for item in files.values()) > 50 * 1024 * 1024:
        raise ValidationError('每次提交最多 20 个附件，附件合计不超过 50 MB。')
    created = []
    storage = SubmissionAttachment._meta.get_field('file').storage
    try:
        for item in files.values():
            if 'upload' in item:
                upload = item['upload']
                upload.seek(0)
                digest = hashlib.sha256()
                for chunk in upload.chunks():
                    digest.update(chunk)
                upload.seek(0)
                item['checksum'] = digest.hexdigest()
                item['stored'] = storage.save('experiments/{}/{}'.format(uuid.uuid4().hex, item['name']), upload)
                created.append(item['stored'])
        if previous:
            previous.current_slot = None
            previous.save(update_fields=['current_slot'])
        submission = SubmitAssignment.objects.create(author=user, assignment_ques=assignment, group=group,
            topic=cleaned['topic'], description=cleaned['description'], assignment_file=next(iter(files.values()))['stored'],
            version_number=version, participant_snapshot=snapshot, rubric_snapshot=assignment.rubric)
        SubmissionAttachment.objects.bulk_create([SubmissionAttachment(submission=submission, file=item['stored'],
            name=item['name'], category=item['category'], size=item['size'], checksum=item['checksum']) for item in files.values()])
        from .code_review import manifest
        manifest(submission)
        return submission
    except Exception:
        for name in created:
            storage.delete(name)
        raise

"""Course-scoped experiment review, previews, exports, and group administration."""
import csv
import re
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from courses.models import Course
from django_lms.permissions import require_teacher, require_member, require_active_course, require_submission_reader, download_file
from .models import Assignment, SubmitAssignment, CourseGroup, GroupMember
from .experiment_forms import CourseGroupForm
from .submission_service import attachment_list, submission_series, materials_for
from .code_review import manifest, read_entry, is_text, text_content, highlighted_lines, changes_between, side_by_side, MAX_PREVIEW


def private(response):
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def readable(request, pk):
    submission = get_object_or_404(SubmitAssignment.objects.select_related('assignment_ques__course', 'author', 'group'), pk=pk)
    require_submission_reader(request.user, submission)
    return submission


def markdown_preview(text):
    """Small safe Markdown subset: no raw HTML, links, embeds, or scripts."""
    blocks, code = [], None
    for line in text.splitlines():
        if line.startswith('```'):
            if code is None:
                code = []
            else:
                blocks.append('<pre><code>{}</code></pre>'.format(escape('\n'.join(code))))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        safe = str(escape(line))
        safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
        safe = re.sub(r'`([^`]+)`', r'<code>\1</code>', safe)
        heading = re.match(r'^(#{1,6})\s+(.*)', safe)
        if heading:
            n = len(heading.group(1))
            blocks.append('<h{0}>{1}</h{0}>'.format(n, heading.group(2)))
        elif safe.startswith(('- ', '* ')):
            blocks.append('<p>• {}</p>'.format(safe[2:]))
        else:
            blocks.append('<p>{}</p>'.format(safe or '&nbsp;'))
    if code is not None:
        blocks.append('<pre><code>{}</code></pre>'.format(escape('\n'.join(code))))
    return mark_safe('\n'.join(blocks))


@login_required
def browse(request, pk):
    submission = readable(request, pk)
    context = {'submission': submission, 'versions': submission_series(submission), 'files': [], 'selected_path': request.GET.get('path', '')}
    try:
        entries = manifest(submission)
        context['files'] = [{'path': path, 'size': entry['size'], 'query': urlencode({'path': path}),
                             'depth': path.count('/')} for path, entry in entries.items()]
        path = context['selected_path']
        if not path:
            path = next((name for name in entries if Path(name).name.lower() == 'readme.md'), next(iter(entries), ''))
            context['selected_path'] = path
        if path not in entries:
            raise Http404('当前版本中不存在该文件。')
        entry = entries[path]
        suffix = Path(path).suffix.lower()
        context['selected_query'] = urlencode({'path': path, 'raw': '1'})
        if suffix in {'.pdf', '.png', '.jpg', '.jpeg'}:
            context['preview_kind'] = 'pdf' if suffix == '.pdf' else 'image'
        elif is_text(path):
            text = text_content(read_entry(entry))
            if text is None:
                context['notice'] = '该文件不是可识别的文本，请下载查看。'
            else:
                context['lines'] = highlighted_lines(path, text)
                if suffix == '.md':
                    context['markdown'] = markdown_preview(text)
        else:
            context['notice'] = '此格式暂不支持在线预览，请在提交详情下载附件。'
        if request.GET.get('raw') == '1':
            # Only fixed non-executable formats are allowed inline, regardless of archive names.
            mime = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(suffix)
            if not mime:
                raise Http404
            data = read_entry(entry, 20 * 1024 * 1024)
            if not ((suffix == '.pdf' and data.startswith(b'%PDF-')) or
                    (suffix == '.png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or
                    (suffix in {'.jpg', '.jpeg'} and data.startswith(b'\xff\xd8\xff'))):
                raise Http404('附件内容与格式不匹配。')
            response = HttpResponse(data, content_type=mime)
            response['Content-Security-Policy'] = ("frame-ancestors 'self'; base-uri 'none'" if suffix == '.pdf'
                                                   else "sandbox; default-src 'none'")
            return private(response)
    except (ValidationError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        context['notice'] = '；'.join(exc.messages) if isinstance(exc, ValidationError) else '附件无法读取，请联系教师。'
    return private(render(request, 'assignments/browse.html', context))


@login_required
def compare(request, pk):
    submission = readable(request, pk)
    versions = submission_series(submission)
    context = {'submission': submission, 'versions': versions, 'changes': [], 'selected_path': request.GET.get('path', '')}
    current = request.GET.get('to') or str(submission.pk)
    try:
        newer = versions.get(pk=current)
        older_id = request.GET.get('from')
        older = versions.get(pk=older_id) if older_id else versions.filter(version_number__lt=newer.version_number).first()
    except (SubmitAssignment.DoesNotExist, ValueError, OverflowError):
        raise Http404('只能对比同一实验、同一学生或小组的提交。')
    context.update(older=older, newer=newer)
    if older is None:
        context['notice'] = '目前只有一个版本，追加提交后即可查看差异。'
    else:
        require_submission_reader(request.user, older)
        require_submission_reader(request.user, newer)
        try:
            left, right = manifest(older), manifest(newer)
            changes = changes_between(left, right)
            for item in changes:
                item['query'] = urlencode({'from': older.pk, 'to': newer.pk, 'path': item['path']})
            context['changes'] = changes
            context['changed_count'] = sum(item['status'] != 'unchanged' for item in changes)
            path = context['selected_path'] or next((row['path'] for row in changes if row['status'] != 'unchanged'), next(iter(right), next(iter(left), '')))
            context['selected_path'] = path
            if path not in left and path not in right:
                raise Http404
            if is_text(path):
                a = text_content(read_entry(left[path])) if path in left else ''
                b = text_content(read_entry(right[path])) if path in right else ''
                if a is not None and b is not None:
                    context['diff_rows'] = side_by_side(a, b)
                else:
                    context['notice'] = '二进制文件仅显示是否更换，请下载查看。'
            else:
                context['notice'] = '图片、PDF 和其他二进制文件仅显示新增、删除或更换状态。'
        except (ValidationError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            context['notice'] = '；'.join(exc.messages) if isinstance(exc, ValidationError) else '附件无法读取，请联系教师。'
    return private(render(request, 'assignments/compare.html', context))


@login_required
def attachment_download(request, pk, attachment_id):
    submission = readable(request, pk)
    item = next((item for item in attachment_list(submission) if item.pk == int(attachment_id)), None)
    if item is None:
        raise Http404
    return download_file(item.file)


@login_required
@require_http_methods(['GET', 'POST'])
def groups(request, course_id, group_id=None):
    with transaction.atomic():
        course = get_object_or_404(Course.objects.select_for_update(), pk=course_id)
        require_member(request.user, course)
        teacher = request.user.user_type == 2 and course.teacher_id == request.user.pk
        group = get_object_or_404(CourseGroup, course=course, pk=group_id) if group_id else None
        editable = teacher and not course.is_archived and not (group and group.submissions.exists())
        if group_id and not teacher:
            raise PermissionDenied
        form = CourseGroupForm(request.POST or None, instance=group, course=course) if editable else None
        if request.method == 'POST':
            require_teacher(request.user, course)
            require_active_course(course)
            if not editable:
                raise PermissionDenied('已有实验提交的小组名单已锁定，历史组员和成绩不会被更改。')
            if form.is_valid():
                obj = form.save(commit=False)
                obj.course = course
                obj.save()
                obj.memberships.all().delete()
                GroupMember.objects.bulk_create([GroupMember(group=obj, course=course, user=user) for user in form.cleaned_data['members']])
                messages.success(request, '实验小组已保存。')
                return redirect('assignments:groups', course_id=course.pk)
    all_groups = course.experiment_groups.prefetch_related('memberships__user')
    # Students see only their own group roster.
    if not teacher:
        all_groups = all_groups.filter(memberships__user=request.user)
    for item in all_groups:
        item.locked = item.submissions.exists()
    ungrouped = course.students.exclude(pk__in=GroupMember.objects.filter(course=course).values('user_id')) if teacher else []
    return render(request, 'assignments/groups.html', {'course': course, 'groups': all_groups, 'form': form,
        'is_teacher': teacher, 'editing_group': group, 'ungrouped': ungrouped})


def workbench_context(assignment, params):
    effective = list(assignment.question.filter(current_slot=1).select_related('author', 'group').prefetch_related('attachments'))
    by_owner = {(item.group_id if assignment.submission_mode == 'group' else item.author_id): item for item in effective}
    if assignment.submission_mode == 'group':
        owners = list(assignment.course.experiment_groups.prefetch_related('memberships__user'))
        rows = [{'label': owner.name, 'owner_id': owner.pk, 'members': [m.user for m in owner.memberships.all()], 'submission': by_owner.get(owner.pk)} for owner in owners]
        ungrouped = list(assignment.course.students.exclude(pk__in=GroupMember.objects.filter(course=assignment.course).values('user_id')))
    else:
        owners = list(assignment.course.students.order_by('username'))
        rows = [{'label': '{}（{}）'.format(owner, owner.username), 'owner_id': owner.pk, 'members': [owner], 'submission': by_owner.get(owner.pk)} for owner in owners]
        owner_ids = {owner.pk for owner in owners}
        rows.extend({'label': '{}（已退课）'.format(item.author), 'owner_id': item.author_id, 'members': [item.author], 'submission': item} for item in effective if item.author_id not in owner_ids)
        ungrouped = []
    for row in rows:
        item = row['submission']
        row['status'] = 'missing' if not item else ('graded' if item.graded else 'pending')
        row['materials'] = materials_for(item) if item else []
    counts = {key: sum(row['status'] == key for row in rows) for key in ('missing', 'pending', 'graded')}
    query = params.get('q', '').strip()[:100]
    status = params.get('status', 'all')
    selected_group = params.get('group', '')
    filtered = rows
    if query:
        filtered = [row for row in filtered if query.casefold() in (row['label'] + ' ' + ' '.join(u.username + ' ' + str(u) for u in row['members'])).casefold()]
    if status in counts:
        filtered = [row for row in filtered if row['status'] == status]
    if selected_group and assignment.submission_mode == 'group':
        filtered = [row for row in filtered if str(row['owner_id']) == selected_group]
    page = Paginator(filtered, 25).get_page(params.get('page'))
    return {'workbench_page': page, 'workbench_rows': filtered, 'missing_count': counts['missing'], 'pending_count': counts['pending'],
            'graded_count': counts['graded'], 'ungrouped': ungrouped, 'selected_status': status, 'query': query,
            'selected_group': selected_group, 'course_groups': assignment.course.experiment_groups.all(),
            'export_query': urlencode({'q': query, 'status': status, 'group': selected_group}),
            'page_query': urlencode({'q': query, 'status': status, 'group': selected_group})}


def csv_cell(value):
    if isinstance(value, (int, float)):
        return value
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


@login_required
def export(request, pk, kind):
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=pk)
    require_teacher(request.user, assignment.course)
    rows = workbench_context(assignment, request.GET)['workbench_rows']
    if kind == 'grades':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="experiment-{}-grades.csv"'.format(pk)
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['课程', '实验', '小组/提交单位', '用户名', '姓名', '状态', '版本', '总分/小组分', '个人调整', '个人成绩', '评语', '提交时间'])
        for row in rows:
            item = row['submission']
            members = item.participant_snapshot if item and item.participant_snapshot else [{'id': u.pk, 'username': u.username, 'name': str(u)} for u in row['members']]
            for member in members:
                adjustment = item.individual_adjustments.get(str(member['id']), 0) if item else 0
                values = [assignment.course.course_name, assignment.assignment_name, row['label'], member['username'], member['name'],
                    {'missing': '未提交', 'pending': '待评分', 'graded': '已评分'}[row['status']], item.version_number if item else '',
                    item.grade if item and item.graded else '', adjustment if item and item.graded else '',
                    max(0, min(100, item.grade + adjustment)) if item and item.graded else '', item.feedback if item else '',
                    item.submitted_date.isoformat() if item else '']
                writer.writerow([csv_cell(value) for value in values])
        return private(response)
    if kind != 'files':
        raise Http404
    entries, total = [], 0
    for row in rows:
        if row['submission']:
            for item in attachment_list(row['submission']):
                entries.append((row['submission'], item))
                total += item.size
    if len(entries) > 500 or total > 200 * 1024 * 1024:
        messages.error(request, '批量下载最多 500 个附件、合计 200 MB，请缩小筛选范围。')
        return redirect(assignment)
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for submission, item in entries:
                path = 'submission-{}-v{}/{}'.format(submission.pk, submission.version_number, item.name)
                with item.file.open('rb') as stream, archive.open(path, 'w') as target:
                    copied = 0
                    while True:
                        chunk = stream.read(65536)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > 20 * 1024 * 1024:
                            raise ValidationError('附件超过批量下载大小限制。')
                        target.write(chunk)
        output.seek(0)
        return private(FileResponse(output, as_attachment=True, filename='experiment-{}-submissions.zip'.format(pk)))
    except (OSError, ValidationError):
        output.close()
        messages.error(request, '部分附件缺失或超过限制，批量下载未完成，请在提交详情检查。')
        return redirect(assignment)

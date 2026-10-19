from pathlib import Path

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404


def require_role(user, role):
    if not user.is_authenticated or user.user_type != role:
        raise PermissionDenied('当前身份无权执行此操作。')


def require_teacher(user, course):
    require_role(user, 2)
    if course.teacher_id != user.pk:
        raise PermissionDenied('仅本课程教师可以执行此操作。')


def require_member(user, course):
    if not user.is_authenticated or not (
        (user.user_type == 2 and course.teacher_id == user.pk)
        or (user.user_type == 1 and course.students.filter(pk=user.pk).exists())
    ):
        raise PermissionDenied('请先加入本课程。')


def require_submission_reader(user, submission):
    if not user.is_authenticated:
        raise PermissionDenied
    if user.user_type == 1 and submission.author_id == user.pk:
        return
    if user.user_type == 1 and any(member.get('id') == user.pk for member in submission.participant_snapshot):
        return
    if submission.assignment_ques_id:
        require_teacher(user, submission.assignment_ques.course)
    else:
        raise PermissionDenied


class TeacherRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        require_role(request.user, 2)
        return super().dispatch(request, *args, **kwargs)


def download_file(field):
    try:
        stream = field.open('rb')
    except (FileNotFoundError, OSError, ValueError):
        raise Http404('附件不存在，请联系课程教师。')
    response = FileResponse(stream, as_attachment=True, filename=Path(field.name).name)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def require_active_course(course):
    if course.is_archived:
        raise PermissionDenied('课程已归档，请教师恢复课程后再操作。')

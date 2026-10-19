from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views import generic
from django.views.decorators.http import require_POST

from courses.models import Course, Enrollment
from courses.forms import CreateCourseForm
from django_lms.permissions import TeacherRequiredMixin, require_role, require_teacher, require_active_course


class CreateCourse(TeacherRequiredMixin, generic.CreateView):
    form_class = CreateCourseForm
    model = Course

    def form_valid(self, form):
        form.instance.teacher = self.request.user
        messages.success(self.request, '课程已创建。')
        return super().form_valid(form)


class UpdateCourse(TeacherRequiredMixin, generic.UpdateView):
    form_class = CreateCourseForm
    model = Course

    def get_queryset(self):
        return Course.objects.filter(teacher=self.request.user, is_archived=False)

    def form_valid(self, form):
        with transaction.atomic():
            course = get_object_or_404(Course.objects.select_for_update(), pk=form.instance.pk)
            require_teacher(self.request.user, course)
            require_active_course(course)
            messages.success(self.request, '课程信息已更新。')
            return super().form_valid(form)


class CourseDetail(generic.DetailView):
    model = Course

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        course = self.object
        context['is_teacher'] = user.is_authenticated and user.user_type == 2 and course.teacher_id == user.pk
        context['is_enrolled'] = user.is_authenticated and user.user_type == 1 and course.students.filter(pk=user.pk).exists()
        context['can_view_content'] = context['is_teacher'] or context['is_enrolled']
        if context['can_view_content']:
            context['assignments'] = course.assignment_set.order_by('-start_date')
            context['resources'] = course.resource_set.all()
        if context['is_teacher']:
            context['members'] = course.students.order_by('username')
        return context


class ListCourse(generic.ListView):
    model = Course

    def get_queryset(self):
        return Course.objects.select_related('teacher').prefetch_related('students').order_by('is_archived', 'course_name')


@login_required
@require_POST
def enroll_course(request, pk):
    require_role(request.user, 1)
    with transaction.atomic():
        course = get_object_or_404(Course.objects.select_for_update(), pk=pk)
        require_active_course(course)
        _, created = Enrollment.objects.get_or_create(student=request.user, course=course)
    messages.success(request, '已加入课程。' if created else '您已加入这门课程。')
    return redirect(course)


@login_required
@require_POST
def unenroll_course(request, pk):
    require_role(request.user, 1)
    with transaction.atomic():
        course = get_object_or_404(Course.objects.select_for_update(), pk=pk)
        Enrollment.objects.filter(student=request.user, course=course).delete()
    messages.success(request, '已退出课程。您的提交和成绩仍保留在个人页。')
    return redirect(course)


@login_required
@require_POST
def archive_course(request, pk):
    with transaction.atomic():
        course = get_object_or_404(Course.objects.select_for_update(), pk=pk)
        require_teacher(request.user, course)
        if request.POST.get('action') not in ('archive', 'restore'):
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('无效的课程操作。')
        course.is_archived = request.POST['action'] == 'archive'
        course.save(update_fields=['is_archived'])
    messages.success(request, '课程已归档，历史内容可以继续查看。' if course.is_archived else '课程已恢复。')
    return redirect(course)

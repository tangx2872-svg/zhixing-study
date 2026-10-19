from django_lms.permissions import require_active_course
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_http_methods

from assignments.experiment_forms import CreateAssignmentForm, SubmitAssignmentForm, GradeAssignmentForm
from assignments.models import Assignment, SubmitAssignment, SubmissionAttachment
from courses.models import Course
from django_lms.permissions import TeacherRequiredMixin, require_teacher, require_member, require_role, require_submission_reader, download_file
from .submission_service import group_for, current_for, save_version, submission_series, attachment_list, materials_for, visible_to


def locked_assignment(pk):
    course_id = get_object_or_404(Assignment, pk=pk).course_id
    course = get_object_or_404(Course.objects.select_for_update(), pk=course_id)
    assignment = get_object_or_404(Assignment.objects.select_for_update(), pk=pk)
    assignment.course = course
    return assignment


class ActiveCourseSaveMixin:
    def form_valid(self, form):
        with transaction.atomic():
            course = get_object_or_404(Course.objects.select_for_update(), pk=form.instance.course_id)
            require_teacher(self.request.user, course)
            require_active_course(course)
            if form.instance.pk:
                persisted = locked_assignment(form.instance.pk)
                if persisted.question.exists():
                    form.instance.submission_mode = persisted.submission_mode
                    form.instance.required_materials = persisted.required_materials
                    form.instance.rubric = persisted.rubric
            return super().form_valid(form)


class CreateAssignment(ActiveCourseSaveMixin, TeacherRequiredMixin, generic.CreateView):
    form_class = CreateAssignmentForm
    template_name = 'assignments/create_assignment_form.html'

    def get_initial(self):
        initial = super().get_initial()
        course_id = self.request.GET.get('course', '')
        if course_id.isdecimal():
            from courses.models import Course
            course = Course.objects.filter(pk=course_id, teacher=self.request.user, is_archived=False).first()
            if course:
                initial['course'] = course.pk
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class UpdateAssignment(ActiveCourseSaveMixin, TeacherRequiredMixin, generic.UpdateView):
    model = Assignment
    form_class = CreateAssignmentForm
    template_name = 'assignments/create_assignment_form.html'

    def get_queryset(self):
        return super().get_queryset().filter(course__teacher=self.request.user, course__is_archived=False)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class DeleteAssignment(TeacherRequiredMixin, generic.DeleteView):
    model = Assignment
    success_url = reverse_lazy('courses:list')

    def get_queryset(self):
        return super().get_queryset().filter(course__teacher=self.request.user, course__is_archived=False)

    def delete(self, request, *args, **kwargs):
        with transaction.atomic():
            obj = get_object_or_404(self.get_queryset(), pk=kwargs['pk'])
            obj = locked_assignment(obj.pk)
            require_active_course(obj.course)
            if obj.question.exists():
                messages.error(request, '已有学生提交的作业不能删除，请保留教学记录。')
                return redirect(obj)
            return super().delete(request, *args, **kwargs)


def require_editable_submission(user, assignment, submission=None):
    require_role(user, 1)
    require_member(user, assignment.course)
    if not assignment.is_open:
        raise PermissionDenied('作业尚未开始或已截止，不能修改提交。')
    if submission and submission.current_slot != 1:
        raise PermissionDenied('历史版本不能修改。')


@login_required
@require_http_methods(['GET', 'POST'])
def submit_assignment(request, pk):
    # Serialize all submissions/grading for this assignment, including the first submission.
    with transaction.atomic():
        assignment = locked_assignment(pk)
        require_editable_submission(request.user, assignment)
        group = group_for(request.user, assignment)
        submission = current_for(request.user, assignment, group)
        require_editable_submission(request.user, assignment, submission)
        form = SubmitAssignmentForm(request.POST or None, request.FILES or None, previous=submission)
        if request.method == 'POST' and form.is_valid():
            try:
                with transaction.atomic():
                    obj = save_version(request.user, assignment, group, submission, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, '已保存实验提交 v{}，历史附件与评分保留。'.format(obj.version_number))
                return redirect(obj)
    return render(request, 'assignments/submitassignment_form.html', {'form': form, 'assignment': assignment, 'submission': submission, 'group': group, 'required_materials': [(key, dict(SubmissionAttachment.CATEGORY)[key]) for key in assignment.required_materials]})


class SubmitAssignmentDetail(LoginRequiredMixin, generic.DetailView):
    model = SubmitAssignment
    context_object_name = 'submissions'
    template_name = 'assignments/submitassignment_detail.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        require_submission_reader(self.request.user, obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        context['can_view_assignment'] = bool(obj.assignment_ques_id and (obj.assignment_ques.course.teacher_id == self.request.user.pk or obj.assignment_ques.course.students.filter(pk=self.request.user.pk).exists()))
        context['can_edit'] = bool(obj.assignment_ques_id and obj.assignment_ques.is_open and obj.current_slot == 1 and self.request.user.user_type == 1 and obj.assignment_ques.course.students.filter(pk=self.request.user.pk).exists())
        context['versions'] = submission_series(obj)
        context['attachments'] = attachment_list(obj)
        context['materials'] = materials_for(obj)
        context['my_grade'] = next((row['final_grade'] for row in obj.participant_grades if row['id'] == self.request.user.pk), obj.grade)
        return context


class AssignmentDetail(LoginRequiredMixin, generic.DetailView):
    model = Assignment
    template_name = 'assignments/experiment_detail.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        require_member(self.request.user, obj.course)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submissions = self.object.question.select_related('author').order_by('-submitted_date', '-pk')
        if self.request.user.user_type == 1:
            submissions = submissions.filter(visible_to(self.request.user)).distinct()
        context['submitted'] = submissions
        current = submissions.filter(current_slot=1).first() if self.request.user.user_type == 1 else None
        context['current_submission'] = current
        context['can_submit'] = self.object.is_open
        context['materials_required'] = [dict(SubmissionAttachment.CATEGORY)[key] for key in self.object.required_materials]
        if self.request.user.user_type == 2:
            effective = list(self.object.question.filter(current_slot=1).select_related('author'))
            by_student = {item.author_id: item for item in effective}
            members = list(self.object.course.students.order_by('username'))
            member_ids = {student.pk for student in members}
            context['roster'] = [{'student': student, 'submission': by_student.get(student.pk)} for student in members]
            context['missing_count'] = sum(student.pk not in by_student for student in members)
            context['pending_count'] = sum(not item.graded for item in effective)
            context['graded_count'] = sum(item.graded for item in effective)
            context['former_submissions'] = [item for item in effective if item.author_id not in member_ids]
        if self.request.user.user_type == 2:
            from .experiments import workbench_context
            context.update(workbench_context(self.object, self.request.GET))
        return context


@login_required
@require_http_methods(['GET', 'POST'])
def delete_view(request, pk):
    with transaction.atomic():
        obj = get_object_or_404(SubmitAssignment, pk=pk)
        require_submission_reader(request.user, obj)
        assignment = locked_assignment(obj.assignment_ques_id)
        obj.refresh_from_db()
        require_editable_submission(request.user, assignment, obj)
        if request.method == 'POST':
            if obj.graded:
                raise PermissionDenied('已评分提交不能撤回，可在截止前追加新版本。')
            obj.current_slot = None
            obj.withdrawn = True
            obj.withdrawn_at = timezone.now()
            obj.save(update_fields=['current_slot', 'withdrawn', 'withdrawn_at'])
            messages.success(request, '已撤回有效提交，历史版本仍保留，可在截止前重新提交。')
            return redirect(assignment)
    return render(request, 'assignments/submission_confirm_delete.html', {'submission': obj})


@login_required
@require_http_methods(['GET', 'POST'])
def grade_assignment(request, pk):
    with transaction.atomic():
        submission = get_object_or_404(SubmitAssignment, pk=pk)
        assignment = locked_assignment(submission.assignment_ques_id)
        require_teacher(request.user, assignment.course)
        require_active_course(assignment.course)
        submission.refresh_from_db()
        if submission.current_slot != 1:
            raise PermissionDenied('历史版本不能评分，请批改有效提交。')
        form = GradeAssignmentForm(request.POST or None, instance=submission)
        if request.method == 'POST' and form.is_valid():
            # ModelForm validation mutates its instance; reload before recording the old grade.
            submission.refresh_from_db()
            submission.grade_assignment(form.cleaned_data['grade'], form.cleaned_data['feedback'], request.user,
                                        form.cleaned_data['breakdown'], form.cleaned_data['adjustments'])
            messages.success(request, '成绩已保存。')
            return redirect(submission)
    return render(request, 'assignments/grade_form.html', {'form': form, 'submissions': submission})


@login_required
def download_submission(request, pk):
    submission = get_object_or_404(SubmitAssignment, pk=pk)
    require_submission_reader(request.user, submission)
    return download_file(submission.assignment_file)

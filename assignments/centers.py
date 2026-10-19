"""Role-scoped, read-only entry points into the existing teaching workflow."""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch
from django.shortcuts import render
from django.utils import timezone

from assignments.models import Assignment, SubmitAssignment
from courses.models import Course
from .submission_service import visible_to
from .models import GroupMember


def owned_courses(user):
    if user.user_type == 2:
        return Course.objects.filter(teacher=user)
    return Course.objects.filter(students=user)


def course_filter(queryset, value, field='course_id'):
    if not value:
        return queryset
    if not value.isdecimal() or len(value) > 18:
        return queryset.none()
    return queryset.filter(**{field: int(value)})


@login_required
def assignment_center(request):
    courses = owned_courses(request.user)
    assignments = Assignment.objects.filter(course__in=courses).select_related('course', 'course__teacher')
    teacher = request.user.user_type == 2
    now = timezone.now()
    if teacher:
        assignments = assignments.annotate(
            pending_count=Count('question', filter=Q(question__current_slot=1, question__graded=False)),
            graded_count=Count('question', filter=Q(question__current_slot=1, question__graded=True)))
        options = [('all', '全部'), ('pending', '待批改'), ('open', '进行中'), ('closed', '已截止'), ('archived', '已归档')]
    else:
        current = SubmitAssignment.objects.filter(visible_to(request.user), current_slot=1).distinct()
        assignments = assignments.prefetch_related(Prefetch('question', queryset=current, to_attr='my_current'))
        options = [('all', '全部'), ('todo', '待提交'), ('pending', '待评分'), ('graded', '已评分'), ('missed', '已截止未交'), ('archived', '已归档')]
    selected_course = request.GET.get('course', '')
    selected_status = request.GET.get('status', 'all')
    if selected_status not in dict(options):
        selected_status = 'all'
    assignments = course_filter(assignments, selected_course)
    if teacher:
        if selected_status == 'pending':
            assignments = assignments.filter(pending_count__gt=0, course__is_archived=False)
        elif selected_status == 'open':
            assignments = assignments.filter(course__is_archived=False, start_date__lte=now, due_date__gt=now)
        elif selected_status == 'closed':
            assignments = assignments.filter(course__is_archived=False, due_date__lte=now)
    else:
        current = SubmitAssignment.objects.filter(visible_to(request.user), current_slot=1).distinct()
        if selected_status in ('pending', 'graded'):
            assignments = assignments.filter(pk__in=current.filter(graded=selected_status == 'graded').values('assignment_ques_id'))
        elif selected_status in ('todo', 'missed'):
            assignments = assignments.exclude(pk__in=current.exclude(assignment_ques=None).values('assignment_ques_id')).filter(course__is_archived=False)
            if selected_status == 'todo':
                assignments = assignments.filter(start_date__lte=now, due_date__gt=now)
            else:
                assignments = assignments.filter(due_date__lte=now)
    if selected_status == 'archived':
        assignments = assignments.filter(course__is_archived=True)
    page = Paginator(assignments.order_by('course__is_archived', 'due_date', 'pk'), 12).get_page(request.GET.get('page'))
    for assignment in page:
        assignment.my_submission = None if teacher else next(iter(assignment.my_current), None)
        if teacher:
            assignment.center_status = assignment.status_label
        elif assignment.my_submission:
            assignment.center_status = '已评分' if assignment.my_submission.graded else '待评分'
        elif assignment.course.is_archived:
            assignment.center_status = '已归档未交'
        elif now >= assignment.due_date:
            assignment.center_status = '已截止未交'
        elif now < assignment.start_date:
            assignment.center_status = '未开始'
        else:
            assignment.center_status = '待提交'
        assignment.can_submit_here = not teacher and assignment.is_open and (assignment.submission_mode != 'group' or GroupMember.objects.filter(course_id=assignment.course_id, user=request.user).exists())
    return render(request, 'assignments/center.html', {
        'page_obj': page, 'courses': courses, 'selected_course': selected_course,
        'selected_status': selected_status, 'status_options': options, 'is_teacher': teacher,
    })


@login_required
def feedback_center(request):
    teacher = request.user.user_type == 2
    submissions = SubmitAssignment.objects.select_related('author', 'assignment_ques__course')
    if teacher:
        submissions = submissions.filter(assignment_ques__course__teacher=request.user)
        courses = owned_courses(request.user)
    else:
        submissions = submissions.filter(visible_to(request.user)).distinct()
        # Include courses the student left; historical feedback remains accessible.
        courses = Course.objects.filter(pk__in=submissions.values('assignment_ques__course_id'))
    options = [('all', '全部'), ('pending', '待评分'), ('graded', '已评分'), ('history', '历史版本')]
    selected_status = request.GET.get('status', 'all')
    if selected_status not in dict(options):
        selected_status = 'all'
    selected_course = request.GET.get('course', '')
    submissions = course_filter(submissions, selected_course, 'assignment_ques__course_id')
    if selected_status == 'pending':
        submissions = submissions.filter(current_slot=1, graded=False)
    elif selected_status == 'graded':
        submissions = submissions.filter(current_slot=1, graded=True)
    elif selected_status == 'history':
        submissions = submissions.filter(current_slot__isnull=True)
    page = Paginator(submissions.order_by('-updated_at', '-pk'), 12).get_page(request.GET.get('page'))
    for submission in page:
        submission.display_grade = submission.grade if teacher else next((row['final_grade'] for row in submission.participant_grades if row['id'] == request.user.pk), submission.grade)
    return render(request, 'assignments/feedback_center.html', {
        'page_obj': page, 'courses': courses, 'is_teacher': teacher,
        'selected_course': selected_course, 'selected_status': selected_status, 'status_options': options,
    })

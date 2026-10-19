from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views import generic

from assignments.models import Assignment, SubmitAssignment
from courses.models import Course
from research.models import ResearchWorkspace
from resources.models import Resource


def index(request):
    """首页：保留原有 Hero，登录后补充与本人相关的近期内容。"""
    context = {}
    user = request.user

    if user.is_authenticated:
        if user.user_type == 2:
            courses = Course.objects.filter(teacher=user)
        else:
            courses = Course.objects.filter(students=user)
        courses = courses.select_related('teacher')

        context['recent_courses'] = courses.order_by('-pk')[:4]
        context['recent_assignments'] = (
            Assignment.objects.filter(course__in=courses, course__is_archived=False)
            .filter(due_date__gte=timezone.now())
            .select_related('course')
            .order_by('due_date')[:5]
        )
        context['recent_resources'] = (
            Resource.objects.filter(course__in=courses, workspace__isnull=True)
            .select_related('course')
            .order_by('-pk')[:5]
        )
        context['my_projects'] = (
            ResearchWorkspace.objects.filter(Q(owner=user) | Q(memberships__user=user))
            .distinct()
            .select_related('owner')
            .order_by('-updated_at')[:3]
        )
        if user.user_type == 2:
            context['pending_total'] = SubmitAssignment.objects.filter(
                assignment_ques__course__teacher=user, current_slot=1, graded=False
            ).count()
        else:
            context['pending_total'] = SubmitAssignment.objects.filter(
                author=user, current_slot=1, graded=True
            ).count()
    else:
        context['recent_courses'] = (
            Course.objects.filter(is_archived=False).select_related('teacher').order_by('-pk')[:4]
        )

    context['demo_projects'] = (
        ResearchWorkspace.objects.filter(demo_key__isnull=False)
        .exclude(demo_key='')
        .order_by('demo_key')[:2]
    )
    return render(request, 'index.html', context)


class UserProfile(LoginRequiredMixin, generic.ListView):
    model = Course
    template_name = 'user_profile.html'

    def get_queryset(self):
        if str(self.request.user.pk) != str(self.kwargs['pk']):
            raise PermissionDenied('只能查看自己的个人页。')
        if self.request.user.user_type == 2:
            return Course.objects.filter(teacher=self.request.user)
        return Course.objects.filter(students=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        courses = context['course_list']
        context['course_count'] = courses.count()
        context['assignment_count'] = Assignment.objects.filter(course__in=courses).count()
        if self.request.user.user_type == 1:
            from assignments.submission_service import visible_to
            context['my_submissions'] = SubmitAssignment.objects.filter(visible_to(self.request.user)).distinct().select_related('assignment_ques__course').order_by('-updated_at', '-pk')
            current = context['my_submissions'].filter(current_slot=1)
        else:
            current = SubmitAssignment.objects.filter(assignment_ques__course__teacher=self.request.user, current_slot=1)
        context['pending_count'] = current.filter(graded=False).count()
        context['graded_count'] = current.filter(graded=True).count()
        return context

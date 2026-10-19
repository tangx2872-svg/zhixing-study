from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views import generic
from courses.models import Course
from assignments.models import Assignment, SubmitAssignment


def index(request):
    return render(request, 'index.html')


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

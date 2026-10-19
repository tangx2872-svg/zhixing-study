from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.views import generic
from django.views.decorators.http import require_http_methods
from courses.models import Course
from django_lms.permissions import TeacherRequiredMixin, require_teacher, require_member, require_active_course, download_file
from resources.forms import CreateResourceForm
from resources.models import Resource


class CreateResource(TeacherRequiredMixin, generic.CreateView):
    form_class = CreateResourceForm
    template_name = 'resources/create_resource_form.html'

    def get_initial(self):
        initial = super().get_initial()
        course_id = self.request.GET.get('course', '')
        if course_id.isdecimal():
            course = Course.objects.filter(pk=course_id, teacher=self.request.user, is_archived=False).first()
            if course:
                initial['course'] = course.pk
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            course = get_object_or_404(Course.objects.select_for_update(), pk=form.instance.course_id)
            require_teacher(self.request.user, course)
            require_active_course(course)
            self.object = form.save()
        messages.success(self.request, '学习资料已上传。')
        return redirect(course)


@login_required
@require_http_methods(['GET', 'POST'])
def delete_view(request, pk):
    with transaction.atomic():
        obj = get_object_or_404(Resource, pk=pk)
        course = get_object_or_404(Course.objects.select_for_update(), pk=obj.course_id)
        require_teacher(request.user, course)
        require_active_course(course)
        if request.method == 'POST':
            obj.delete()
            messages.success(request, '学习资料已删除。')
            return redirect(course)
    return render(request, 'resources/resource_confirm_delete.html', {'resource': obj})


@login_required
def download_resource(request, pk):
    resource = get_object_or_404(Resource, pk=pk)
    if resource.workspace_id:
        from research.permissions import require_workspace
        require_workspace(request.user, resource.workspace)
        return download_file(resource.resource_file)
    require_member(request.user, resource.course)
    return download_file(resource.resource_file)

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, Max
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from .forms import WorkspaceForm, MemberForm, TaskForm, CommitForm, UploadForm, CommentForm
from .models import ResearchWorkspace, WorkspaceMember, FileVersion, Activity
from .services import save_artifacts
from django.core.exceptions import ValidationError
from django_lms.permissions import download_file
from .permissions import require_workspace, workspace_reader


def filtered_commits(request, workspace):
    queryset = workspace.commits.select_related('author', 'related_task').prefetch_related('file_changes')
    keyword = request.GET.get('q', '').strip()[:200]
    if keyword:
        queryset = queryset.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))
    for param, field in (('member', 'author_id'), ('task', 'related_task_id')):
        value = request.GET.get(param, '')
        if value:
            if value.isdecimal() and len(value) < 19:
                queryset = queryset.filter(**{field: int(value)})
            else:
                queryset = queryset.none()
    return queryset


def paginate(request, queryset, size=20):
    query = request.GET.copy()
    query.pop('page', None)
    return {'page_obj': Paginator(queryset, size).get_page(request.GET.get('page')),
            'filter_query': query.urlencode() + '&' if query else ''}


def context(user, workspace, tab):
    role = require_workspace(user, workspace)
    return {'workspace': workspace, 'tab': tab, 'role': role,
            'can_write': role in ('owner', 'member') and workspace.status != 'archived', 'is_owner': role == 'owner',
            'guest_mode': workspace.is_demo}


@require_GET
def demo_list(request):
    projects = ResearchWorkspace.objects.filter(demo_key__isnull=False).exclude(demo_key='').select_related('owner').annotate(
        member_total=Count('memberships', distinct=True), task_total=Count('tasks', distinct=True),
        completed_total=Count('tasks', filter=Q(tasks__progress=100), distinct=True), commit_total=Count('commits', distinct=True)).order_by('demo_key')
    return render(request, 'research/demo_list.html', {'projects': projects, 'guest_mode': True})


@login_required
@require_GET
def workspace_list(request):
    projects = ResearchWorkspace.objects.filter(Q(owner=request.user) | Q(memberships__user=request.user)).distinct()
    keyword = request.GET.get('q', '').strip()[:200]
    if keyword:
        projects = projects.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
    data = paginate(request, projects.select_related('owner'), 12)
    data.update(projects=data['page_obj'], keyword=keyword)
    return render(request, 'research/list.html', data)


@login_required
@require_http_methods(['GET', 'POST'])
def workspace_create(request):
    form = WorkspaceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.owner = obj.created_by = request.user
            obj.save()
            Activity.objects.create(workspace=obj, actor=request.user, kind='workspace_created', title=obj.name)
        return redirect(obj)
    return render(request, 'research/form.html', {'form': form, 'heading': '创建科研项目'})


@login_required
@require_http_methods(['GET', 'POST'])
def workspace_edit(request, pk):
    with transaction.atomic():
        workspace = get_object_or_404(ResearchWorkspace.objects.select_for_update(), pk=pk)
        require_workspace(request.user, workspace, owner=True)
        form = WorkspaceForm(request.POST or None, instance=workspace)
        if request.method == 'POST' and form.is_valid():
            form.save()
            Activity.objects.create(workspace=workspace, actor=request.user, kind='workspace_updated', title=workspace.name,
                                    description=workspace.get_status_display())
            return redirect(workspace)
    return render(request, 'research/form.html', dict(context(request.user, workspace, 'overview'), form=form, heading='管理项目'))


@workspace_reader
@require_GET
def overview(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'overview')
    data['commits'] = workspace.commits.select_related('author', 'related_task').prefetch_related('file_changes')[:5]
    data['tasks'] = workspace.tasks.filter(progress__lt=100).select_related('assignee')[:6]
    data['member_count'] = workspace.memberships.exclude(user_id=workspace.owner_id).count() + 1
    data['task_count'] = workspace.tasks.count()
    data['completed_count'] = workspace.tasks.filter(progress=100).count()
    data['commit_count'] = workspace.commits.count()
    data['recent_files'] = workspace.files.annotate(last_upload=Max('versions__created_at')).order_by('-last_upload', '-pk').prefetch_related('versions')[:5]
    data['activities'] = workspace.activities.select_related('actor', 'commit', 'task', 'version__logical_file')[:5]
    return render(request, 'research/overview.html', data)


@workspace_reader
@require_http_methods(['GET', 'POST'])
def members(request, pk):
    with transaction.atomic():
        workspace = get_object_or_404(ResearchWorkspace.objects.select_for_update(), pk=pk)
        data = context(request.user, workspace, 'members')
        if request.method == 'POST':
            require_workspace(request.user, workspace, owner=True, write=True)
        form = MemberForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            if form.member_user.pk == workspace.owner_id:
                form.add_error('username', '项目负责人已拥有管理权限。')
            else:
                membership, created = WorkspaceMember.objects.update_or_create(workspace=workspace, user=form.member_user, defaults={'role': form.cleaned_data['role']})
                Activity.objects.create(workspace=workspace, actor=request.user, kind='member_joined' if created else 'member_updated',
                                        title='{} · {}'.format(form.member_user, membership.get_role_display()))
                messages.success(request, '成员及角色已保存。')
                return redirect('research:members', pk=pk)
    data.update(form=form, memberships=workspace.memberships.select_related('user').order_by('user__username'))
    now = timezone.now()
    local_now = timezone.localtime(now)
    week_start = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    summary = {item['author_id']: item for item in workspace.commits.order_by().values('author_id').annotate(
        latest=Max('created_at'), week_count=Count('pk', filter=Q(created_at__gte=week_start, created_at__lte=now)))}
    rows = [(workspace.owner, '项目负责人')] + [(m.user, m.get_role_display()) for m in data['memberships'] if m.user_id != workspace.owner_id]
    data['member_rows'] = [{'user': user, 'role': role, 'latest': summary.get(user.pk, {}).get('latest'),
                           'week_count': summary.get(user.pk, {}).get('week_count', 0)} for user, role in rows]
    data['week_start'] = week_start
    return render(request, 'research/members.html', data)


@workspace_reader
@require_GET
def tasks(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'tasks')
    queryset = workspace.tasks.select_related('assignee')
    status = request.GET.get('status', '')
    if status == 'completed':
        queryset = queryset.filter(progress=100)
    elif status == 'ongoing':
        queryset = queryset.filter(progress__lt=100)
    data.update(paginate(request, queryset))
    data['tasks'] = data['page_obj']
    return render(request, 'research/tasks.html', data)


@login_required
@require_http_methods(['GET', 'POST'])
def task_create(request, pk):
    with transaction.atomic():
        workspace = get_object_or_404(ResearchWorkspace.objects.select_for_update(), pk=pk)
        require_workspace(request.user, workspace, owner=True, write=True)
        form = TaskForm(request.POST or None, workspace=workspace)
        if request.method == 'POST' and form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()
            Activity.objects.create(workspace=workspace, actor=request.user, kind='task_created', title=task.title, task=task)
            if task.progress == 100:
                Activity.objects.create(workspace=workspace, actor=request.user, kind='task_completed', title=task.title, task=task)
            return redirect('research:task_detail', pk=pk, task_id=task.pk)
    return render(request, 'research/form.html', dict(context(request.user, workspace, 'tasks'), form=form, heading='创建科研任务'))


@workspace_reader
@require_http_methods(['GET', 'POST'])
def task_detail(request, pk, task_id):
    with transaction.atomic():
        workspace = get_object_or_404(ResearchWorkspace.objects.select_for_update(), pk=pk)
        data = context(request.user, workspace, 'tasks')
        task = get_object_or_404(workspace.tasks, pk=task_id)
        old_progress = task.progress
        can_manage = data['can_write'] and (data['is_owner'] or task.assignee_id == request.user.pk)
        form = TaskForm(request.POST or None, workspace=workspace, instance=task)
        if request.method == 'POST':
            require_workspace(request.user, workspace, write=True)
            if not can_manage:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied('只有项目负责人或任务负责人可以更新任务。')
            if not data['is_owner']:
                for field in ('title', 'description', 'assignee'):
                    form.fields[field].disabled = True
            if form.is_valid():
                form.save()
                Activity.objects.create(workspace=workspace, actor=request.user,
                    kind='task_completed' if old_progress != 100 and task.progress == 100 else 'task_updated',
                    title=task.title, description='进度 {}% → {}%'.format(old_progress, task.progress), task=task)
                return redirect('research:task_detail', pk=pk, task_id=task_id)
    data.update(paginate(request, task.commits.select_related('author', 'related_task').prefetch_related('file_changes')))
    data.update(task=task, form=form, can_manage=can_manage, commits=data['page_obj'])
    return render(request, 'research/task_detail.html', data)


@login_required
@require_http_methods(['GET', 'POST'])
def commit_create(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    require_workspace(request.user, workspace, write=True)
    form = CommitForm(request.POST or None, request.FILES or None, workspace=workspace)
    if request.method == 'POST' and form.is_valid():
        def create_commit(locked_workspace):
            commit = form.save(commit=False)
            commit.workspace = locked_workspace
            commit.author = request.user
            commit.save()
            return commit
        try:
            commit, _ = save_artifacts(workspace, request.user, form.cleaned_data, create_commit)
            return redirect(commit)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'research/form.html', dict(context(request.user, workspace, 'history'), form=form, heading='提交科研进度', note='提交后保留原始内容；需要修正时请追加一次进度。', file_inventory=list(workspace.files.values('id', 'name'))))


@workspace_reader
@require_GET
def history(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'history')
    data.update(paginate(request, filtered_commits(request, workspace)))
    data['task_options'] = workspace.tasks.all()
    data['member_options'] = get_user_model().objects.filter(Q(pk=workspace.owner_id) | Q(pk__in=workspace.memberships.values('user_id'))).order_by('username')
    return render(request, 'research/history.html', data)


@workspace_reader
@require_GET
def commit_detail(request, pk, commit_id):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'history')
    data['commit'] = get_object_or_404(workspace.commits.select_related('author', 'related_task', 'parent_commit').prefetch_related(
        'file_changes__version__logical_file', 'file_changes__previous_version', 'comments__author'), pk=commit_id)
    data['comment_form'] = CommentForm()
    return render(request, 'research/commit_detail.html', data)


@workspace_reader
@require_GET
def files(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'files')
    queryset = workspace.files.prefetch_related('versions__uploaded_by')
    keyword = request.GET.get('q', '').strip()[:200]
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    data.update(paginate(request, queryset))
    data['files'] = data['page_obj']
    return render(request, 'research/files.html', data)


@login_required
@require_http_methods(['GET', 'POST'])
def file_upload(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    require_workspace(request.user, workspace, write=True)
    initial = {}
    target = request.GET.get('file', '')
    if target.isdecimal() and len(target) < 19:
        initial = {'logical_file': get_object_or_404(workspace.files, pk=int(target)), 'duplicate_action': 'version'}
    form = UploadForm(request.POST or None, request.FILES or None, workspace=workspace, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            _, versions = save_artifacts(workspace, request.user, form.cleaned_data)
            return redirect('research:file_detail', pk=pk, file_id=versions[0].logical_file_id)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'research/form.html', dict(context(request.user, workspace, 'files'), form=form, heading='上传项目文件', file_inventory=list(workspace.files.values('id', 'name'))))


@workspace_reader
@require_GET
def file_detail(request, pk, file_id):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'files')
    logical = get_object_or_404(workspace.files, pk=file_id)
    data.update(paginate(request, logical.versions.select_related('uploaded_by', 'resource').prefetch_related('commit_changes__commit')))
    data.update(logical_file=logical, versions=data['page_obj'], current_version=logical.current_version)
    return render(request, 'research/file_detail.html', data)


@workspace_reader
@require_GET
def version_download(request, pk, version_id):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    require_workspace(request.user, workspace)
    version = get_object_or_404(FileVersion.objects.select_related('resource', 'logical_file'), pk=version_id, logical_file__workspace=workspace)
    response = download_file(version.resource.resource_file)
    from django.utils.http import urlquote
    response['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(urlquote(version.logical_file.name))
    return response


@login_required
@require_http_methods(['POST'])
def comment_create(request, pk, commit_id):
    with transaction.atomic():
        workspace = get_object_or_404(ResearchWorkspace.objects.select_for_update(), pk=pk)
        require_workspace(request.user, workspace, write=True)
        commit = get_object_or_404(workspace.commits, pk=commit_id)
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.commit = commit
            comment.save()
            Activity.objects.create(workspace=workspace, actor=request.user, kind='comment', title=commit.title,
                                    description=comment.content, comment=comment, commit=commit)
            return redirect(commit)
    data = context(request.user, workspace, 'history')
    data.update(commit=commit, comment_form=form)
    return render(request, 'research/commit_detail.html', data)


@workspace_reader
@require_GET
def activity(request, pk):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'activity')
    data.update(paginate(request, workspace.activities.select_related('actor', 'commit', 'task', 'version__logical_file'), 25))
    return render(request, 'research/activity.html', data)


@workspace_reader
@require_GET
def member_activity(request, pk, user_id):
    workspace = get_object_or_404(ResearchWorkspace, pk=pk)
    data = context(request.user, workspace, 'members')
    user = get_object_or_404(get_user_model(), pk=user_id)
    if user.pk != workspace.owner_id and not workspace.memberships.filter(user=user).exists():
        from django.http import Http404
        raise Http404('此账号不是项目成员。')
    data['member_user'] = user
    data.update(paginate(request, workspace.commits.filter(author=user).select_related('author', 'related_task').prefetch_related('file_changes')))
    return render(request, 'research/member_activity.html', data)

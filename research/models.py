from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.urls import reverse


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('历史记录不能覆盖，请追加新记录。')

    def delete(self):
        raise ValidationError('科研历史不能删除。')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('历史记录不能覆盖。')


class AppendOnly(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('历史记录不能覆盖，请新建修正记录。')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('科研历史不能删除。')

    class Meta:
        abstract = True


class ResearchWorkspace(models.Model):
    STATUS = [('active', '进行中'), ('paused', '暂停'), ('completed', '已完成'), ('archived', '已归档')]
    name = models.CharField('项目名称', max_length=200)
    description = models.TextField('项目简介')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_workspaces')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_workspaces')
    status = models.CharField('项目状态', max_length=12, choices=STATUS, default='active')
    demo_key = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def is_demo(self):
        return bool(self.demo_key)

    def get_absolute_url(self):
        return reverse('research:overview', args=[self.pk])

    class Meta:
        ordering = ['-updated_at', '-pk']


class WorkspaceMember(models.Model):
    # Owner is represented by Workspace.owner, never a competing membership role.
    ROLE = [('member', '项目成员'), ('viewer', '只读成员')]
    workspace = models.ForeignKey(ResearchWorkspace, on_delete=models.PROTECT, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField('角色', max_length=10, choices=ROLE, default='member')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')]


class ResearchTask(models.Model):
    workspace = models.ForeignKey(ResearchWorkspace, on_delete=models.PROTECT, related_name='tasks')
    title = models.CharField('任务名称', max_length=200)
    description = models.TextField('任务说明', blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='research_tasks')
    progress = models.PositiveSmallIntegerField('进度（%）', default=0, validators=[MaxValueValidator(100)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def clean(self):
        if self.assignee_id and self.workspace_id:
            if self.assignee_id != self.workspace.owner_id and not self.workspace.memberships.filter(user_id=self.assignee_id, role='member').exists():
                raise ValidationError({'assignee': '负责人必须是本项目可写成员。'})

    class Meta:
        ordering = ['-created_at', '-pk']


class ProgressCommit(AppendOnly):
    workspace = models.ForeignKey(ResearchWorkspace, on_delete=models.PROTECT, related_name='commits')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='progress_commits')
    title = models.CharField('标题', max_length=200)
    description = models.TextField('今天做了什么？')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, default='submitted', editable=False)
    related_task = models.ForeignKey(ResearchTask, null=True, blank=True, on_delete=models.PROTECT, related_name='commits')
    parent_commit = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='followups')

    def clean(self):
        if self.related_task_id and self.related_task.workspace_id != self.workspace_id:
            raise ValidationError({'related_task': '不能关联其他项目的任务。'})
        if self.parent_commit_id and self.parent_commit.workspace_id != self.workspace_id:
            raise ValidationError({'parent_commit': '不能关联其他项目的进度。'})

    def get_absolute_url(self):
        return reverse('research:commit_detail', args=[self.workspace_id, self.pk])

    class Meta:
        ordering = ['-created_at', '-pk']


class LogicalFile(AppendOnly):
    workspace = models.ForeignKey(ResearchWorkspace, on_delete=models.PROTECT, related_name='files')
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def current_version(self):
        return self.versions.order_by('-version_number').first()

    def __str__(self):
        return '{} · 文件 #{}'.format(self.name, self.pk)

    class Meta:
        ordering = ['name', 'pk']


class FileVersion(AppendOnly):
    logical_file = models.ForeignKey(LogicalFile, on_delete=models.PROTECT, related_name='versions')
    version_number = models.PositiveIntegerField()
    resource = models.OneToOneField('resources.Resource', on_delete=models.PROTECT, related_name='research_version')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)
    size = models.PositiveIntegerField()
    checksum = models.CharField(max_length=64)

    def clean(self):
        if self.resource_id and self.logical_file_id and self.resource.workspace_id != self.logical_file.workspace_id:
            raise ValidationError('文件版本和附件必须属于同一个项目。')

    def __str__(self):
        return '{} · v{} · 文件 #{}'.format(self.logical_file.name, self.version_number, self.logical_file_id)

    class Meta:
        ordering = ['-version_number']
        constraints = [models.UniqueConstraint(fields=['logical_file', 'version_number'], name='unique_file_version')]


class CommitFileChange(AppendOnly):
    commit = models.ForeignKey(ProgressCommit, on_delete=models.PROTECT, related_name='file_changes')
    version = models.ForeignKey(FileVersion, on_delete=models.PROTECT, related_name='commit_changes')
    previous_version = models.ForeignKey(FileVersion, null=True, blank=True, on_delete=models.PROTECT, related_name='superseded_in')
    kind = models.CharField(max_length=10, choices=[('new', '新增文件'), ('version', '新版本'), ('reference', '引用已有版本')])

    def clean(self):
        if self.version_id and self.commit_id and self.version.logical_file.workspace_id != self.commit.workspace_id:
            raise ValidationError('不能关联其他项目的文件。')
        if self.previous_version_id and (self.previous_version.logical_file_id != self.version.logical_file_id or self.previous_version.version_number >= self.version.version_number):
            raise ValidationError('前一版本必须属于同一文件且早于本版本。')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['commit', 'version'], name='unique_commit_file_version')]


class CommitComment(AppendOnly):
    commit = models.ForeignKey(ProgressCommit, on_delete=models.PROTECT, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    content = models.TextField('评论')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class Activity(AppendOnly):
    TYPES = [('workspace_created', '创建项目'), ('workspace_updated', '更新项目'),
             ('progress_commit', '提交科研进度'), ('file_upload', '上传文件'), ('file_new_version', '上传新版本'),
             ('task_created', '创建任务'), ('task_updated', '更新任务'), ('task_completed', '完成任务'),
             ('comment', '发表评论'), ('member_joined', '加入成员'), ('member_updated', '调整角色')]
    workspace = models.ForeignKey(ResearchWorkspace, on_delete=models.PROTECT, related_name='activities')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=24, choices=TYPES)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    commit = models.ForeignKey(ProgressCommit, null=True, blank=True, on_delete=models.PROTECT)
    task = models.ForeignKey(ResearchTask, null=True, blank=True, on_delete=models.PROTECT)
    version = models.ForeignKey(FileVersion, null=True, blank=True, on_delete=models.PROTECT)
    comment = models.ForeignKey(CommitComment, null=True, blank=True, on_delete=models.PROTECT)

    def clean(self):
        for item in (self.commit, self.task, self.version.logical_file if self.version_id else None,
                     self.comment.commit if self.comment_id else None):
            if item is not None and item.workspace_id != self.workspace_id:
                raise ValidationError('动态关联对象必须属于当前项目。')

    class Meta:
        ordering = ['-created_at', '-pk']

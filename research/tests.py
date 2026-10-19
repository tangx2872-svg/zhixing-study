from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from users.models import User
from .models import ResearchWorkspace, WorkspaceMember, ResearchTask, ProgressCommit
import hashlib
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, TransactionTestCase
from django.test import Client
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from resources.models import Resource
from .models import LogicalFile, FileVersion, CommitFileChange
from .services import save_artifacts
from .models import Activity, CommitComment
from django.utils import timezone
from datetime import timedelta


class ResearchTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp(prefix='research-tests-')
        self.media = Path(media)
        self.addCleanup(shutil.rmtree, media)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.owner = User.objects.create_user('supervisor', user_type=2)
        self.member = User.objects.create_user('researcher')
        self.viewer = User.objects.create_user('viewer')
        self.outsider = User.objects.create_user('outsider')
        self.workspace = ResearchWorkspace.objects.create(name='异常检测', description='研究', owner=self.owner, created_by=self.owner)
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.member)
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.viewer, role='viewer')
        self.task = ResearchTask.objects.create(workspace=self.workspace, title='baseline', created_by=self.owner, assignee=self.member)

    def file(self, data=b'result v1', name='results.csv'):
        return SimpleUploadedFile(name, data)

    def download(self, version, expected):
        response = self.client.get(self.url('version_download', version.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), expected)
        response.close()

    def url(self, name, *args):
        return reverse('research:' + name, args=[self.workspace.pk, *args])

    def test_create_workspace_member_task_commit(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('research:create'), {'name': '新研究', 'description': '问题', 'status': 'active'}).status_code, 302)
        self.assertEqual(self.client.post(self.url('members'), {'username': self.outsider.username, 'role': 'member'}).status_code, 302)
        self.assertEqual(self.client.post(self.url('task_create'), {'title': '新任务', 'description': '分析', 'assignee': self.member.pk, 'progress': 0}).status_code, 302)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.url('commit_create'), {'title': '完成 baseline', 'description': 'AUROC 0.982', 'related_task': self.task.pk}).status_code, 302)
        commit = ProgressCommit.objects.get()
        self.assertEqual(commit.author, self.member)
        self.assertEqual(commit.related_task, self.task)
        self.assertContains(self.client.get(self.url('history')), '完成 baseline')
        self.assertContains(self.client.get(self.url('task_detail', self.task.pk)), '完成 baseline')

    def test_readers_and_unauthorized_access(self):
        for user in (self.owner, self.member, self.viewer):
            self.client.force_login(user)
            for route in ('overview', 'history', 'members', 'tasks'):
                self.assertEqual(self.client.get(self.url(route)).status_code, 200)
        self.client.force_login(self.viewer)
        for route in ('commit_create', 'task_create', 'edit', 'members'):
            self.assertEqual(self.client.post(self.url(route), {}).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url('overview')).status_code, 403)
        self.assertNotContains(self.client.get(reverse('research:list')), self.workspace.name)
        self.client.logout()
        self.assertEqual(self.client.get(self.url('history')).status_code, 302)

    def test_history_cannot_be_rewritten_or_deleted(self):
        commit = ProgressCommit.objects.create(workspace=self.workspace, author=self.member, title='original', description='original')
        commit.title = 'changed'
        with self.assertRaises(ValidationError):
            commit.save()
        with self.assertRaises(ValidationError):
            ProgressCommit.objects.filter(pk=commit.pk).update(title='changed')
        with self.assertRaises(ValidationError):
            commit.delete()
        with self.assertRaises(ProtectedError):
            self.member.delete()
        commit.refresh_from_db()
        self.assertEqual(commit.title, 'original')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(commit.get_absolute_url(), {'title': 'overwrite'}).status_code, 405)

    def test_cross_project_links_rejected(self):
        other = ResearchWorkspace.objects.create(name='其他', description='x', owner=self.owner, created_by=self.owner)
        task = ResearchTask.objects.create(workspace=other, title='其他任务', created_by=self.owner)
        parent = ProgressCommit.objects.create(workspace=other, author=self.owner, title='其他提交', description='x')
        self.client.force_login(self.member)
        response = self.client.post(self.url('commit_create'), {'title': '非法', 'description': 'x', 'related_task': task.pk, 'parent_commit': parent.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workspace.commits.count(), 0)

    def test_task_progress_and_archive(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.url('task_detail', self.task.pk), {'progress': 100, 'title': '篡改名称'}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.progress, 100)
        self.assertEqual(self.task.title, 'baseline')
        self.workspace.status = 'archived'
        self.workspace.save()
        self.assertEqual(self.client.post(self.url('commit_create'), {'title': 'x', 'description': 'x'}).status_code, 403)
        self.assertEqual(self.client.get(self.url('history')).status_code, 200)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url('edit'), {'name': '异常检测', 'description': '研究', 'status': 'active'}).status_code, 302)

    def test_commit_versions_preserve_old_bytes_and_links(self):
        self.client.force_login(self.member)
        for index, data in enumerate((b'result v1', b'result v2'), 1):
            response = self.client.post(self.url('commit_create'), {'title': '实验 {}'.format(index), 'description': '完成',
                'related_task': self.task.pk, 'uploads': self.file(data), 'duplicate_action': 'version', 'version_description': '版本 {}'.format(index)})
            self.assertEqual(response.status_code, 302)
        logical = LogicalFile.objects.get()
        v1, v2 = list(logical.versions.order_by('version_number'))
        self.assertNotEqual(v1.resource.resource_file.name, v2.resource.resource_file.name)
        self.assertEqual(v2.checksum, hashlib.sha256(b'result v2').hexdigest())
        self.assertEqual(v2.version_number, 2)
        change = CommitFileChange.objects.get(version=v2)
        self.assertEqual(change.previous_version, v1)
        self.assertEqual(change.kind, 'version')
        self.assertContains(self.client.get(change.commit.get_absolute_url()), 'v1 → v2')
        self.assertContains(self.client.get(self.url('files')), 'results.csv')
        self.assertContains(self.client.get(self.url('file_detail', logical.pk)), 'v2')
        self.download(v1, b'result v1')
        self.download(v2, b'result v2')
        self.client.force_login(self.viewer)
        self.download(v1, b'result v1')
        self.assertEqual(self.client.post(self.url('file_upload'), {'uploads': self.file()}).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url('version_download', v1.pk)).status_code, 403)
        self.assertEqual(self.client.get(reverse('resources:download', args=[v1.resource_id])).status_code, 403)
        with self.assertRaises(ProtectedError):
            v1.resource.delete()
        with self.assertRaises(ValidationError):
            v1.resource.save()
        with self.assertRaises(ValidationError):
            v1.save()

    def test_same_name_requires_choice_and_independent_files_are_distinct(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.url('file_upload'), {'uploads': self.file()}).status_code, 302)
        response = self.client.post(self.url('commit_create'), {'title': 'collision', 'description': 'x', 'uploads': self.file(b'v2')})
        self.assertContains(response, '检测到同名文件')
        self.assertEqual(self.workspace.commits.count(), 0)
        self.assertEqual(FileVersion.objects.count(), 1)
        self.assertEqual(self.client.post(self.url('file_upload'), {'uploads': self.file(b'separate'), 'duplicate_action': 'independent'}).status_code, 302)
        self.assertEqual(LogicalFile.objects.count(), 2)
        response = self.client.post(self.url('file_upload'), {'uploads': self.file(), 'duplicate_action': 'version'})
        self.assertContains(response, '有多个独立文件')
        logical = LogicalFile.objects.first()
        self.assertEqual(self.client.post(self.url('file_upload'), {'uploads': self.file(b'v2'), 'logical_file': logical.pk, 'duplicate_action': 'version'}).status_code, 302)
        self.assertEqual(logical.current_version.version_number, 2)

    def test_existing_version_reference_and_cross_project_rejection(self):
        _, versions = save_artifacts(self.workspace, self.member, {'uploads': [self.file()]})
        version = versions[0]
        self.client.force_login(self.member)
        response = self.client.post(self.url('commit_create'), {'title': '引用成果', 'description': 'x', 'existing_versions': [version.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CommitFileChange.objects.get().kind, 'reference')
        self.assertEqual(FileVersion.objects.count(), 1)
        other = ResearchWorkspace.objects.create(name='其他', description='x', owner=self.owner, created_by=self.owner)
        response = self.client.post(reverse('research:commit_create', args=[other.pk]), {'title': '非法', 'description': 'x', 'existing_versions': [version.pk]})
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('research:commit_create', args=[other.pk]), {'title': '非法', 'description': 'x', 'existing_versions': [version.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(other.commits.count(), 0)
        self.assertEqual(self.client.get(reverse('research:version_download', args=[other.pk, version.pk])).status_code, 404)

    def test_failed_upload_rolls_back_db_and_storage(self):
        with patch('research.services.FileVersion.objects.create', side_effect=RuntimeError('simulated DB failure')):
            with self.assertRaises(RuntimeError):
                save_artifacts(self.workspace, self.member, {'uploads': [self.file()]})
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(LogicalFile.objects.count(), 0)
        self.assertEqual([p for p in self.media.rglob('*') if p.is_file()], [])

    def test_failed_second_file_rolls_back_commit_and_first_file(self):
        original = FileVersion.objects.create
        attempts = []

        def fail_second(**kwargs):
            attempts.append(kwargs)
            if len(attempts) == 2:
                raise RuntimeError('second version failed')
            return original(**kwargs)

        def create_commit(workspace):
            return ProgressCommit.objects.create(workspace=workspace, author=self.member, title='batch', description='x')

        with patch('research.services.FileVersion.objects.create', side_effect=fail_second), self.assertRaises(RuntimeError):
            save_artifacts(self.workspace, self.member, {'uploads': [self.file(), self.file(name='readme.md')]}, create_commit)
        self.assertEqual(Resource.objects.count(), 0)
        self.assertEqual(ProgressCommit.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 0)
        self.assertEqual([p for p in self.media.rglob('*') if p.is_file()], [])

    def test_conflicting_upload_options_and_csrf_are_rejected(self):
        _, versions = save_artifacts(self.workspace, self.member, {'uploads': [self.file()]})
        self.client.force_login(self.member)
        response = self.client.post(self.url('file_upload'), {'uploads': self.file(), 'logical_file': versions[0].logical_file_id, 'duplicate_action': 'independent'})
        self.assertContains(response, '请清空')
        self.assertEqual(FileVersion.objects.count(), 1)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)
        self.assertEqual(client.post(self.url('commit_create'), {'title': 'csrf', 'description': 'x'}).status_code, 403)
        self.assertEqual(ProgressCommit.objects.count(), 0)

    def test_member_week_counts_use_beijing_week_and_project_scope(self):
        now = timezone.now()
        monday = (timezone.localtime(now) - timedelta(days=timezone.localtime(now).weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        for created_at in (monday - timedelta(seconds=1), monday, now):
            with patch('django.utils.timezone.now', return_value=created_at):
                ProgressCommit.objects.create(workspace=self.workspace, author=self.member, title='阶段记录', description='x')
        other = ResearchWorkspace.objects.create(name='其他', description='x', owner=self.member, created_by=self.member)
        ProgressCommit.objects.create(workspace=other, author=self.member, title='其他进度', description='x')
        self.client.force_login(self.owner)
        response = self.client.get(self.url('members'))
        row = next(r for r in response.context['member_rows'] if r['user'] == self.member)
        self.assertEqual(row['week_count'], 2)

    def test_all_files_are_validated_and_batch_is_atomic(self):
        self.client.force_login(self.member)
        response = self.client.post(self.url('commit_create'), {'title': 'invalid', 'description': 'x',
            'uploads': [self.file(), self.file(b'bad', 'malware.exe')]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FileVersion.objects.count(), 0)
        self.assertEqual(ProgressCommit.objects.count(), 0)
        self.assertEqual(self.client.post(self.url('file_upload'), {'uploads': self.file(b'')}).status_code, 200)

    def test_activity_comments_and_members_progress(self):
        self.client.force_login(self.member)
        self.client.post(self.url('commit_create'), {'title': '实验结果', 'description': '完成', 'uploads': self.file()})
        commit = self.workspace.commits.get()
        self.assertEqual(Activity.objects.filter(kind='progress_commit').count(), 1)
        self.assertEqual(Activity.objects.filter(kind='file_upload').count(), 1)
        self.assertEqual(self.client.post(self.url('comment_create', commit.pk), {'content': '补充 cable'}).status_code, 302)
        self.assertContains(self.client.get(commit.get_absolute_url()), '补充 cable')
        self.assertContains(self.client.get(self.url('activity')), '发表评论')
        self.assertContains(self.client.get(self.url('member_activity', self.member.pk)), '实验结果')
        response = self.client.get(self.url('members'))
        row = next(r for r in response.context['member_rows'] if r['user'] == self.member)
        self.assertEqual(row['week_count'], 1)
        self.assertIsNotNone(row['latest'])
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(self.url('comment_create', commit.pk), {'content': '非法'}).status_code, 403)
        self.assertEqual(self.client.get(self.url('activity')).status_code, 200)
        self.assertEqual(CommitComment.objects.count(), 1)
        comment = CommitComment.objects.get()
        comment.content = '覆盖'
        with self.assertRaises(ValidationError):
            comment.save()
        self.client.force_login(self.member)
        self.assertContains(self.client.post(self.url('comment_create', commit.pk), {'content': '   '}), '这个字段是必填项')
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url('activity')).status_code, 403)

    def test_member_join_and_task_completion_are_logged(self):
        self.client.force_login(self.owner)
        self.client.post(self.url('members'), {'username': self.outsider.username, 'role': 'member'})
        self.assertEqual(Activity.objects.get(kind='member_joined').actor, self.owner)
        self.client.post(self.url('members'), {'username': self.outsider.username, 'role': 'viewer'})
        self.assertEqual(Activity.objects.filter(kind='member_updated').count(), 1)
        self.client.force_login(self.member)
        self.client.post(self.url('task_detail', self.task.pk), {'progress': 100})
        self.assertEqual(Activity.objects.get(kind='task_completed').description, '进度 0% → 100%')
        self.client.post(self.url('task_detail', self.task.pk), {'progress': 100})
        self.assertEqual(Activity.objects.filter(kind='task_completed').count(), 1)

    def test_dashboard_and_history_filters_and_pagination(self):
        for index in range(23):
            ProgressCommit.objects.create(workspace=self.workspace, author=self.member, related_task=self.task,
                                          title='baseline {}'.format(index), description='AUROC')
        ProgressCommit.objects.create(workspace=self.workspace, author=self.owner, title='文献阅读', description='总结')
        self.client.force_login(self.member)
        response = self.client.get(self.url('overview'))
        self.assertEqual(response.context['member_count'], 3)
        self.assertEqual(response.context['commit_count'], 24)
        self.assertEqual(response.context['task_count'], 1)
        self.assertContains(response, '最近文件')
        query = {'member': self.member.pk, 'task': self.task.pk, 'q': 'baseline'}
        response = self.client.get(self.url('history'), query)
        self.assertEqual(response.context['page_obj'].paginator.count, 23)
        self.assertEqual(len(response.context['page_obj']), 20)
        self.assertContains(response, 'q=baseline')
        response = self.client.get(self.url('history'), dict(query, page=2))
        self.assertEqual(len(response.context['page_obj']), 3)
        self.assertEqual(self.client.get(self.url('history'), {'member': 'invalid'}).context['page_obj'].paginator.count, 0)
        self.assertContains(self.client.get(self.url('history'), {'q': '文献'}), '文献阅读')
        self.assertEqual(self.client.get(self.url('tasks'), {'status': 'completed'}).context['page_obj'].paginator.count, 0)
        self.assertEqual(self.client.get(self.url('member_activity', self.outsider.pk)).status_code, 404)


class ResearchMigrationTests(TransactionTestCase):
    def test_legacy_course_resource_survives_upgrade(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [(app, name) for app, name in latest if app not in ('resources', 'research')]
        old += [('resources', '0001_initial'), ('research', '0001_initial')]
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            user = apps.get_model('users', 'User').objects.create(username='legacy-owner')
            course = apps.get_model('courses', 'Course').objects.create(course_name='旧课程', course_description='保留', teacher_id=user.pk)
            resource = apps.get_model('resources', 'Resource').objects.create(resource_name='旧资料', resource_file='old-guide.pdf', course_id=course.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            resource = apps.get_model('resources', 'Resource').objects.get(pk=resource.pk)
            self.assertEqual(resource.course_id, course.pk)
            self.assertEqual(resource.resource_file.name, 'old-guide.pdf')
            self.assertIsNone(resource.workspace_id)
        finally:
            MigrationExecutor(connection).migrate(latest)

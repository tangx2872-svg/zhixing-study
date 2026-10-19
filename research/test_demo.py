import shutil
import tempfile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from users.models import User
from .demo import seed_demo
from .models import ResearchWorkspace, ProgressCommit, FileVersion, Activity, WorkspaceMember
from .services import save_artifacts


class GuestDemoTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp(prefix='guest-demo-tests-')
        self.addCleanup(shutil.rmtree, media)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.projects = [project for project, _ in seed_demo()]
        self.project = next(p for p in self.projects if p.demo_key == 'illumination-demo-v1')
        self.owner = User.objects.create_user('real-supervisor', password='test-password', user_type=2)
        self.private = ResearchWorkspace.objects.create(name='保密课题', description='不公开的真实内容', created_by=self.owner, owner=self.owner)
        self.private_commit = ProgressCommit.objects.create(workspace=self.private, author=self.owner, title='真实实验记录', description='private')

    def url(self, route, *extra, project=None):
        return reverse('research:' + route, args=[(project or self.project).pk, *extra])

    def test_anonymous_demo_navigation_and_private_project_stays_private(self):
        self.assertContains(self.client.get('/'), '访客体验')
        response = self.client.get(reverse('research:demo'))
        self.assertContains(response, self.project.name)
        self.assertNotContains(response, '保密课题')
        for route in ('overview', 'tasks', 'history', 'files', 'members', 'activity'):
            self.assertContains(self.client.get(self.url(route)), '访客演示')
            self.assertEqual(self.client.get(self.url(route, project=self.private)).status_code, 302)
        self.assertEqual(self.client.get(self.private_commit.get_absolute_url()).status_code, 302)
        self.assertEqual(self.client.get(self.url('commit_detail', self.private_commit.pk)).status_code, 404)
        self.assertContains(self.client.get(self.url('history'), {'q': 'baseline'}), 'baseline')

    def test_demo_versions_and_associated_details_are_public_read_only(self):
        logical = self.project.files.get(name='results.csv')
        self.assertEqual(logical.versions.count(), 3)
        self.assertContains(self.client.get(self.url('file_detail', logical.pk)), 'v3')
        for version in logical.versions.all():
            response = self.client.get(self.url('version_download', version.pk))
            self.assertEqual(response.status_code, 200)
            payload = b''.join(response.streaming_content)
            self.assertIn(b'bottle', payload)
            response.close()
            commit = version.commit_changes.get().commit
            self.assertContains(self.client.get(commit.get_absolute_url()), '下载本次记录')
        task = self.project.tasks.first()
        self.assertEqual(self.client.get(self.url('task_detail', task.pk)).status_code, 200)
        person = self.project.memberships.first().user
        self.assertEqual(self.client.get(self.url('member_activity', person.pk)).status_code, 200)
        self.assertNotContains(self.client.get(self.url('overview')), '>提交进度</a>')

    def test_guest_and_logged_in_users_cannot_write_demo(self):
        commit = self.project.commits.first()
        task = self.project.tasks.first()
        original_progress = task.progress
        for user in (None, self.owner, self.project.owner):
            if user is None:
                self.client.logout()
            else:
                self.client.force_login(user)
            for route, args in (('commit_create', ()), ('file_upload', ()), ('edit', ()), ('members', ()),
                                ('task_create', ()), ('task_detail', (task.pk,)), ('comment_create', (commit.pk,))):
                response = self.client.post(self.url(route, *args), {'content': 'overwrite', 'progress': 0})
                self.assertIn(response.status_code, (302, 403))
            with self.assertRaises(PermissionDenied):
                save_artifacts(self.project, user or self.owner, {'uploads': []})
        self.assertEqual(self.project.commits.count(), 7)
        task.refresh_from_db()
        self.assertEqual(task.progress, original_progress)

    def test_seed_is_idempotent_and_virtual_accounts_cannot_login(self):
        before = (User.objects.count(), ProgressCommit.objects.count(), FileVersion.objects.count(), Activity.objects.count())
        call_command('seed_research_demo', verbosity=0)
        self.assertEqual(before, (User.objects.count(), ProgressCommit.objects.count(), FileVersion.objects.count(), Activity.objects.count()))
        for person in User.objects.filter(username__startswith='__research_demo_'):
            self.assertFalse(person.is_active)
            self.assertFalse(person.has_usable_password())
            self.assertFalse(self.client.login(username=person.username, password='!'))
        self.private.refresh_from_db()
        self.assertFalse(self.private.is_demo)
        self.assertEqual(self.private.name, '保密课题')

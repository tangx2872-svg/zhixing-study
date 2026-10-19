import csv
import io
import shutil
import stat
import tempfile
import zipfile
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courses.models import Course, Enrollment
from users.models import User
from .models import Assignment, SubmitAssignment, CourseGroup, GroupMember, SubmissionAttachment
from .code_review import archive_entries, text_content, side_by_side


class ExperimentTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp(prefix='experiment-tests-')
        self.addCleanup(shutil.rmtree, media)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.teacher = User.objects.create_user('lab_teacher', user_type=2)
        self.student = User.objects.create_user('lab_student', user_type=1)
        self.partner = User.objects.create_user('lab_partner', user_type=1)
        self.stranger = User.objects.create_user('lab_stranger', user_type=1)
        self.other_teacher = User.objects.create_user('lab_other_teacher', user_type=2)
        self.course = Course.objects.create(course_name='软件工程实验', course_description='x', teacher=self.teacher)
        for user in [self.student, self.partner, self.stranger]:
            Enrollment.objects.create(course=self.course, student=user)
        self.assignment = Assignment.objects.create(course=self.course, assignment_name='实验提交', assignment_description='完整材料', due_date=timezone.now() + timedelta(days=7))
        self.client.force_login(self.student)

    def url(self, name, pk=None, **kwargs):
        if kwargs and pk is not None:
            kwargs['pk'] = pk
        return reverse('assignments:' + name, kwargs=kwargs) if kwargs else reverse('assignments:' + name, args=[pk or self.assignment.pk])

    def file(self, name='main.py', data=b'print(1)\n'):
        return SimpleUploadedFile(name, data)

    def archive(self, files, name='project.zip'):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as output:
            for path, data in files.items():
                output.writestr(path, data)
        return self.file(name, stream.getvalue())

    def submit(self, **kwargs):
        data = {'topic': '本次成果', 'description': '完成实验', 'assignment_file': self.file()}
        data.update(kwargs)
        response = self.client.post(self.url('submit'), data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        return SubmitAssignment.objects.get(pk=response.url.rstrip('/').split('/')[-1])

    def group(self):
        self.assignment.submission_mode = 'group'
        self.assignment.save()
        group = CourseGroup.objects.create(course=self.course, name='第一组')
        for user in [self.student, self.partner]:
            GroupMember.objects.create(course=self.course, group=group, user=user)
        return group

    def test_new_version_preserves_files_and_grade(self):
        first = self.submit()
        first.grade_assignment(83, '第一版评分', self.teacher)
        second = self.submit(topic='修正版', assignment_file=self.file(data=b'print(2)\n'))
        first.refresh_from_db()
        self.assertIsNone(first.current_slot)
        self.assertEqual(first.grade, 83)
        self.assertEqual(first.grade_records.get().feedback, '第一版评分')
        self.assertEqual(second.version_number, 2)
        self.assertFalse(second.graded)
        self.assertNotEqual(first.assignment_file.name, second.assignment_file.name)
        response = self.client.get(self.url('download', first.pk))
        self.assertEqual(b''.join(response.streaming_content), b'print(1)\n')
        response.close()

    def test_withdraw_preserves_history_and_new_sequence(self):
        first = self.submit()
        self.assertEqual(self.client.post(self.url('submit_delete', first.pk)).status_code, 302)
        first.refresh_from_db()
        self.assertTrue(first.withdrawn)
        self.assertIsNotNone(first.withdrawn_at)
        second = self.submit()
        self.assertEqual(second.version_number, 2)
        self.assertTrue(first.assignment_file.storage.exists(first.assignment_file.name))

    def test_graded_version_cannot_be_withdrawn(self):
        first = self.submit()
        first.grade_assignment(90)
        self.assertEqual(self.client.post(self.url('submit_delete', first.pk)).status_code, 403)

    def test_keep_existing_and_same_name_replacement(self):
        first = self.submit(report_files=[self.file('report.md', b'# report')])
        second = self.submit(keep_existing='on', assignment_file=self.file(data=b'print(3)'))
        self.assertEqual(set(second.attachments.values_list('name', flat=True)), {'report.md', 'main.py'})
        self.assertEqual(first.attachments.get(name='report.md').file.name, second.attachments.get(name='report.md').file.name)

    def test_missing_materials_do_not_replace_current(self):
        first = self.submit()
        self.assignment.required_materials = ['code', 'report', 'screenshots']
        self.assignment.save()
        response = self.client.post(self.url('submit'), {'topic': '缺少材料', 'description': 'x', 'code_files': self.file()})
        self.assertContains(response, '缺少必交材料')
        first.refresh_from_db()
        self.assertEqual(first.current_slot, 1)
        self.assertEqual(self.assignment.question.count(), 1)

    def test_material_categories_and_multiple_files(self):
        self.assignment.required_materials = ['code', 'report', 'screenshots', 'test_report']
        self.assignment.save()
        response = self.client.post(self.url('submit'), {'topic': '齐全', 'description': 'x',
            'code_files': [self.file(), self.file('Main.java', b'class Main {}')],
            'report_files': self.file('report.pdf', b'%PDF-1.4'),
            'screenshots_files': self.file('run.png', b'\x89PNG\r\n\x1a\n'),
            'test_report_files': self.file('tests.html', b'<script>alert(1)</script>')})
        self.assertEqual(response.status_code, 302)
        submission = self.assignment.question.get()
        self.assertEqual(submission.attachments.count(), 5)
        self.assertEqual({item.category for item in submission.attachments.all()}, set(self.assignment.required_materials))

    def test_zip_browse_highlights_and_escapes_html(self):
        submission = self.submit(assignment_file=self.archive({'project/main.py': b'print(1)', 'project/page.html': b'<script>alert(1)</script>'}))
        response = self.client.get(self.url('browse', submission.pk), {'path': 'main.py'})
        self.assertContains(response, 'main.py')
        self.assertContains(response, 'line-number')
        response = self.client.get(self.url('browse', submission.pk), {'path': 'page.html'})
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(self.client.get(self.url('browse', submission.pk), {'path': '../main.py'}).status_code, 404)
        self.assertEqual(self.client.get(self.url('browse', submission.pk), {'path': 'page.html', 'raw': '1'}).status_code, 404)

    def test_diff_reports_add_delete_modify_and_unchanged(self):
        first = self.submit(assignment_file=self.archive({'v1/main.py': b'print(1)\n', 'v1/remove.txt': b'bye', 'v1/keep.txt': b'keep'}))
        second = self.submit(assignment_file=self.archive({'v2/main.py': b'print(2)\n', 'v2/add.txt': b'new', 'v2/keep.txt': b'keep'}))
        response = self.client.get(self.url('compare', second.pk), {'path': 'main.py'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['path']: row['status'] for row in response.context['changes']}, {'main.py': 'modified', 'remove.txt': 'deleted', 'keep.txt': 'unchanged', 'add.txt': 'added'})
        self.assertEqual(response.context['older'].pk, first.pk)
        self.assertEqual(response.context['diff_rows'][0]['left'], 'print(1)')
        self.assertEqual(response.context['diff_rows'][0]['right'], 'print(2)')

    def test_compare_cannot_cross_student_or_assignment(self):
        own = self.submit()
        self.client.force_login(self.stranger)
        other = self.submit()
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.url('compare', own.pk), {'from': other.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url('compare', own.pk), {'from': 'invalid'}).status_code, 404)

    def test_private_preview_compare_attachment_and_export(self):
        submission = self.submit()
        attachment = submission.attachments.get()
        endpoints = [self.url('browse', submission.pk), self.url('compare', submission.pk),
            self.url('attachment_download', pk=submission.pk, attachment_id=attachment.pk), self.url('download', submission.pk)]
        for user in [self.stranger, self.other_teacher]:
            self.client.force_login(user)
            for endpoint in endpoints:
                self.assertEqual(self.client.get(endpoint).status_code, 403, endpoint)
            self.assertEqual(self.client.get(self.url('export', pk=self.assignment.pk, kind='grades')).status_code, 403)
        self.client.logout()
        for endpoint in endpoints:
            self.assertEqual(self.client.get(endpoint).status_code, 302)

    def test_pdf_image_and_markdown_previews(self):
        submission = self.submit(assignment_file=self.file('report.md', b'# Report\n<script>alert(1)</script>'),
            report_files=[self.file('paper.pdf', b'%PDF-1.4\n%%EOF')],
            screenshots_files=[self.file('run.png', b'\x89PNG\r\n\x1a\n')])
        response = self.client.get(self.url('browse', submission.pk), {'path': 'report.md'})
        self.assertContains(response, '<h1>Report</h1>', html=True)
        self.assertNotContains(response, '<script>alert(1)</script>')
        for path, mime in [('paper.pdf', 'application/pdf'), ('run.png', 'image/png')]:
            response = self.client.get(self.url('browse', submission.pk), {'path': path, 'raw': '1'})
            self.assertEqual(response['Content-Type'], mime)
            self.assertIn("frame-ancestors 'self'" if path.endswith('.pdf') else 'sandbox', response['Content-Security-Policy'])

    def test_invalid_image_is_not_served_inline(self):
        submission = self.submit(assignment_file=self.file('fake.png', b'<html>'))
        self.assertEqual(self.client.get(self.url('browse', submission.pk), {'path': 'fake.png', 'raw': '1'}).status_code, 404)

    def test_archive_rejects_traversal_symlinks_bombs_duplicates(self):
        for path in ['../escape.py', '/absolute.py', 'C:/escape.py', 'a/../escape.py']:
            with self.assertRaises(ValidationError):
                archive_entries(self.archive({path: b'print(1)'}))
        with self.assertRaises(ValidationError):
            archive_entries(self.archive({'huge.txt': b'0' * (2 * 1024 * 1024)}))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            info = zipfile.ZipInfo('link')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, 'target')
        stream.seek(0)
        with self.assertRaises(ValidationError):
            archive_entries(stream)
        response = self.client.post(self.url('submit'), {'topic': '坏文件', 'description': 'x', 'code_files': self.file('bad.zip', b'not zip')})
        self.assertContains(response, '无法读取 ZIP')
        self.assertEqual(self.assignment.question.count(), 0)

    def test_browse_limits_and_binary_diff(self):
        first = self.submit(assignment_file=self.file('large.py', b'x' * (512 * 1024 + 1)))
        self.assertContains(self.client.get(self.url('browse', first.pk)), '超过在线预览')
        second = self.submit(assignment_file=self.file('image.png', b'\x89PNG\r\n\x1a\nNEW'))
        self.assertContains(self.client.get(self.url('compare', second.pk), {'path': 'image.png'}), '二进制文件')
        with self.assertRaises(ValidationError):
            side_by_side('x\n' * 2001, 'y\n')
        self.assertEqual(text_content('中文'.encode('gb18030')), '中文')
        self.assertIsNone(text_content(b'\x00\x01'))

    def test_failed_save_cleans_new_files_and_preserves_current(self):
        first = self.submit()
        with patch('assignments.submission_service.SubmissionAttachment.objects.bulk_create', side_effect=ValidationError('模拟失败')):
            response = self.client.post(self.url('submit'), {'topic': '新版', 'description': 'x', 'code_files': self.file('new.py')})
        self.assertContains(response, '模拟失败')
        first.refresh_from_db()
        self.assertEqual(first.current_slot, 1)
        self.assertEqual(self.assignment.question.count(), 1)
        from pathlib import Path
        from django.conf import settings
        self.assertEqual(len([p for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file()]), 1)

    def test_teacher_creates_groups_and_validates_course_membership(self):
        self.client.force_login(self.teacher)
        url = self.url('groups', course_id=self.course.pk)
        self.assertEqual(self.client.post(url, {'name': '第一组', 'members': [self.student.pk, self.partner.pk]}).status_code, 302)
        group = CourseGroup.objects.get()
        self.assertEqual(group.memberships.count(), 2)
        response = self.client.post(url, {'name': '重复归属', 'members': [self.student.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(url, {'name': '私自建组'}).status_code, 403)
        self.assertContains(self.client.get(url), '第一组')

    def test_group_submission_shared_and_membership_locked(self):
        group = self.group()
        first = self.submit()
        self.assertEqual(first.group, group)
        self.assertEqual({row['id'] for row in first.participant_snapshot}, {self.student.pk, self.partner.pk})
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(first.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse('assignments:center')), '待评分')
        second = self.submit()
        self.assertEqual(second.version_number, 2)
        self.assertEqual(second.author, self.partner)
        self.assertEqual(self.assignment.question.filter(current_slot=1).count(), 1)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(self.url('group_edit', course_id=self.course.pk, group_id=group.pk), {'name': '改组', 'members': [self.student.pk]}).status_code, 403)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(self.url('submit'), {'topic': '越组'}).status_code, 403)
        self.assertEqual(self.client.get(first.get_absolute_url()).status_code, 403)

    def test_group_grade_rubric_adjustments_and_export(self):
        self.group()
        self.assignment.rubric = [{'title': '代码', 'points': 60}, {'title': '报告', 'points': 40}]
        self.assignment.save()
        submission = self.submit()
        self.client.force_login(self.teacher)
        data = {'score_0': 55, 'score_1': 35, 'feedback': '整体良好', 'adjust_' + str(self.partner.pk): -8}
        response = self.client.post(self.url('grade', submission.pk), data)
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.grade, 90)
        self.assertEqual(next(row['final_grade'] for row in submission.participant_grades if row['id'] == self.partner.pk), 82)
        self.assertEqual(submission.grade_records.get().score_breakdown[0]['score'], 55)
        self.assertEqual(submission.grade_records.get().individual_adjustments[str(self.partner.pk)], -8)
        response = self.client.get(self.url('export', pk=self.assignment.pk, kind='grades'))
        content = response.content.decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(next(row['个人成绩'] for row in rows if row['用户名'] == self.partner.username), '82')
        self.client.force_login(self.partner)
        self.assertContains(self.client.get(submission.get_absolute_url()), '我的成绩：82 分')
        self.assertContains(self.client.get(reverse('assignments:feedback')), '成绩：82 分')

    def test_rubric_validation_and_configuration_freeze(self):
        self.client.force_login(self.teacher)
        data = {'assignment_name': '按项评分', 'assignment_description': 'x', 'course': self.course.pk,
                'due_date': (timezone.localtime() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
                'rubric_text': '代码 | 60\n报告 | 30', 'submission_mode': 'group'}
        response = self.client.post(reverse('assignments:create'), data)
        self.assertContains(response, '满分须合计 100')
        data['rubric_text'] = '代码 | 60\n报告 | 40'
        self.assertEqual(self.client.post(reverse('assignments:create'), data).status_code, 302)
        assignment = Assignment.objects.get(assignment_name='按项评分')
        self.assertEqual(assignment.rubric[0]['points'], 60)
        self.client.force_login(self.student)
        self.submit()
        self.client.force_login(self.teacher)
        data.update(assignment_name='改标题', submission_mode='group', required_materials=['code'], rubric_text='另一项 | 100')
        self.assertEqual(self.client.post(self.url('update'), data).status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.submission_mode, 'individual')
        self.assertEqual(self.assignment.rubric, [])
        self.assertEqual(self.assignment.required_materials, [])

    def test_workbench_filters_and_batch_download(self):
        submission = self.submit()
        self.client.force_login(self.teacher)
        response = self.client.get(self.assignment.get_absolute_url(), {'status': 'missing'})
        self.assertEqual(response.context['workbench_page'].paginator.count, 2)
        response = self.client.get(self.assignment.get_absolute_url(), {'q': self.student.username, 'status': 'pending'})
        self.assertEqual(response.context['workbench_page'].paginator.count, 1)
        response = self.client.get(self.url('export', pk=self.assignment.pk, kind='files'), {'q': self.student.username})
        data = b''.join(response.streaming_content)
        response.close()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read('submission-{}-v1/main.py'.format(submission.pk)), b'print(1)\n')

    def test_archive_and_leaving_preserve_group_history(self):
        self.group()
        submission = self.submit()
        Enrollment.objects.filter(course=self.course, student=self.partner).delete()
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(submission.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse('assignments:feedback')), '本次成果')
        self.assertEqual(self.client.post(self.url('submit'), {'topic': '退课提交'}).status_code, 403)
        self.client.force_login(self.student)
        response = self.client.post(self.url('submit'), {'topic': '新版', 'description': 'x', 'assignment_file': self.file()})
        self.assertEqual(response.status_code, 403)
        self.course.is_archived = True
        self.course.save()
        self.assertEqual(self.client.post(self.url('submit'), {'topic': '归档提交'}).status_code, 403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(self.url('groups', course_id=self.course.pk), {'name': '新增', 'members': [self.stranger.pk]}).status_code, 403)
        self.assertEqual(self.client.get(self.url('browse', submission.pk)).status_code, 200)

    def test_group_unique_current_constraint(self):
        group = self.group()
        self.submit()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SubmitAssignment.objects.create(group=group, author=self.partner, assignment_ques=self.assignment, topic='重复有效版本', description='x', assignment_file='x.py')

    def test_csv_formula_neutralization(self):
        from .experiments import csv_cell
        self.assertEqual(csv_cell('=SUM(A1)'), "'=SUM(A1)")
        self.assertEqual(csv_cell(' +1'), "' +1")
        self.assertEqual(csv_cell('正常'), '正常')

    def test_submission_payload_and_history_cannot_be_overwritten_or_deleted(self):
        first = self.submit()
        first.topic = '覆盖旧代码'
        with self.assertRaises(ValidationError):
            first.save()
        with self.assertRaises(ValidationError):
            SubmitAssignment.objects.filter(pk=first.pk).update(description='覆盖')
        with self.assertRaises(ValidationError):
            SubmitAssignment.objects.filter(pk=first.pk).delete()
        first.refresh_from_db()
        with self.assertRaises(ValidationError):
            first.delete()
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.assignment.delete()
        with self.assertRaises(ProtectedError):
            self.student.delete()
        self.assertTrue(SubmitAssignment.objects.filter(pk=first.pk).exists())

    def test_superseded_version_cannot_be_graded_and_adjustment_history_is_retained(self):
        self.group()
        first = self.submit()
        self.client.force_login(self.teacher)
        for grade, adjustment in [(80, -10), (90, 5)]:
            self.assertEqual(self.client.post(self.url('grade', first.pk), {'grade': grade, 'adjust_' + str(self.partner.pk): adjustment}).status_code, 302)
        first.refresh_from_db()
        records = list(first.grade_records.all())
        self.assertEqual(records[1].individual_adjustments[str(self.partner.pk)], -10)
        self.assertEqual(records[0].individual_adjustments[str(self.partner.pk)], 5)
        self.client.force_login(self.partner)
        second = self.submit()
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(self.url('grade', first.pk), {'grade': 100}).status_code, 403)
        first.refresh_from_db()
        self.assertEqual(first.grade, 90)
        self.assertFalse(second.graded)

    def test_archive_duplicate_and_entry_limits(self):
        stream = io.BytesIO()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(stream, 'w') as archive:
                archive.writestr('same.py', '1')
                archive.writestr('same.py', '2')
        stream.seek(0)
        with self.assertRaises(ValidationError):
            archive_entries(stream)
        with self.assertRaises(ValidationError):
            archive_entries(self.archive({'f{}.txt'.format(i): b'x' for i in range(1001)}))

import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from users.models import User
from courses.models import Course, Enrollment
from assignments.models import Assignment, SubmitAssignment
from resources.models import Resource


class WorkflowTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp(prefix='lms-tests-')
        self.addCleanup(shutil.rmtree, media)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.teacher = User.objects.create_user('teacher', password='test-password', user_type=2)
        self.other_teacher = User.objects.create_user('other-teacher', user_type=2)
        self.student = User.objects.create_user('student', password='test-password', user_type=1)
        self.outsider = User.objects.create_user('outsider', user_type=1)
        self.course = Course.objects.create(course_name='教学实验', course_description='说明', teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)
        self.assignment = Assignment.objects.create(
            assignment_name='实验一', assignment_description='要求', course=self.course,
            due_date=timezone.now() + timedelta(days=7))
        self.submission = SubmitAssignment.objects.create(
            topic='报告', description='内容', author=self.student, assignment_ques=self.assignment,
            assignment_file=self.file())
        self.resource = Resource.objects.create(resource_name='指南', course=self.course, resource_file=self.file())

    def file(self, name='report.txt', data=b'experiment report'):
        return SimpleUploadedFile(name, data, content_type='text/plain')

    def login(self, user):
        self.client.force_login(user)

    def test_home_login_and_role_pages(self):
        for url in ['/', '/users/login/', '/users/signup/', '/courses/all/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertTrue(self.client.login(username='teacher', password='test-password'))
        for url in ['/courses/new/', '/assignments/create/', '/resources/create/',
                    '/courses/detail/%s/' % self.course.pk, '/assignments/detail/%s/' % self.assignment.pk,
                    '/assignments/grade/%s/' % self.submission.pk]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_core_workflow(self):
        self.login(self.teacher)
        self.assertEqual(self.client.post('/courses/new/', {
            'course_name': '新课程', 'course_description': '完整流程'}).status_code, 302)
        course = Course.objects.get(course_name='新课程')
        self.assertEqual(self.client.post('/assignments/create/', {
            'assignment_name': '新作业', 'assignment_description': '测试', 'course': course.pk,
            'due_date': (timezone.localtime() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M')}).status_code, 302)
        assignment = Assignment.objects.get(assignment_name='新作业')
        self.login(self.student)
        self.assertEqual(self.client.post('/courses/enroll/%s/' % course.pk).status_code, 302)
        self.assertEqual(self.client.get(assignment.get_absolute_url()).status_code, 200)
        response = self.client.post(reverse('assignments:submit', args=[assignment.pk]), {
            'topic': '完整流程报告', 'description': '已完成', 'assignment_file': self.file(),
            'author': self.student.pk, 'assignment_ques': assignment.pk})
        self.assertEqual(response.status_code, 302)
        submission = SubmitAssignment.objects.get(assignment_ques=assignment)
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('assignments:grade', args=[submission.pk]), {'grade': 92}).status_code, 302)
        submission.refresh_from_db()
        self.assertTrue(submission.graded)
        self.assertEqual(submission.grade, 92)
        self.login(self.student)
        self.assertContains(self.client.get(submission.get_absolute_url()), '92')
        download = self.client.get(reverse('assignments:download', args=[submission.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), b'experiment report')
        download.close()

    def test_student_cannot_create_course_or_grade_or_delete_others(self):
        self.login(self.outsider)
        self.assertEqual(self.client.post('/courses/new/', {'course_name': '非法', 'course_description': 'x'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('assignments:grade', args=[self.submission.pk]), {'grade': 100}).status_code, 403)
        self.assertEqual(self.client.post(reverse('assignments:submit_delete', args=[self.submission.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('resources:delete', args=[self.resource.pk])).status_code, 403)
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.graded)
        self.assertTrue(Resource.objects.filter(pk=self.resource.pk).exists())

    def test_other_teacher_cannot_manage_course_work(self):
        self.login(self.other_teacher)
        for name in ['assignments:update', 'assignments:delete']:
            self.assertEqual(self.client.post(reverse(name, args=[self.assignment.pk])).status_code, 404)
        self.assertEqual(self.client.get(self.assignment.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.post(reverse('assignments:grade', args=[self.submission.pk]), {'grade': 100}).status_code, 403)

    def test_private_downloads_and_disabled_graphql(self):
        for user in [self.outsider, self.other_teacher]:
            self.login(user)
            self.assertEqual(self.client.get(self.submission.get_absolute_url()).status_code, 403)
            for name, pk in [('assignments:download', self.submission.pk), ('resources:download', self.resource.pk)]:
                self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get('/graphql/').status_code, 404)
        self.assertEqual(self.client.get('/assignments/media/' + self.submission.assignment_file.name).status_code, 404)
        self.assertEqual(self.client.get(reverse('assignments:download', args=[self.submission.pk])).status_code, 302)

    def test_submission_update_and_identity_are_bound_to_url(self):
        self.login(self.student)
        other = Assignment.objects.create(assignment_name='另一个作业', assignment_description='x', course=self.course, due_date=timezone.now() + timedelta(days=3))
        self.client.get(other.get_absolute_url())
        url = reverse('assignments:submit', args=[self.assignment.pk])
        self.assertEqual(self.client.post(url, {'topic': '新版', 'description': '更新', 'keep_existing': 'on', 'author': self.outsider.pk, 'assignment_ques': other.pk}).status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.topic, '报告')
        self.assertIsNone(self.submission.current_slot)
        self.assertEqual(SubmitAssignment.objects.get(assignment_ques=self.assignment, current_slot=1).topic, '新版')
        self.assertEqual(self.submission.author_id, self.student.pk)
        self.assertEqual(self.submission.assignment_ques_id, self.assignment.pk)
        self.assertEqual(SubmitAssignment.objects.filter(assignment_ques=self.assignment, author=self.student, current_slot=1).count(), 1)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_deadline_is_enforced_and_graded_version_is_preserved(self):
        self.login(self.student)
        url = reverse('assignments:submit', args=[self.assignment.pk])
        self.assignment.due_date = timezone.now() - timedelta(seconds=1)
        self.assignment.save()
        self.assertEqual(self.client.post(url, {'topic': '超时'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('assignments:submit_delete', args=[self.submission.pk])).status_code, 403)
        self.assignment.due_date = timezone.now() + timedelta(days=1)
        self.assignment.save()
        self.submission.grade_assignment(80)
        self.assertEqual(self.client.post(url, {'topic': '改分后内容', 'description': '继续完善', 'keep_existing': 'on'}).status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.topic, '报告')
        self.assertEqual(self.submission.grade, 80)
        self.assertTrue(self.submission.graded)

    def test_unenrolled_and_teacher_cannot_submit(self):
        for user in [self.outsider, self.teacher]:
            self.login(user)
            self.assertEqual(self.client.post(reverse('assignments:submit', args=[self.assignment.pk]), {'topic': 'x'}).status_code, 403)

    def test_file_validation_and_missing_file(self):
        self.login(self.student)
        url = reverse('assignments:submit', args=[self.assignment.pk])
        for name, data in [('payload.exe', b'<script>'), ('empty.txt', b''), ('large.txt', b'x' * (20 * 1024 * 1024 + 1))]:
            response = self.client.post(url, {'topic': '非法附件', 'description': 'x', 'assignment_file': self.file(name, data)})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.submission.assignment_file.storage.delete(self.submission.assignment_file.name)
        self.assertEqual(self.client.get(reverse('assignments:download', args=[self.submission.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('assignments:submit_delete', args=[self.submission.pk])).status_code, 302)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.withdrawn)
        self.assertIsNone(self.submission.current_slot)

    def test_assignment_edit_and_delete_preserve_submissions(self):
        self.login(self.teacher)
        url = reverse('assignments:update', args=[self.assignment.pk])
        self.assertEqual(self.client.post(url, {'assignment_name': '改名', 'assignment_description': '新要求', 'due_date': (timezone.localtime() + timedelta(days=2)).strftime('%Y-%m-%d %H:%M'), 'course': self.course.pk}).status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.assignment_name, '改名')
        self.assertEqual(Assignment.objects.count(), 1)
        self.assertEqual(self.client.post(reverse('assignments:delete', args=[self.assignment.pk])).status_code, 302)
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())

    def test_invalid_deadline_and_grade_validation(self):
        self.login(self.teacher)
        response = self.client.post('/assignments/create/', {'assignment_name': '过期', 'assignment_description': 'x', 'course': self.course.pk, 'due_date': '2020-01-01 12:00'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('due_date', response.context['form'].errors)
        for grade in [-1, 101, 'abc']:
            response = self.client.post(reverse('assignments:grade', args=[self.submission.pk]), {'grade': grade})
            self.assertEqual(response.status_code, 200)
            self.assertIn('grade', response.context['form'].errors)

    def test_grade_feedback_revision_history_and_roster(self):
        Enrollment.objects.create(course=self.course, student=self.outsider)
        self.login(self.teacher)
        response = self.client.get(self.assignment.get_absolute_url())
        self.assertEqual(response.context['missing_count'], 1)
        self.assertEqual(response.context['pending_count'], 1)
        self.assertEqual(response.context['graded_count'], 0)
        url = reverse('assignments:grade', args=[self.submission.pk])
        for grade, feedback in [(70, '需要补充实验分析'), (85, '复核后调整成绩')]:
            self.assertEqual(self.client.post(url, {'grade': grade, 'feedback': feedback}).status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grade, 85)
        self.assertEqual(self.submission.grade_records.count(), 2)
        self.assertIsNotNone(self.submission.graded_at)
        response = self.client.get(self.assignment.get_absolute_url())
        self.assertEqual(response.context['graded_count'], 1)
        self.assertEqual(response.context['pending_count'], 0)
        self.login(self.student)
        response = self.client.get(self.submission.get_absolute_url())
        self.assertContains(response, '复核后调整成绩')
        self.assertContains(response, '需要补充实验分析')
        self.assertContains(response, '85')
        self.assertEqual(self.client.post(url, {'grade': 100, 'feedback': '自行改分'}).status_code, 403)
        self.assertEqual(self.submission.grade_records.count(), 2)

    def test_course_edit_archive_restore_and_readonly(self):
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('courses:update', args=[self.course.pk]), {'course_name': '更新课程', 'course_description': '更新介绍'}).status_code, 302)
        self.course.refresh_from_db()
        self.assertEqual(self.course.course_name, '更新课程')
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, self.student.username)
        archive_url = reverse('courses:archive', args=[self.course.pk])
        self.assertEqual(self.client.get(archive_url).status_code, 405)
        self.assertEqual(self.client.post(archive_url, {'action': 'archive'}).status_code, 302)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_archived)
        self.assertEqual(self.client.post(reverse('assignments:grade', args=[self.submission.pk]), {'grade': 90}).status_code, 403)
        self.assertEqual(self.client.post(reverse('resources:delete', args=[self.resource.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('courses:update', args=[self.course.pk])).status_code, 404)
        response = self.client.post('/assignments/create/', {'assignment_name': '归档新增', 'assignment_description': 'x', 'course': self.course.pk, 'due_date': '2099-01-01 12:00'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('course', response.context['form'].errors)
        self.login(self.student)
        self.assertEqual(self.client.get(self.assignment.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.post(reverse('assignments:submit', args=[self.assignment.pk]), {'topic': 'x'}).status_code, 403)
        self.login(self.outsider)
        self.assertEqual(self.client.post(reverse('courses:enroll', args=[self.course.pk])).status_code, 403)
        self.login(self.teacher)
        self.assertEqual(self.client.post(archive_url, {'action': 'restore'}).status_code, 302)
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_archived)
        self.assertEqual(self.client.get(reverse('courses:update', args=[self.course.pk])).status_code, 200)

    def test_enrollment_post_only_and_history_after_leaving(self):
        self.login(self.student)
        enroll = reverse('courses:enroll', args=[self.course.pk])
        leave = reverse('courses:unenroll', args=[self.course.pk])
        self.assertEqual(self.client.get(leave).status_code, 405)
        self.assertEqual(self.client.get(enroll).status_code, 405)
        self.assertEqual(self.client.post(enroll).status_code, 302)
        self.assertEqual(Enrollment.objects.filter(course=self.course, student=self.student).count(), 1)
        self.assertEqual(self.client.post(leave).status_code, 302)
        self.assertEqual(self.client.get(self.assignment.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.get(self.submission.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse('profile', args=[self.student.pk])), '报告')
        self.assertEqual(self.client.post(reverse('assignments:submit', args=[self.assignment.pk]), {'topic': 'x'}).status_code, 403)
        self.login(self.teacher)
        response = self.client.get(self.assignment.get_absolute_url())
        self.assertEqual(len(response.context['former_submissions']), 1)
        self.assertEqual(response.context['missing_count'], 0)
        self.assertTrue(SubmitAssignment.objects.filter(pk=self.submission.pk).exists())

    def test_course_ownership_and_private_profile(self):
        self.login(self.other_teacher)
        self.assertEqual(self.client.post(reverse('courses:archive', args=[self.course.pk]), {'action': 'archive'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('courses:update', args=[self.course.pk]), {'course_name': '非法', 'course_description': 'x'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('profile', args=[self.student.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('courses:enroll', args=[self.course.pk])).status_code, 403)

    def test_csrf_required_for_mutations(self):
        from django.test import Client
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.student)
        self.assertEqual(browser.post(reverse('courses:unenroll', args=[self.course.pk])).status_code, 403)
        browser.force_login(self.teacher)
        self.assertEqual(browser.post(reverse('assignments:grade', args=[self.submission.pk]), {'grade': 100}).status_code, 403)

    def test_legacy_grade_is_preserved_on_first_revision(self):
        SubmitAssignment.objects.filter(pk=self.submission.pk).update(graded=True, grade=60)
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('assignments:grade', args=[self.submission.pk]), {'grade': 75, 'feedback': '复核'}).status_code, 302)
        self.assertEqual(set(self.submission.grade_records.values_list('grade', flat=True)), {60, 75})
        self.assertIsNone(self.submission.grade_records.get(grade=60).created_at)

    def test_resource_upload_download_delete_and_cross_course_validation(self):
        other_course = Course.objects.create(course_name='他人课程', course_description='x', teacher=self.other_teacher)
        self.login(self.teacher)
        response = self.client.post('/resources/create/', {'resource_name': '非法', 'course': other_course.pk, 'resource_file': self.file()})
        self.assertEqual(response.status_code, 200)
        self.assertIn('course', response.context['form'].errors)
        response = self.client.post('/resources/create/', {'resource_name': '新资料', 'course': self.course.pk, 'resource_file': self.file('guide.txt')})
        self.assertEqual(response.status_code, 302)
        resource = Resource.objects.get(resource_name='新资料')
        self.login(self.student)
        response = self.client.get(reverse('resources:download', args=[resource.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'experiment report')
        response.close()
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('resources:delete', args=[resource.pk])).status_code, 302)
        self.assertFalse(Resource.objects.filter(pk=resource.pk).exists())

    def test_historical_submission_is_readonly(self):
        history = SubmitAssignment.objects.create(author=self.student, assignment_ques=self.assignment,
            current_slot=None, topic='历史版本', description='x', assignment_file=self.file('history.txt'))
        self.login(self.student)
        self.assertContains(self.client.get(history.get_absolute_url()), '历史版本')
        self.assertEqual(self.client.post(reverse('assignments:submit_delete', args=[history.pk])).status_code, 403)
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('assignments:grade', args=[history.pk]), {'grade': 100}).status_code, 403)

from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from assignments.models import Assignment, SubmitAssignment
from courses.models import Course, Enrollment
from users.models import User


class CenterTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('center_teacher', user_type=2)
        self.student = User.objects.create_user('center_student', user_type=1)
        self.other = User.objects.create_user('center_other', user_type=2)
        self.course = Course.objects.create(course_name='我的课程', course_description='x', teacher=self.teacher)
        self.private = Course.objects.create(course_name='他人课程', course_description='x', teacher=self.other)
        Enrollment.objects.create(course=self.course, student=self.student)
        self.open = Assignment.objects.create(course=self.course, assignment_name='待交报告', assignment_description='x', due_date=timezone.now() + timedelta(days=1))
        self.expired = Assignment.objects.create(course=self.course, assignment_name='过期报告', assignment_description='x', due_date=timezone.now() - timedelta(days=1))
        self.hidden = Assignment.objects.create(course=self.private, assignment_name='私有报告', assignment_description='x', due_date=timezone.now() + timedelta(days=1))

    def submit(self, assignment=None, **kwargs):
        return SubmitAssignment.objects.create(author=self.student, assignment_ques=assignment or self.open,
            topic='实验报告', description='x', assignment_file='demo.txt', **kwargs)

    def test_student_assignment_status_and_scoping(self):
        self.client.force_login(self.student)
        url = reverse('assignments:center')
        response = self.client.get(url, {'status': 'todo'})
        self.assertContains(response, '待交报告')
        self.assertNotContains(response, '过期报告')
        self.assertNotContains(response, '私有报告')
        self.assertContains(self.client.get(url, {'status': 'missed'}), '过期报告')
        self.submit()
        self.assertNotContains(self.client.get(url, {'status': 'todo'}), '待交报告')
        self.assertContains(self.client.get(url, {'status': 'pending'}), '待交报告')
        self.assertContains(self.client.get(url, {'status': 'pending'}), '更新提交')

    def test_teacher_pending_and_foreign_course_filter(self):
        self.submit()
        self.client.force_login(self.teacher)
        url = reverse('assignments:center')
        response = self.client.get(url, {'status': 'pending'})
        self.assertContains(response, '待交报告')
        self.assertNotContains(response, '过期报告')
        self.assertNotContains(response, '私有报告')
        self.assertEqual(self.client.get(url, {'course': self.private.pk}).context['page_obj'].paginator.count, 0)
        self.assertEqual(self.client.get(url, {'course': 'bad'}).status_code, 200)

    def test_archive_and_pagination(self):
        self.client.force_login(self.student)
        self.course.is_archived = True
        self.course.save()
        response = self.client.get(reverse('assignments:center'), {'status': 'archived'})
        self.assertContains(response, '已归档未交')
        self.assertNotContains(response, 'href="/assignments/submit/')
        self.assertEqual(self.client.get(reverse('assignments:center'), {'status': 'todo'}).context['page_obj'].paginator.count, 0)
        for number in range(13):
            Assignment.objects.create(course=self.course, assignment_name='分页%s' % number, assignment_description='x', due_date=self.open.due_date)
        response = self.client.get(reverse('assignments:center'), {'page': 2})
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(len(response.context['page_obj']), 3)

    def test_center_requires_login(self):
        self.assertEqual(self.client.get(reverse('assignments:center')).status_code, 302)
        self.assertEqual(self.client.get(reverse('assignments:feedback')).status_code, 302)

    def test_feedback_remains_after_leaving_and_zero_grade(self):
        submission = self.submit(graded=True, grade=0, feedback='请补充分析')
        Enrollment.objects.filter(student=self.student).delete()
        self.client.force_login(self.student)
        url = reverse('assignments:feedback')
        response = self.client.get(url, {'status': 'graded', 'course': self.course.pk})
        self.assertContains(response, '成绩：0 分')
        self.assertContains(response, '请补充分析')
        self.assertContains(response, reverse('assignments:submit_detail', args=[submission.pk]))
        self.assertEqual(self.client.get(reverse('assignments:center')).context['page_obj'].paginator.count, 0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url, {'course': self.course.pk}).context['page_obj'].paginator.count, 0)

    def test_feedback_separates_current_and_historical_versions(self):
        self.submit()
        self.submit(current_slot=None, graded=True, grade=50)
        self.client.force_login(self.student)
        url = reverse('assignments:feedback')
        self.assertEqual(self.client.get(url, {'status': 'history'}).context['page_obj'].paginator.count, 1)
        self.assertEqual(self.client.get(url, {'status': 'pending'}).context['page_obj'].paginator.count, 1)
        self.assertEqual(self.client.get(url, {'status': 'graded'}).context['page_obj'].paginator.count, 0)
        self.client.force_login(self.teacher)
        self.course.is_archived = True
        self.course.save()
        response = self.client.get(url)
        self.assertContains(response, '课程已归档')
        self.assertNotContains(response, 'href="/assignments/grade/')

    def test_student_never_sees_other_students_feedback(self):
        self.submit()
        stranger = User.objects.create_user('another_student', user_type=1)
        Enrollment.objects.create(student=stranger, course=self.course)
        SubmitAssignment.objects.create(author=stranger, assignment_ques=self.open, topic='别人的报告', description='秘密说明', feedback='秘密评语', graded=True, assignment_file='other.txt')
        self.client.force_login(self.student)
        response = self.client.get(reverse('assignments:feedback'))
        self.assertNotContains(response, '别人的报告')
        self.assertNotContains(response, '秘密评语')

    def test_home_cards_and_personal_page_have_working_entries(self):
        response = self.client.get('/')
        self.assertContains(response, reverse('assignments:center'))
        self.assertContains(response, reverse('assignments:feedback'))
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('profile', args=[self.teacher.pk]))
        self.assertContains(response, '查看作业与批改进度')
        for route in ['assignments:center', 'assignments:feedback']:
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)

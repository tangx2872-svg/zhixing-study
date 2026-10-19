from django.test import TestCase
from django.urls import reverse
from html.parser import HTMLParser

from courses.models import Course
from users.models import User


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = {}
        self.href = None
        self.label = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.label = ''

    def handle_data(self, data):
        if self.href is not None:
            self.label += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            self.links.setdefault(self.label.strip(), []).append(self.href)
            self.href = None


class TeacherCreationNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(username='navigation_teacher', user_type=2)
        cls.course = Course.objects.create(
            course_name='Navigation course', course_description='Test course',
            teacher=cls.teacher,
        )

    def setUp(self):
        self.client.force_login(self.teacher)

    def test_teacher_links_open_distinct_creation_forms(self):
        response = self.client.get(reverse('courses:detail', args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        parser = LinkParser()
        parser.feed(response.content.decode())
        for label, route, template, field in (
            ('发布作业', 'assignments:create', 'assignments/create_assignment_form.html', 'assignment_name'),
            ('上传学习资料', 'resources:create', 'resources/create_resource_form.html', 'resource_file'),
        ):
            with self.subTest(label=label):
                # Both the sidebar and the course action must point to the right form.
                self.assertEqual(parser.links[label], [reverse(route), reverse(route) + '?course={}'.format(self.course.pk)])
                course_page = self.client.get(parser.links[label][1])
                self.assertEqual(course_page.context['form'].initial['course'], self.course.pk)
                page = self.client.get(parser.links[label][0])
                self.assertEqual(page.status_code, 200)
                self.assertTemplateUsed(page, template)
                self.assertContains(page, 'name="{}"'.format(field))
                self.assertContains(page, 'action="{}"'.format(reverse(route)))

    def test_creation_pages_require_login(self):
        self.client.logout()
        for route in ('assignments:create', 'resources:create'):
            with self.subTest(route=route):
                self.assertRedirects(
                    self.client.get(reverse(route)),
                    '{}?next={}'.format(reverse('users:login'), reverse(route)),
                )

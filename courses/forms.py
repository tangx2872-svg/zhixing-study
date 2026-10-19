from django.forms import ModelForm

from courses.models import Course


class CreateCourseForm(ModelForm):
    class Meta:
        model = Course
        fields = ('course_name', 'course_description')
        labels = {
            'course_name': '课程名称',
            'course_description': '课程简介',
        }

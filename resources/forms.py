from django_lms.files import validate_upload
from django.forms import ModelForm, DateInput, TimeInput, Form
from django import forms
from django.shortcuts import get_object_or_404
from resources.models import Resource
from django.utils import timezone
from courses.models import Course
from users.models import User


class CreateResourceForm(ModelForm):
    class Meta:
        model = Resource
        fields = ('resource_name', 'resource_file', 'course')
        labels = {
            'resource_name': '资料名称',
            'resource_file': '资料文件',
            'course': '所属课程',
        }


    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        user_object = User.objects.filter(username=user.username)
        new_user_object = get_object_or_404(user_object)
        self.fields['course'].queryset = self.fields['course'].queryset.filter(teacher=new_user_object.id, is_archived=False)

    def clean_resource_file(self):
        return validate_upload(self.cleaned_data['resource_file'])

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django import forms
from django.conf import settings

class UserCreateForm(UserCreationForm):

    class Meta:
        fields = ('username', 'last_name', 'first_name', 'email', 'password1', 'password2', 'user_type')
        model = get_user_model()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = '用户名'
        self.fields['first_name'].label = '名'
        self.fields['last_name'].label = '姓'
        self.fields['email'].label = '电子邮箱'
        self.fields['password1'].label = '密码'
        self.fields['password2'].label = '确认密码'
        self.fields['user_type'].label = '注册身份'
        self.fields['user_type'].choices = [(1, '学生'), (2, '教师')]

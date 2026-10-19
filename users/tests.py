from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.test import RequestFactory, TestCase
from django.urls import reverse

User = get_user_model()


class AdminUserPasswordTests(TestCase):
    """BUG-001 回归测试：后台创建/编辑用户时的密码必须走 Django 标准哈希机制。"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin-tester',
            email='admin-tester@example.com',
            password='admin-pass-123',
        )
        self.client.force_login(self.superuser)

    def _admin(self):
        return admin.site._registry[User]

    @staticmethod
    def _form_errors(response):
        """表单校验失败时把错误带进断言信息，便于定位。"""
        if response.status_code == 200 and response.context is not None:
            adminform = response.context.get('adminform')
            if adminform is not None:
                return adminform.form.errors
        return None

    def test_admin_add_user_hashes_password(self):
        """后台新建用户：密码必须被哈希，check_password 必须通过。"""
        response = self.client.post(
            reverse('admin:users_user_add'),
            {
                'username': 'new-student',
                'password1': 'test-password',
                'password2': 'test-password',
                'user_type': 1,
            },
        )
        self.assertEqual(response.status_code, 302, self._form_errors(response))

        user = User.objects.get(username='new-student')
        self.assertTrue(user.check_password('test-password'))
        self.assertNotEqual(user.password, 'test-password')

    def _change_post_data(self, user, **overrides):
        """构造后台编辑表单的提交数据（date_joined 为必填的拆分日期控件）。"""
        request = RequestFactory().get('/')
        request.user = self.superuser
        form = self._admin().get_form(request, obj=user)(instance=user)
        widget = form.fields['date_joined'].widget

        data = {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'user_type': user.user_type,
            'is_active': 'on',
            'date_joined_0': widget.widgets[0].format_value(user.date_joined),
            'date_joined_1': widget.widgets[1].format_value(user.date_joined),
        }
        data.update(overrides)
        return data

    def test_admin_edit_name_keeps_existing_password(self):
        """后台只改姓名/邮箱等普通字段：原密码必须依然可用。"""
        user = User.objects.create_user(
            username='edit-me',
            email='edit-me@example.com',
            password='test-password',
            first_name='旧名',
            last_name='旧姓',
        )

        response = self.client.post(
            reverse('admin:users_user_change', args=[user.pk]),
            self._change_post_data(
                user,
                first_name='新名',
                last_name='新姓',
                email='changed@example.com',
            ),
        )
        self.assertEqual(response.status_code, 302, self._form_errors(response))

        user.refresh_from_db()
        self.assertEqual(user.first_name, '新名')
        self.assertEqual(user.email, 'changed@example.com')
        self.assertTrue(user.check_password('test-password'))

    def test_admin_change_form_password_is_readonly_hash(self):
        """后台编辑页的 password 字段必须是只读哈希，而不是普通文本输入框。"""
        user = User.objects.create_user(username='readonly-me', password='test-password')
        request = RequestFactory().get('/admin/users/user/{}/change/'.format(user.pk))
        request.user = self.superuser

        form = self._admin().get_form(request, obj=user)
        self.assertIsInstance(form.base_fields['password'], ReadOnlyPasswordHashField)

    def test_admin_password_change_view_uses_standard_hashing(self):
        """管理员通过标准改密流程设置的密码必须可登录。"""
        user = User.objects.create_user(username='reset-me', password='old-password')

        response = self.client.post(
            reverse('admin:auth_user_password_change', args=[user.pk]),
            {'password1': 'new-password-456', 'password2': 'new-password-456'},
        )
        self.assertEqual(response.status_code, 302, self._form_errors(response))

        user.refresh_from_db()
        self.assertTrue(user.check_password('new-password-456'))
        self.assertFalse(user.check_password('old-password'))

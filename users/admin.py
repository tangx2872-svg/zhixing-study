from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from users.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """users.User 是 AbstractUser 的子类，直接复用 Django 标准 UserAdmin。

    标准 UserAdmin 已经提供正确的密码处理：
    - 新建用户走 UserCreationForm，密码经 set_password 哈希；
    - 编辑用户时 password 是只读的密码哈希，不会被普通文本覆盖；
    - 改密走独立的 user_change_password 视图，同样使用 set_password。

    这里只补充项目自定义的 user_type 字段，避免换成 UserAdmin 后该字段无法编辑。
    """

    fieldsets = DjangoUserAdmin.fieldsets + (
        ('教学身份', {'fields': ('user_type',)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('教学身份', {'fields': ('user_type',)}),
    )

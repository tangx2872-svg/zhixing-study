from django.db import models
from django.contrib import auth

# Create your models here.
class User(auth.models.AbstractUser):
    USER_TYPE_CHOICES = (
        (1, 'Student'),
        (2, 'Teacher')
    )

    user_type = models.PositiveIntegerField(choices=USER_TYPE_CHOICES, default=1)

    def __str__(self):
        return self.get_full_name() or self.username

    def get_full_name(self):
        return '{}{}'.format(self.last_name.strip(), self.first_name.strip())

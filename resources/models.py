from django.db import models
from users.models import User
from courses.models import Course
from django.urls import reverse
from django.utils import timezone
import os
from django.conf import settings

# Create your models here.
class Resource(models.Model):
    resource_name = models.CharField(max_length=200, blank=False)
    resource_file = models.FileField(blank=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    workspace = models.ForeignKey('research.ResearchWorkspace', on_delete=models.PROTECT, null=True, blank=True, related_name='resources')

    def save(self, *args, **kwargs):
        if self.pk and Resource.objects.filter(pk=self.pk, workspace__isnull=False).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError('科研附件不可覆盖，请上传新版本。')
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [models.CheckConstraint(
            check=(models.Q(course__isnull=False, workspace__isnull=True) | models.Q(course__isnull=True, workspace__isnull=False)),
            name='resource_single_scope')]

    def __str__(self):
        return self.resource_name

    def get_absolute_url(self):
        return reverse('courses:list')

from django.db.models.signals import post_delete
from django.dispatch import receiver
from django_lms.files import remove_unreferenced_file


@receiver(post_delete, sender=Resource)
def cleanup_attachment(sender, instance, **kwargs):
    field = instance.resource_file
    remove_unreferenced_file(field.storage, field.name)

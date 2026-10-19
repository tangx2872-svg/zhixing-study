from django.db import models
from users.models import User
from courses.models import Course
from django.urls import reverse
from django.utils import timezone
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError


SNAPSHOT_FIELDS = {'author_id', 'author', 'assignment_ques_id', 'assignment_ques', 'group_id', 'group',
                   'topic', 'description', 'assignment_file', 'submitted_date', 'updated_at',
                   'version_number', 'participant_snapshot', 'rubric_snapshot'}


class SubmissionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if SNAPSHOT_FIELDS.intersection(kwargs):
            raise ValidationError('实验提交内容不能覆盖，请追加新版本。')
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError('实验历史不能删除，请撤回当前有效提交。')

    def bulk_update(self, objs, fields, batch_size=None):
        if SNAPSHOT_FIELDS.intersection(fields):
            raise ValidationError('实验提交内容不能覆盖。')
        return super().bulk_update(objs, fields, batch_size=batch_size)

# Create your models here.
class Assignment(models.Model):
    assignment_name = models.CharField(max_length=200, blank=False)
    assignment_description = models.TextField(blank=False)
    start_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateTimeField()
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    submission_mode = models.CharField('提交方式', max_length=12, default='individual', choices=[('individual', '个人实验'), ('group', '小组实验')])
    required_materials = models.JSONField(default=list, blank=True)
    rubric = models.JSONField(default=list, blank=True)

    @property
    def is_open(self):
        now = timezone.now()
        return not self.course.is_archived and self.start_date <= now < self.due_date

    @property
    def status_label(self):
        if self.course.is_archived:
            return '课程已归档'
        if timezone.now() < self.start_date:
            return '未开始'
        return '进行中' if self.is_open else '已截止'

    def __str__(self):
        return self.assignment_name

    def get_absolute_url(self):
        return reverse('assignments:detail', kwargs={'pk': self.pk})

class SubmitAssignment(models.Model):
    objects = SubmissionQuerySet.as_manager()
    author = models.ForeignKey(User, related_name='assignment', on_delete=models.PROTECT)
    topic = models.CharField(max_length=200, blank=False)
    description = models.TextField(blank=False)
    assignment_file = models.FileField(blank=False, upload_to='assignments')
    submitted_date = models.DateTimeField(default=timezone.now)
    assignment_ques = models.ForeignKey(Assignment, related_name="question", on_delete=models.PROTECT, null=True)
    # NULL marks a retained historical version; slot 1 is the effective submission.
    current_slot = models.PositiveSmallIntegerField(default=1, null=True, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)
    graded = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    group = models.ForeignKey('CourseGroup', null=True, blank=True, on_delete=models.PROTECT, related_name='submissions')
    version_number = models.PositiveIntegerField(default=1)
    participant_snapshot = models.JSONField(default=list, blank=True)
    rubric_snapshot = models.JSONField(default=list, blank=True)
    score_breakdown = models.JSONField(default=list, blank=True)
    individual_adjustments = models.JSONField(default=dict, blank=True)
    withdrawn = models.BooleanField(default=False)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    grade = models.IntegerField(
        default=0,
        validators=[
            MaxValueValidator(100),
            MinValueValidator(0)
        ]
    )

    def __str__(self):
        return self.topic

    def save(self, *args, **kwargs):
        if not self._state.adding:
            persisted = type(self).objects.get(pk=self.pk)
            for field in SNAPSHOT_FIELDS - {'author', 'assignment_ques', 'group'}:
                if getattr(self, field) != getattr(persisted, field):
                    raise ValidationError('实验提交内容不能覆盖，请追加新版本。')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('实验历史不能删除，请撤回当前有效提交。')

    def grade_assignment(self, grade, feedback='', grader=None, breakdown=None, adjustments=None):
        if self.current_slot != 1:
            raise ValidationError('历史版本不能重新评分。')
        if self.graded and not self.grade_records.exists():
            GradeRecord.objects.create(submission=self, grade=self.grade, feedback=self.feedback, created_at=self.graded_at, score_breakdown=self.score_breakdown, individual_adjustments=self.individual_adjustments)
        self.grade = grade
        self.graded = True
        self.feedback = feedback
        self.graded_at = timezone.now()
        self.score_breakdown = breakdown or []
        self.individual_adjustments = adjustments or {}
        self.save()
        if grader is not None:
            GradeRecord.objects.create(submission=self, grader=grader, grade=grade, feedback=feedback, score_breakdown=self.score_breakdown, individual_adjustments=self.individual_adjustments)

    @property
    def owner_label(self):
        return self.group.name if self.group_id else str(self.author)

    @property
    def participant_grades(self):
        return [dict(member, adjustment=self.individual_adjustments.get(str(member['id']), 0),
                     final_grade=max(0, min(100, self.grade + self.individual_adjustments.get(str(member['id']), 0))))
                for member in self.participant_snapshot]

    def get_absolute_url(self):
        return reverse('assignments:submit_detail', kwargs={'pk': self.pk})

    class Meta:
        constraints = [models.UniqueConstraint(fields=['author', 'assignment_ques', 'current_slot'], name='unique_current_submission'),
                       models.UniqueConstraint(fields=['group', 'assignment_ques', 'current_slot'], name='unique_current_group_submission')]


from django.db.models.signals import post_delete
from django.dispatch import receiver
from django_lms.files import remove_unreferenced_file


@receiver(post_delete, sender=SubmitAssignment)
def cleanup_attachment(sender, instance, **kwargs):
    field = instance.assignment_file
    remove_unreferenced_file(field.storage, field.name)


class GradeRecord(models.Model):
    submission = models.ForeignKey(SubmitAssignment, related_name='grade_records', on_delete=models.CASCADE)
    grader = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    grade = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, null=True, blank=True)
    score_breakdown = models.JSONField(default=list, blank=True)
    individual_adjustments = models.JSONField(default=dict, blank=True)

    @property
    def participant_grades(self):
        return [dict(member, adjustment=self.individual_adjustments.get(str(member['id']), 0),
                     final_grade=max(0, min(100, self.grade + self.individual_adjustments.get(str(member['id']), 0))))
                for member in self.submission.participant_snapshot]

    class Meta:
        ordering = ['-created_at', '-pk']


class CourseGroup(models.Model):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='experiment_groups')
    name = models.CharField('小组名称', max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'pk']
        constraints = [models.UniqueConstraint(fields=['course', 'name'], name='unique_course_group_name')]

    def __str__(self):
        return self.name


class GroupMember(models.Model):
    group = models.ForeignKey(CourseGroup, on_delete=models.CASCADE, related_name='memberships')
    course = models.ForeignKey(Course, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='experiment_memberships')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['course', 'user'], name='one_experiment_group_per_course')]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.group_id and self.group.course_id != self.course_id:
            raise ValidationError('小组和成员必须属于同一课程。')
        if self.user_id and not self.course.students.filter(pk=self.user_id).exists():
            raise ValidationError('小组成员必须是本课程学生。')


class SubmissionAttachment(models.Model):
    CATEGORY = [('code', '源码'), ('report', '实验报告'), ('screenshots', '运行截图'), ('test_report', '测试报告')]
    submission = models.ForeignKey(SubmitAssignment, on_delete=models.PROTECT, related_name='attachments')
    file = models.FileField(upload_to='experiments')
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=16, choices=CATEGORY)
    size = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('历史附件不能覆盖。')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('历史附件不能删除。')

    class Meta:
        ordering = ['category', 'name', 'pk']
        constraints = [models.UniqueConstraint(fields=['submission', 'name'], name='unique_submission_attachment_name')]

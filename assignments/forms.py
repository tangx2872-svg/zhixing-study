from django import forms
from django.utils import timezone
from assignments.models import SubmitAssignment, Assignment
from courses.models import Course


class GradeAssignmentForm(forms.ModelForm):
    class Meta:
        model = SubmitAssignment
        fields = ['grade', 'feedback']
        labels = {'grade': '成绩', 'feedback': '批改评语'}
        help_texts = {'grade': '请输入 0 至 100 之间的整数。'}


class CreateAssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ('assignment_name', 'assignment_description', 'due_date', 'course')
        labels = {'assignment_name': '作业名称', 'assignment_description': '作业要求', 'due_date': '截止时间（北京时间）', 'course': '所属课程'}
        widgets = {'due_date': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['course'].queryset = Course.objects.filter(teacher=user, is_archived=False)
        if self.instance.pk:
            self.fields['course'].disabled = True

    def clean_due_date(self):
        value = self.cleaned_data['due_date']
        if value <= timezone.now():
            if not self.instance.pk or value.replace(second=0, microsecond=0) != self.instance.due_date.replace(second=0, microsecond=0):
                raise forms.ValidationError('新的截止时间必须晚于当前时间。')
        if value <= self.instance.start_date:
            raise forms.ValidationError('截止时间必须晚于发布时间。')
        return value

from pathlib import Path
from django import forms
from .forms import CreateAssignmentForm as BaseAssignmentForm, GradeAssignmentForm as BaseGradeForm
from .models import SubmitAssignment, SubmissionAttachment, CourseGroup, GroupMember
from .code_review import CODE_EXTENSIONS, TEXT_NAMES, archive_entries


class GradeAssignmentForm(BaseGradeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rubric = self.instance.rubric_snapshot
        if rubric:
            self.fields['grade'].widget = forms.HiddenInput()
            self.fields['grade'].disabled = True
            self.fields['grade'].required = False
        for index, item in enumerate(rubric):
            self.fields['score_{}'.format(index)] = forms.IntegerField(label='{}（满分 {}）'.format(item['title'], item['points']),
                min_value=0, max_value=item['points'], initial=next((row['score'] for row in self.instance.score_breakdown if row.get('title') == item['title']), None))
        if self.instance.group_id:
            for member in self.instance.participant_snapshot:
                key = str(member['id'])
                self.fields['adjust_' + key] = forms.IntegerField(label='{}（{}）个人调整分'.format(member['name'], member['username']),
                    min_value=-100, max_value=100, required=False, initial=self.instance.individual_adjustments.get(key, 0),
                    help_text='在小组分基础上加减；个人最终成绩限定为 0～100 分。')

    def clean(self):
        cleaned = super().clean()
        rubric = self.instance.rubric_snapshot
        cleaned['breakdown'] = [dict(item, score=cleaned.get('score_{}'.format(index), 0)) for index, item in enumerate(rubric)]
        if rubric:
            cleaned['grade'] = sum(item['score'] for item in cleaned['breakdown'])
            self.instance.grade = cleaned['grade']
        cleaned['adjustments'] = {str(member['id']): cleaned.get('adjust_' + str(member['id'])) or 0
                                  for member in self.instance.participant_snapshot} if self.instance.group_id else {}
        return cleaned


class CreateAssignmentForm(BaseAssignmentForm):
    required_materials = forms.MultipleChoiceField(label='必交材料', choices=SubmissionAttachment.CATEGORY, required=False,
                                                  widget=forms.CheckboxSelectMultiple)
    rubric_text = forms.CharField(label='评分项', required=False, widget=forms.Textarea(attrs={'rows': 4}),
        help_text='每行填写“评分项 | 满分”，例如：代码正确性 | 40。各项满分须合计 100；留空则直接填写总成绩。')

    class Meta(BaseAssignmentForm.Meta):
        fields = BaseAssignmentForm.Meta.fields + ('submission_mode', 'required_materials')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['submission_mode'].required = False
        self.initial['rubric_text'] = '\n'.join('{} | {}'.format(item['title'], item['points']) for item in self.instance.rubric)
        if self.instance.pk and self.instance.question.exists():
            for name in ('submission_mode', 'required_materials', 'rubric_text'):
                self.fields[name].disabled = True
                self.fields[name].help_text = '已有提交，为保持历史一致不能更改；需要调整请发布新实验。'

    def clean_submission_mode(self):
        return self.cleaned_data.get('submission_mode') or 'individual'

    def clean_rubric_text(self):
        text, rubric = self.cleaned_data.get('rubric_text', ''), []
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = line.rsplit('|', 1)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip().isdigit():
                raise forms.ValidationError('评分项格式应为：代码正确性 | 40')
            title, points = parts[0].strip(), int(parts[1].strip())
            if len(title) > 80 or not 1 <= points <= 100 or any(item['title'] == title for item in rubric):
                raise forms.ValidationError('评分项名称须唯一且不超过 80 字，满分须为 1～100。')
            rubric.append({'title': title, 'points': points})
        if len(rubric) > 20 or (rubric and sum(item['points'] for item in rubric) != 100):
            raise forms.ValidationError('评分项最多 20 项，满分须合计 100。')
        self.instance.rubric = rubric
        return text


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        super().__init__(dict(attrs or {}, multiple=True))

    def value_from_datadict(self, data, files, name):
        return files.getlist(name)


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []
        return [super(MultipleFileField, self).clean(item, initial) for item in data]


def validate_experiment_upload(file, category=None):
    from django_lms.files import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE
    suffix = Path(file.name).suffix.lower()
    if not file.size or file.size > MAX_UPLOAD_SIZE:
        raise forms.ValidationError('附件不能为空，单个文件最多 20 MB。')
    if suffix not in ALLOWED_EXTENSIONS | CODE_EXTENSIONS | {'.log', '.rst'} and Path(file.name).name not in TEXT_NAMES:
        raise forms.ValidationError('不支持此文件类型；项目源码可打包成 ZIP。')
    if category == 'code' and suffix != '.zip' and suffix not in CODE_EXTENSIONS and Path(file.name).name not in TEXT_NAMES:
        raise forms.ValidationError('源码栏请上传 ZIP 或代码文件。')
    if category == 'screenshots' and suffix not in {'.png', '.jpg', '.jpeg'}:
        raise forms.ValidationError('运行截图请使用 PNG 或 JPG。')
    if category in {'report', 'test_report'} and suffix not in {'.pdf', '.txt', '.md', '.csv', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.html', '.xml', '.json', '.log'}:
        raise forms.ValidationError('报告栏请上传文档或文本报告。')
    if suffix == '.zip':
        archive_entries(file)


class SubmitAssignmentForm(forms.Form):
    topic = forms.CharField(label='提交标题', max_length=200)
    description = forms.CharField(label='本次完成内容与修改说明', widget=forms.Textarea(attrs={'rows': 4}))
    keep_existing = forms.BooleanField(label='保留上一版附件（同名新文件替换对应附件）', required=False, initial=True)
    assignment_file = forms.FileField(label='其他附件', required=False, widget=forms.FileInput,
        help_text='单个附件最多 20 MB；一次最多 20 个附件、合计 50 MB。')

    def __init__(self, *args, **kwargs):
        self.previous = kwargs.pop('previous', None)
        super().__init__(*args, **kwargs)
        for key, label in SubmissionAttachment.CATEGORY:
            self.fields[key + '_files'] = MultipleFileField(label=label, required=False, widget=MultipleFileInput)
        self.fields['code_files'].help_text = '支持 ZIP 项目及 Java、Python、HTML、XML 等源码；打包时请排除 .git、虚拟环境、依赖目录和构建产物。'
        if self.previous:
            self.initial.update(topic=self.previous.topic, description='', keep_existing=True)
        else:
            self.fields.pop('keep_existing')

    def clean(self):
        from .submission_service import infer_category
        cleaned, uploads = super().clean(), []
        if cleaned.get('assignment_file'):
            uploads.append((cleaned['assignment_file'], infer_category(cleaned['assignment_file'].name)))
        for key, label in SubmissionAttachment.CATEGORY:
            uploads.extend((file, key) for file in cleaned.get(key + '_files', []))
        if len(uploads) > 20 or sum(file.size for file, _ in uploads) > 50 * 1024 * 1024:
            raise forms.ValidationError('每次最多上传 20 个附件，合计不超过 50 MB。')
        names = set()
        for file, category in uploads:
            name = Path(file.name).name
            if len(name) > 200 or name in names:
                raise forms.ValidationError('附件名称须唯一且不超过 200 字。')
            names.add(name)
            try:
                validate_experiment_upload(file, category)
            except forms.ValidationError as exc:
                self.add_error('assignment_file' if file is cleaned.get('assignment_file') else category + '_files', exc)
        cleaned['uploads'] = uploads
        if not uploads and not (self.previous and cleaned.get('keep_existing')):
            self.add_error('assignment_file', '请上传附件，或选择保留上一版附件。')
        return cleaned


class CourseGroupForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(label='小组成员', queryset=None, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = CourseGroup
        fields = ['name']

    def __init__(self, *args, **kwargs):
        self.course = kwargs.pop('course')
        super().__init__(*args, **kwargs)
        occupied = GroupMember.objects.filter(course=self.course)
        if self.instance.pk:
            occupied = occupied.exclude(group=self.instance)
        self.fields['members'].queryset = self.course.students.exclude(pk__in=occupied.values('user_id')).order_by('username')
        if self.instance.pk:
            self.initial['members'] = list(self.instance.memberships.values_list('user_id', flat=True))

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if CourseGroup.objects.filter(course=self.course, name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('本课程已有同名小组。')
        return name

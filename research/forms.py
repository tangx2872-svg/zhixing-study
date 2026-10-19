from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import ResearchWorkspace, WorkspaceMember, ResearchTask, ProgressCommit, LogicalFile, FileVersion
from django_lms.files import validate_upload
from .models import CommitComment


class CommentForm(forms.ModelForm):
    class Meta:
        model = CommitComment
        fields = ['content']
        widgets = {'content': forms.Textarea(attrs={'rows': 3})}

    def clean_content(self):
        content = self.cleaned_data['content'].strip()
        if not content or len(content) > 4000:
            raise forms.ValidationError('请填写 1 至 4000 字的评论。')
        return content


class WorkspaceForm(forms.ModelForm):
    class Meta:
        model = ResearchWorkspace
        fields = ['name', 'description', 'status']


class MemberForm(forms.Form):
    username = forms.CharField(label='成员用户名', max_length=150, help_text='输入已注册的同门账号。')
    role = forms.ChoiceField(label='项目角色', choices=WorkspaceMember.ROLE)

    def clean_username(self):
        username = self.cleaned_data['username']
        try:
            self.member_user = get_user_model().objects.get(username=username, is_active=True)
        except get_user_model().DoesNotExist:
            raise forms.ValidationError('找不到此账号，请先让同门注册。')
        return username


class TaskForm(forms.ModelForm):
    class Meta:
        model = ResearchTask
        fields = ['title', 'description', 'assignee', 'progress']
        labels = {'assignee': '任务负责人'}

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.workspace = workspace
        self.fields['assignee'].queryset = get_user_model().objects.filter(
            Q(pk=workspace.owner_id) | Q(pk__in=workspace.memberships.filter(role='member').values('user_id'))).order_by('username')


class MultipleFileInput(forms.FileInput):
    def value_from_datadict(self, data, files, name):
        return files.getlist(name)


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data or []
        if self.required and not files:
            raise forms.ValidationError('请选择文件。')
        if len(files) > 10:
            raise forms.ValidationError('每次最多上传 10 个文件。')
        return [validate_upload(super(MultipleFileField, self).clean(file)) for file in files]


class ArtifactFields(forms.Form):
    uploads = MultipleFileField(label='上传新文件', required=False, widget=MultipleFileInput(attrs={'multiple': True}), help_text='可多选，最多 10 个；每个文件不超过 20 MB。')
    duplicate_action = forms.ChoiceField(label='遇到同名文件时', required=False, choices=[('', '请先选择 / 取消上传'), ('version', '上传为新版本'), ('independent', '作为新的独立文件')])
    version_description = forms.CharField(label='版本说明', required=False, widget=forms.Textarea(attrs={'rows': 2}), max_length=4000)


class UploadForm(ArtifactFields):
    logical_file = forms.ModelChoiceField(label='更新指定文件（可选）', queryset=LogicalFile.objects.none(), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['logical_file'].queryset = workspace.files.all()

    def clean(self):
        data = super().clean()
        if not data.get('uploads'):
            raise forms.ValidationError('请选择至少一个文件。')
        return data


class CommitForm(ArtifactFields, forms.ModelForm):
    existing_versions = forms.ModelMultipleChoiceField(label='选择已有项目文件版本', queryset=FileVersion.objects.none(), required=False,
                                                      help_text='引用选定版本，不会复制文件或改变版本。')
    class Meta:
        model = ProgressCommit
        fields = ['title', 'description', 'related_task', 'parent_commit']
        labels = {'related_task': '关联任务', 'parent_commit': '补充或修正的历史进度（可选）'}
        widgets = {'description': forms.Textarea(attrs={'rows': 6})}

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.workspace = workspace
        self.fields['related_task'].queryset = workspace.tasks.all()
        self.fields['parent_commit'].queryset = workspace.commits.all()
        self.fields['existing_versions'].queryset = FileVersion.objects.filter(logical_file__workspace=workspace).select_related('logical_file')
        self.order_fields(['title', 'description', 'related_task', 'uploads', 'existing_versions', 'duplicate_action', 'version_description', 'parent_commit'])

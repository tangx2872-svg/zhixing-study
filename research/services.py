"""All version creation uses existing Resource storage; project row serializes writers."""
import hashlib
import logging
from pathlib import Path
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from django_lms.files import validate_upload
from resources.models import Resource
from .models import ResearchWorkspace, LogicalFile, FileVersion, CommitFileChange, Activity
from .permissions import require_workspace


def upload_name(upload):
    return Path(upload.name).name


def upload_versions(workspace, user, uploads, description='', mode='', target=None, commit=None, existing=()):
    """Caller must validate the form and own the outer transaction/cleanup ledger.

    Exposes a separate public transaction boundary below for rollback of storage.
    """
    require_workspace(user, workspace, write=True)
    if mode not in ('', 'version', 'independent'):
        raise ValidationError('请选择正确的同名文件处理方式。')
    names = [upload_name(upload) for upload in uploads]
    if len(names) != len(set(names)):
        raise ValidationError('一次上传中有重复文件名，请分别提交。')
    if len(uploads) > 10:
        raise ValidationError('每次最多上传 10 个文件。')
    if target and (target.workspace_id != workspace.pk or len(uploads) != 1):
        raise ValidationError('指定文件时只能上传一个文件，且必须属于当前项目。')
    if target and mode == 'independent':
        raise ValidationError('作为独立文件时，请清空「更新指定文件」选项。')
    plans = []
    for upload, name in zip(uploads, names):
        validate_upload(upload)
        if len(name) > 200:
            raise ValidationError('文件名不能超过 200 个字符。')
        matches = list(workspace.files.filter(name=name))
        logical = target
        if not target and matches:
            if not mode:
                raise ValidationError('检测到同名文件「{}」，请选择上传为新版本、作为独立文件或取消。'.format(name))
            if mode == 'version':
                if len(matches) != 1:
                    raise ValidationError('「{}」有多个独立文件，请在文件详情指定要更新的文件。'.format(name))
                logical = matches[0]
        plans.append((upload, name, logical))
    for version in existing:
        if version.logical_file.workspace_id != workspace.pk:
            raise ValidationError('不能引用其他项目的文件版本。')
    return plans


def save_artifacts(workspace, user, cleaned, commit_factory=None):
    """Atomic DB writes plus compensating cleanup of newly created storage objects."""
    saved = []
    try:
        with transaction.atomic():
            workspace = ResearchWorkspace.objects.select_for_update().get(pk=workspace.pk)
            require_workspace(user, workspace, write=True)
            uploads = cleaned.get('uploads', [])
            existing = cleaned.get('existing_versions', [])
            plans = upload_versions(workspace, user, uploads, cleaned.get('version_description', ''),
                                    cleaned.get('duplicate_action', ''), cleaned.get('logical_file'), existing=existing)
            commit = commit_factory(workspace) if commit_factory else None
            if commit:
                Activity.objects.create(workspace=workspace, actor=user, kind='progress_commit', title=commit.title, commit=commit)
            versions = []
            for upload, name, logical in plans:
                if logical is None:
                    logical = LogicalFile.objects.create(workspace=workspace, name=name, created_by=user)
                previous = logical.current_version
                digest = hashlib.sha256()
                for chunk in upload.chunks():
                    digest.update(chunk)
                upload.seek(0)
                resource = Resource(resource_name=name, workspace=workspace)
                storage = resource.resource_file.storage
                # UUID key; never reuse a historical path even for same logical name.
                stored_name = storage.save('research/{}/{}{}'.format(workspace.pk, uuid4().hex, Path(name).suffix.lower()), upload)
                saved.append((storage, stored_name))
                resource.resource_file.name = stored_name
                resource.save()
                version = FileVersion.objects.create(logical_file=logical, version_number=previous.version_number + 1 if previous else 1,
                    resource=resource, uploaded_by=user, description=cleaned.get('version_description', ''), size=upload.size, checksum=digest.hexdigest())
                versions.append(version)
                Activity.objects.create(workspace=workspace, actor=user, kind='file_new_version' if previous else 'file_upload',
                    title='{} v{}'.format(logical.name, version.version_number), description=version.description, version=version, commit=commit)
                if commit:
                    CommitFileChange.objects.create(commit=commit, version=version, previous_version=previous, kind='version' if previous else 'new')
            if commit:
                for version in existing:
                    CommitFileChange.objects.get_or_create(commit=commit, version=version, defaults={'kind': 'reference'})
            return commit, versions
    except Exception:
        for storage, name in saved:
            try:
                storage.delete(name)
            except OSError:
                logging.getLogger(__name__).exception('Could not clean up failed research upload')
        raise

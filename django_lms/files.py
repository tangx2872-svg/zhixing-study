from pathlib import Path
from django.core.exceptions import ValidationError
from django.db import transaction

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.csv', '.md', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.py', '.ipynb', '.png', '.jpg', '.jpeg'}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024


def validate_upload(file):
    if file.size > MAX_UPLOAD_SIZE:
        raise ValidationError('文件不能超过 20 MB。')
    if not file.size:
        raise ValidationError('不能上传空文件。')
    if Path(file.name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValidationError('不支持此文件类型。请上传文档、图片、ZIP、Python 或 Notebook 文件。')
    return file


def remove_unreferenced_file(storage, name):
    if not name:
        return
    def cleanup():
        from assignments.models import SubmitAssignment
        from resources.models import Resource
        from research.models import FileVersion
        from assignments.models import SubmissionAttachment
        if not SubmitAssignment.objects.filter(assignment_file=name).exists() and not SubmissionAttachment.objects.filter(file=name).exists() and not Resource.objects.filter(resource_file=name).exists() and not FileVersion.objects.filter(resource__resource_file=name).exists():
            try:
                storage.delete(name)
            except OSError:
                import logging
                logging.getLogger(__name__).exception('Could not clean up an unused attachment')
    transaction.on_commit(cleanup)

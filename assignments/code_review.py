"""Bounded, read-only archive browsing. Uploaded code is never extracted or executed."""
import difflib
import hashlib
import stat
import zipfile
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

MAX_ENTRIES = 1000
MAX_EXPANDED = 50 * 1024 * 1024
MAX_PREVIEW = 512 * 1024
MAX_LINES = 5000
TEXT_EXTENSIONS = {'.py', '.java', '.js', '.ts', '.tsx', '.jsx', '.html', '.htm', '.css', '.scss',
                   '.xml', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.sh', '.bat', '.ps1',
                   '.sql', '.c', '.h', '.cpp', '.hpp', '.go', '.rs', '.vue', '.txt', '.md', '.csv',
                   '.properties', '.gradle', '.ipynb', '.rst', '.log', '.kt', '.kts', '.cs', '.m', '.r',
                   '.rb', '.php', '.swift', '.dart', '.scala', '.lua', '.tex'}
TEXT_NAMES = {'Dockerfile', 'Jenkinsfile', 'Makefile', '.gitignore', '.dockerignore'}
CODE_EXTENSIONS = TEXT_EXTENSIONS - {'.txt', '.md', '.csv', '.rst', '.log'}


def archive_entries(stream):
    try:
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValidationError('ZIP 最多包含 1000 个条目。')
            total, seen, result = 0, set(), []
            for info in infos:
                name = info.filename
                path = PurePosixPath(name)
                if ('\\' in name or name.startswith('/') or ':' in name or '\x00' in name
                        or any(part in ('..', '.', '') for part in name.rstrip('/').split('/'))
                        or any(ord(c) < 32 for c in name) or len(name) > 500):
                    raise ValidationError('ZIP 中包含不安全的文件路径。')
                if info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValidationError('不支持加密 ZIP 或符号链接。')
                if info.is_dir():
                    continue
                if str(path) in seen:
                    raise ValidationError('ZIP 中包含重复文件路径。')
                seen.add(str(path))
                total += info.file_size
                if total > MAX_EXPANDED or (info.file_size > 1024 * 1024 and info.file_size > max(1, info.compress_size) * 200):
                    raise ValidationError('ZIP 展开大小或压缩比超出限制。展开后最多 50 MB。')
                result.append({'name': name, 'size': info.file_size})
            if not result:
                raise ValidationError('ZIP 中没有可提交的文件。')
            return result
    except (zipfile.BadZipFile, OSError, NotImplementedError) as exc:
        raise ValidationError('无法读取 ZIP，请上传标准、完整的 ZIP 文件。') from exc
    finally:
        stream.seek(0)


def text_content(data):
    if b'\x00' in data and not data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return None
    for encoding in ('utf-8-sig', 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'gb18030'):
        try:
            value = data.decode(encoding)
            if any(ord(c) < 32 and c not in '\n\r\t\f' for c in value):
                return None
            return value.replace('\r\n', '\n').replace('\r', '\n')
        except UnicodeError:
            pass
    return None


def is_text(path):
    pure = PurePosixPath(path)
    return pure.suffix.lower() in TEXT_EXTENSIONS or pure.name in TEXT_NAMES


def manifest(submission):
    from .submission_service import attachment_list
    result = {}
    attachments = attachment_list(submission)
    zip_count = sum(item.name.lower().endswith('.zip') for item in attachments)
    for item in attachments:
        if item.name.lower().endswith('.zip'):
            with item.file.open('rb') as stream:
                entries = archive_entries(stream)
            roots = {entry['name'].split('/')[0] for entry in entries}
            strip_root = len(roots) == 1 and all('/' in entry['name'] for entry in entries)
            for entry in entries:
                path = entry['name'].split('/', 1)[1] if strip_root else entry['name']
                if zip_count > 1:
                    path = item.name + '/' + path
                if path in result:
                    raise ValidationError('项目中存在相同路径，请分别打包或重新命名附件。')
                result[path] = dict(entry, attachment=item, member=entry['name'], path=path)
        else:
            if item.name in result:
                raise ValidationError('附件路径与 ZIP 内文件冲突。')
            result[item.name] = {'attachment': item, 'member': None, 'path': item.name, 'size': item.size}
        if len(result) > MAX_ENTRIES or sum(entry['size'] for entry in result.values()) > MAX_EXPANDED:
            raise ValidationError('一次提交展开后最多 1000 个文件、合计 50 MB。')
    return dict(sorted(result.items()))


def read_entry(entry, limit=MAX_PREVIEW):
    if entry['size'] > limit:
        raise ValidationError('该文件超过在线预览大小限制，请下载查看。')
    try:
        with entry['attachment'].file.open('rb') as stream:
            if entry['member'] is not None:
                with zipfile.ZipFile(stream) as archive, archive.open(entry['member']) as member:
                    data = member.read(limit + 1)
            else:
                data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValidationError('文件内容超过预览限制。')
        return data
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        raise ValidationError('附件无法读取，请联系教师或重新提交。') from exc


def highlighted_lines(path, text):
    if len(text.splitlines()) > MAX_LINES:
        raise ValidationError('代码超过 5000 行，请下载查看。')
    try:
        lexer = get_lexer_for_filename(path)
    except ClassNotFound:
        lexer = TextLexer()
    html = highlight(text, lexer, HtmlFormatter(nowrap=True))
    return [mark_safe(line) for line in html.splitlines()]


def changes_between(old, new):
    """Hash bounded streams; binary changes are reported, never rendered as executable HTML."""
    changes = []
    for path in sorted(set(old) | set(new)):
        if path not in old:
            status = 'added'
        elif path not in new:
            status = 'deleted'
        else:
            left, right = old[path], new[path]
            if left['size'] != right['size']:
                status = 'modified'
            else:
                status = 'unchanged' if entry_digest(left) == entry_digest(right) else 'modified'
        changes.append({'path': path, 'status': status, 'label': {'added': '新增', 'deleted': '删除', 'modified': '修改', 'unchanged': '未变化'}[status]})
    return changes


def entry_digest(entry):
    digest = hashlib.sha256()
    with entry['attachment'].file.open('rb') as stream:
        if entry['member'] is None:
            source = stream
            archive = None
        else:
            archive = zipfile.ZipFile(stream)
            source = archive.open(entry['member'])
        try:
            remaining = MAX_EXPANDED + 1
            while remaining:
                chunk = source.read(min(65536, remaining))
                if not chunk:
                    return digest.digest()
                digest.update(chunk)
                remaining -= len(chunk)
            raise ValidationError('文件过大，无法在线比较。')
        finally:
            if archive:
                source.close()
                archive.close()


def side_by_side(left, right):
    a, b = left.splitlines(), right.splitlines()
    # Bound SequenceMatcher's worst case on repetitive source files.
    if max(len(a), len(b)) > 2000 or len(left) + len(right) > 256 * 1024:
        raise ValidationError('文件较大，暂不生成逐行差异，请下载对比。')
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=True).get_opcodes():
        for offset in range(max(i2 - i1, j2 - j1)):
            i, j = i1 + offset, j1 + offset
            rows.append({'kind': tag, 'left_number': i + 1 if i < i2 else '',
                         'right_number': j + 1 if j < j2 else '',
                         'left': a[i] if i < i2 else '', 'right': b[j] if j < j2 else ''})
    return rows

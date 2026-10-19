"""Back up local MySQL/media, apply incremental migrations, verify old business rows."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection
from django.utils import timezone


BUSINESS = {
    'users_user': None,
    'courses_course': None,
    'courses_enrollment': None,
    'assignments_assignment': None,
    'assignments_submitassignment': None,
    'assignments_graderecord': None,
    'resources_resource': ['id', 'resource_name', 'resource_file', 'course_id'],
}


def snapshot(projection=None):
    result = {}
    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        for table, fields in BUSINESS.items():
            if table not in tables:
                raise CommandError('Missing expected legacy table: {}'.format(table))
            if projection:
                fields = projection[table]
            elif fields is None:
                fields = [column.name for column in connection.introspection.get_table_description(cursor, table)]
            columns = ', '.join(connection.ops.quote_name(f) for f in fields)
            cursor.execute('SELECT {} FROM {} ORDER BY id'.format(columns, connection.ops.quote_name(table)))
            rows = cursor.fetchall()
            payload = json.dumps(rows, ensure_ascii=False, default=str).encode('utf-8')
            result[table] = {'count': len(rows), 'sha256': hashlib.sha256(payload).hexdigest(), 'fields': fields}
    return result


def media_snapshot():
    root = Path(settings.MEDIA_ROOT)
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()} if root.exists() else {}


class Command(BaseCommand):
    help = 'Back up MySQL and media, then apply incremental migrations and check preserved teaching records.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Apply migrations after verified backups; otherwise backup only.')
        parser.add_argument('--mysqldump', default=shutil.which('mysqldump') or r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe')

    def handle(self, *args, **options):
        config = settings.DATABASES['default']
        if config['ENGINE'] != 'django.db.backends.mysql':
            raise CommandError('This command is intended for the existing MySQL installation only.')
        if not Path(options['mysqldump']).is_file():
            raise CommandError('mysqldump not found; provide --mysqldump PATH.')
        before = snapshot()
        media_before = media_snapshot()
        destination = Path(settings.BASE_DIR) / '.local' / 'research-upgrade' / timezone.localtime().strftime('%Y%m%d-%H%M%S-%f')
        destination.mkdir(parents=True)
        dump = destination / 'database.sql'
        environment = os.environ.copy()
        environment['MYSQL_PWD'] = config.get('PASSWORD', '')
        command = [options['mysqldump'], '--host=' + config.get('HOST', 'localhost'), '--port=' + str(config.get('PORT') or '3306'),
                   '--user=' + config.get('USER', 'root'), '--single-transaction', '--routines', '--triggers', '--events',
                   '--no-tablespaces', '--set-gtid-purged=OFF', '--result-file=' + str(dump), config['NAME']]
        result = subprocess.run(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode or not dump.exists() or dump.stat().st_size == 0:
            raise CommandError('MySQL backup failed; no migration applied. Check mysqldump access locally.')
        with zipfile.ZipFile(destination / 'media.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for relative in media_before:
                archive.write(Path(settings.MEDIA_ROOT) / relative, relative)
        with zipfile.ZipFile(destination / 'media.zip') as archive:
            for relative, digest in media_before.items():
                if hashlib.sha256(archive.read(relative)).hexdigest() != digest:
                    raise CommandError('Media backup verification failed; no migration applied.')
        (destination / 'before.json').write_text(json.dumps({'tables': before, 'media': media_before}, indent=2), encoding='utf-8')
        self.stdout.write('Verified backup: {}'.format(destination))
        if not options['apply']:
            self.stdout.write('Backup only; no migration applied.')
            return
        if snapshot() != before or media_snapshot() != media_before:
            raise CommandError('Existing records changed during backup; pause writers and try again. No migration applied.')
        call_command('migrate', interactive=False)
        call_command('check')
        after = snapshot({table: value['fields'] for table, value in before.items()})
        media_after = media_snapshot()
        report = {'before': before, 'after': after, 'business_preserved': before == after, 'media_preserved': media_before == media_after}
        (destination / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if not report['business_preserved'] or not report['media_preserved']:
            raise CommandError('Preservation check differs; inspect verification.json and the backup before any further changes.')
        self.stdout.write(self.style.SUCCESS('Migration complete: all existing teaching rows and media checksums preserved.'))

from django.db import migrations


def backfill(apps, schema_editor):
    Activity = apps.get_model('research', 'Activity')
    alias = schema_editor.connection.alias

    def add(timestamp, **values):
        # Historical migration models intentionally do not use append-only methods.
        if not Activity.objects.using(alias).filter(**values).exists():
            event = Activity.objects.using(alias).create(**values)
            Activity.objects.using(alias).filter(pk=event.pk).update(created_at=timestamp)

    for project in apps.get_model('research', 'ResearchWorkspace').objects.using(alias).iterator():
        add(project.created_at, workspace_id=project.pk, actor_id=project.created_by_id, kind='workspace_created', title=project.name)
    for member in apps.get_model('research', 'WorkspaceMember').objects.using(alias).select_related('workspace', 'user').iterator():
        add(member.created_at, workspace_id=member.workspace_id, actor_id=member.workspace.owner_id,
            kind='member_joined', title='{} · {}'.format(member.user.username, member.role))
    for task in apps.get_model('research', 'ResearchTask').objects.using(alias).iterator():
        add(task.created_at, workspace_id=task.workspace_id, actor_id=task.created_by_id, kind='task_created', title=task.title, task_id=task.pk)
    for commit in apps.get_model('research', 'ProgressCommit').objects.using(alias).iterator():
        add(commit.created_at, workspace_id=commit.workspace_id, actor_id=commit.author_id, kind='progress_commit', title=commit.title, commit_id=commit.pk)
    for version in apps.get_model('research', 'FileVersion').objects.using(alias).select_related('logical_file').iterator():
        add(version.created_at, workspace_id=version.logical_file.workspace_id, actor_id=version.uploaded_by_id,
            kind='file_upload' if version.version_number == 1 else 'file_new_version',
            title='{} v{}'.format(version.logical_file.name, version.version_number), version_id=version.pk)


class Migration(migrations.Migration):
    dependencies = [('research', '0003_activity_commitcomment')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]

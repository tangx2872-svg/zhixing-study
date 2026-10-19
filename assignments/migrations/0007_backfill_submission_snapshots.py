from django.db import migrations


def backfill(apps, schema_editor):
    Submission = apps.get_model('assignments', 'SubmitAssignment')
    alias = schema_editor.connection.alias
    counters = {}
    for submission in Submission.objects.using(alias).select_related('author').order_by('submitted_date', 'pk').iterator():
        key = (submission.assignment_ques_id, submission.author_id)
        counters[key] = counters.get(key, 0) + 1
        Submission.objects.using(alias).filter(pk=submission.pk).update(version_number=counters[key],
            participant_snapshot=[{'id': submission.author_id, 'username': submission.author.username,
                                   'name': submission.author.first_name or submission.author.username}])


class Migration(migrations.Migration):
    dependencies = [('assignments', '0006_auto_20261008_1057')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]

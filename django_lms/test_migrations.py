from datetime import timedelta
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ExistingDataMigrationTests(TransactionTestCase):
    def test_duplicate_submissions_are_retained_and_constrained(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [('assignments', '0002_auto_20201027_1311'), ('courses', '0001_initial')]
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            User = apps.get_model('users', 'User')
            Course = apps.get_model('courses', 'Course')
            Assignment = apps.get_model('assignments', 'Assignment')
            Submission = apps.get_model('assignments', 'SubmitAssignment')
            teacher = User.objects.create(username='old-teacher', user_type=2)
            student = User.objects.create(username='old-student', user_type=1)
            course = Course.objects.create(course_name='旧课程', course_description='旧记录', teacher=teacher)
            assignment = Assignment.objects.create(assignment_name='旧作业', assignment_description='要求', course=course, due_date=timezone.now() + timedelta(days=1))
            first = Submission.objects.create(author=student, assignment_ques=assignment, topic='已评分旧版', description='x', assignment_file='old.txt', graded=True, grade=80)
            second = Submission.objects.create(author=student, assignment_ques=assignment, topic='较新未评分', description='x', assignment_file='new.txt')
            orphan = Submission.objects.create(author=student, topic='未关联历史提交', description='x', assignment_file='orphan.txt')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            Submission = apps.get_model('assignments', 'SubmitAssignment')
            self.assertEqual(Submission.objects.count(), 3)
            self.assertEqual(Submission.objects.get(pk=first.pk).current_slot, 1)
            self.assertIsNone(Submission.objects.get(pk=second.pk).current_slot)
            self.assertIsNone(Submission.objects.get(pk=orphan.pk).current_slot)
            self.assertEqual(Submission.objects.get(pk=first.pk).grade, 80)
            self.assertEqual(Submission.objects.get(pk=first.pk).version_number, 1)
            self.assertEqual(Submission.objects.get(pk=second.pk).version_number, 2)
            self.assertEqual(Submission.objects.get(pk=first.pk).participant_snapshot[0]['id'], student.pk)
            self.assertEqual(Submission.objects.get(pk=second.pk).assignment_file, 'new.txt')
            self.assertEqual(apps.get_model('assignments', 'Assignment').objects.get(pk=assignment.pk).submission_mode, 'individual')
            Record = apps.get_model('assignments', 'GradeRecord')
            record = Record.objects.get(submission_id=first.pk)
            self.assertEqual(record.grade, 80)
            self.assertIsNone(record.created_at)
            self.assertIsNone(record.grader_id)
            self.assertEqual(Submission.objects.get(pk=first.pk).updated_at, first.submitted_date)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Submission.objects.create(author_id=student.pk, assignment_ques_id=assignment.pk, topic='重复有效提交', description='x', assignment_file='duplicate.txt')
        finally:
            MigrationExecutor(connection).migrate(latest)

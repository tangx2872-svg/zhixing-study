from django.core.management import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from research.demo import seed_demo


class Command(BaseCommand):
    help = 'Create curated read-only guest demo workspaces; existing records are never overwritten.'

    def handle(self, *args, **options):
        try:
            projects = seed_demo()
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        for project, created in projects:
            self.stdout.write('{}: {} ({})'.format('Created' if created else 'Already prepared', project.demo_key, project.pk))
        self.stdout.write(self.style.SUCCESS('Guest demo ready: /research/demo/'))

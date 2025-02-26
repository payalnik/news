from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

class Command(BaseCommand):
    help = 'Setup periodic tasks for checking scheduled emails'

    def handle(self, *args, **kwargs):
        # Create interval schedule (every 30 minutes)
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=30,
            period=IntervalSchedule.MINUTES,
        )
        
        # Create periodic task
        task, created = PeriodicTask.objects.get_or_create(
            name='Check scheduled emails',
            task='news_app.tasks.check_scheduled_emails',
            interval=schedule,
            kwargs=json.dumps({}),
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Successfully created periodic task'))
        else:
            self.stdout.write(self.style.SUCCESS('Periodic task already exists'))

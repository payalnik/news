from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

class Command(BaseCommand):
    help = 'Setup periodic tasks for checking scheduled emails'

    def handle(self, *args, **kwargs):
        # Create interval schedule (every 5 minutes)
        # Handle potential duplicate schedules
        try:
            schedule = IntervalSchedule.objects.get(
                every=5,
                period=IntervalSchedule.MINUTES,
            )
            created = False
        except IntervalSchedule.DoesNotExist:
            schedule = IntervalSchedule.objects.create(
                every=5,
                period=IntervalSchedule.MINUTES,
            )
            created = True
        except IntervalSchedule.MultipleObjectsReturned:
            # If multiple objects exist, use the first one
            schedules = IntervalSchedule.objects.filter(
                every=5,
                period=IntervalSchedule.MINUTES,
            )
            schedule = schedules.first()
            created = False
            self.stdout.write(self.style.WARNING(f'Found {schedules.count()} duplicate schedules, using the first one'))
        
        # Get or update periodic task
        try:
            task = PeriodicTask.objects.get(name='Check scheduled emails')
            # Update the task
            task.task = 'news_app.tasks.check_scheduled_emails'
            task.interval = schedule
            task.kwargs = json.dumps({})
            task.enabled = True  # Make sure it's enabled
            task.save()
            self.stdout.write(self.style.SUCCESS('Successfully updated periodic task'))
        except PeriodicTask.DoesNotExist:
            # Create a new task if it doesn't exist
            task = PeriodicTask.objects.create(
                name='Check scheduled emails',
                task='news_app.tasks.check_scheduled_emails',
                interval=schedule,
                kwargs=json.dumps({}),
                enabled=True,
            )
            self.stdout.write(self.style.SUCCESS('Successfully created periodic task'))

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
import json

class Command(BaseCommand):
    help = 'Setup periodic tasks for checking scheduled emails and cleaning up old news items'

    def handle(self, *args, **kwargs):
        # Setup task for checking scheduled emails
        self.setup_check_emails_task()
        
        # Setup task for cleaning up old news items
        self.setup_cleanup_task()
        
        self.stdout.write(self.style.SUCCESS('Successfully set up all periodic tasks'))
    
    def setup_check_emails_task(self):
        """Setup the task for checking scheduled emails (runs every 5 minutes)"""
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
            self.stdout.write(self.style.SUCCESS('Successfully updated check emails task'))
        except PeriodicTask.DoesNotExist:
            # Create a new task if it doesn't exist
            task = PeriodicTask.objects.create(
                name='Check scheduled emails',
                task='news_app.tasks.check_scheduled_emails',
                interval=schedule,
                kwargs=json.dumps({}),
                enabled=True,
            )
            self.stdout.write(self.style.SUCCESS('Successfully created check emails task'))
    
    def setup_cleanup_task(self):
        """Setup the task for cleaning up old news items (runs daily at 3:00 AM)"""
        # Create or get a crontab schedule for 3:00 AM daily
        try:
            crontab = CrontabSchedule.objects.get(
                minute='0',
                hour='3',
                day_of_week='*',
                day_of_month='*',
                month_of_year='*'
            )
            created = False
        except CrontabSchedule.DoesNotExist:
            crontab = CrontabSchedule.objects.create(
                minute='0',
                hour='3',
                day_of_week='*',
                day_of_month='*',
                month_of_year='*'
            )
            created = True
        except CrontabSchedule.MultipleObjectsReturned:
            # If multiple objects exist, use the first one
            crontabs = CrontabSchedule.objects.filter(
                minute='0',
                hour='3',
                day_of_week='*',
                day_of_month='*',
                month_of_year='*'
            )
            crontab = crontabs.first()
            created = False
            self.stdout.write(self.style.WARNING(f'Found {crontabs.count()} duplicate crontabs, using the first one'))
        
        # Get or update periodic task
        try:
            task = PeriodicTask.objects.get(name='Clean up old news items')
            # Update the task
            task.task = 'news_app.tasks.cleanup_old_news_items'
            task.crontab = crontab
            task.interval = None  # Make sure interval is None since we're using crontab
            task.kwargs = json.dumps({})
            task.enabled = True  # Make sure it's enabled
            task.save()
            self.stdout.write(self.style.SUCCESS('Successfully updated cleanup task'))
        except PeriodicTask.DoesNotExist:
            # Create a new task if it doesn't exist
            task = PeriodicTask.objects.create(
                name='Clean up old news items',
                task='news_app.tasks.cleanup_old_news_items',
                crontab=crontab,
                kwargs=json.dumps({}),
                enabled=True,
            )
            self.stdout.write(self.style.SUCCESS('Successfully created cleanup task'))

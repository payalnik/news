from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Check periodic tasks configured in the system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Show all details including task arguments and options',
        )
        parser.add_argument(
            '--enabled',
            action='store_true',
            help='Show only enabled tasks',
        )
        parser.add_argument(
            '--disabled',
            action='store_true',
            help='Show only disabled tasks',
        )

    def handle(self, *args, **options):
        # Get all periodic tasks
        tasks = PeriodicTask.objects.all().order_by('name')
        
        # Filter by enabled/disabled if requested
        if options['enabled']:
            tasks = tasks.filter(enabled=True)
        elif options['disabled']:
            tasks = tasks.filter(enabled=False)
        
        # Display header
        self.stdout.write(self.style.SUCCESS(f"Periodic Tasks Configuration ({tasks.count()} total)"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"Current time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Count enabled and disabled tasks
        enabled_count = tasks.filter(enabled=True).count()
        disabled_count = tasks.filter(enabled=False).count()
        self.stdout.write(f"Enabled tasks: {enabled_count}")
        self.stdout.write(f"Disabled tasks: {disabled_count}")
        self.stdout.write("=" * 80)
        
        # Display interval schedules
        interval_schedules = IntervalSchedule.objects.all()
        self.stdout.write(self.style.SUCCESS("\nInterval Schedules:"))
        self.stdout.write("-" * 80)
        
        if interval_schedules.exists():
            for schedule in interval_schedules:
                self.stdout.write(f"ID: {schedule.id} - Every {schedule.every} {schedule.period}")
        else:
            self.stdout.write(self.style.WARNING("No interval schedules configured"))
        
        # Display crontab schedules
        crontab_schedules = CrontabSchedule.objects.all()
        self.stdout.write(self.style.SUCCESS("\nCrontab Schedules:"))
        self.stdout.write("-" * 80)
        
        if crontab_schedules.exists():
            for schedule in crontab_schedules:
                self.stdout.write(f"ID: {schedule.id} - {schedule.minute} {schedule.hour} {schedule.day_of_week} {schedule.day_of_month} {schedule.month_of_year}")
        else:
            self.stdout.write(self.style.WARNING("No crontab schedules configured"))
        
        # Display all tasks
        self.stdout.write(self.style.SUCCESS("\nPeriodic Tasks:"))
        self.stdout.write("-" * 80)
        
        if tasks.exists():
            for task in tasks:
                # Basic info
                status = "ENABLED" if task.enabled else "DISABLED"
                status_style = self.style.SUCCESS if task.enabled else self.style.WARNING
                
                self.stdout.write(status_style(f"{task.name} [{status}]"))
                self.stdout.write(f"  Task: {task.task}")
                
                # Schedule info
                if task.interval:
                    self.stdout.write(f"  Schedule: Every {task.interval.every} {task.interval.period}")
                elif task.crontab:
                    self.stdout.write(f"  Schedule: {task.crontab.minute} {task.crontab.hour} {task.crontab.day_of_week} {task.crontab.day_of_month} {task.crontab.month_of_year}")
                elif task.solar:
                    self.stdout.write(f"  Schedule: Solar - {task.solar.event} at {task.solar.latitude}/{task.solar.longitude}")
                elif task.clocked:
                    self.stdout.write(f"  Schedule: Clocked - {task.clocked.clocked_time}")
                else:
                    self.stdout.write("  Schedule: One-off task")
                
                # Last run info
                if task.last_run_at:
                    self.stdout.write(f"  Last run: {task.last_run_at.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    
                    # Calculate time since last run
                    time_since_last_run = timezone.now() - task.last_run_at
                    hours, remainder = divmod(time_since_last_run.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    self.stdout.write(f"  Time since last run: {int(hours)}h {int(minutes)}m {int(seconds)}s")
                else:
                    self.stdout.write("  Last run: Never")
                
                # Total run count
                self.stdout.write(f"  Total run count: {task.total_run_count}")
                
                # Additional details if --all flag is provided
                if options['all']:
                    if task.kwargs:
                        self.stdout.write(f"  Arguments: {task.kwargs}")
                    if task.expires:
                        self.stdout.write(f"  Expires: {task.expires.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    if task.start_time:
                        self.stdout.write(f"  Start time: {task.start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    if task.description:
                        self.stdout.write(f"  Description: {task.description}")
                
                self.stdout.write("")  # Empty line between tasks
        else:
            self.stdout.write(self.style.WARNING("No periodic tasks configured"))
        
        # Display troubleshooting information
        self.stdout.write(self.style.SUCCESS("\nTroubleshooting Information:"))
        self.stdout.write("-" * 80)
        self.stdout.write("If tasks are not running, check the following:")
        self.stdout.write("1. Ensure Celery worker is running: celery -A news_updater worker -l info")
        self.stdout.write("2. Ensure Celery beat is running: celery -A news_updater beat -l info")
        self.stdout.write("3. Ensure Redis server is running: redis-cli ping")
        self.stdout.write("4. Check Celery logs for errors")
        self.stdout.write("5. Verify that tasks are enabled")
        self.stdout.write("6. Verify that the schedule is correct")
        self.stdout.write("7. Ensure the CELERY_BEAT_SCHEDULER setting is set to 'django_celery_beat.schedulers:DatabaseScheduler'")

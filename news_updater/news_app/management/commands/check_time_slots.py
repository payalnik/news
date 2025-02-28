from django.core.management.base import BaseCommand
from django.utils import timezone
from news_app.models import TimeSlot, UserProfile
from datetime import timedelta
import pytz

class Command(BaseCommand):
    help = 'Check time slots enabled for scheduled emails'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Filter by username',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Show all details including user emails',
        )
        parser.add_argument(
            '--check-now',
            action='store_true',
            help='Check which time slots would be triggered now',
        )

    def handle(self, *args, **options):
        # Get current UTC time
        current_time = timezone.now().astimezone(timezone.utc)
        current_time_only = current_time.time()
        
        # Calculate time 5 minutes ago (the window used in the check_scheduled_emails task)
        five_mins_ago = current_time - timedelta(minutes=5)
        five_mins_ago_time = five_mins_ago.time()
        
        # Get all time slots
        time_slots = TimeSlot.objects.all().order_by('time')
        
        # Filter by username if provided
        if options['user']:
            time_slots = time_slots.filter(user_profile__user__username=options['user'])
        
        # Display header
        self.stdout.write(self.style.SUCCESS(f"Time Slots Configuration ({time_slots.count()} total)"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Current time only: {current_time_only.strftime('%H:%M:%S')}")
        self.stdout.write(f"5 minutes ago: {five_mins_ago_time.strftime('%H:%M:%S')}")
        self.stdout.write("=" * 80)
        
        # Check if any time slots would be triggered now
        if options['check_now']:
            self.stdout.write(self.style.SUCCESS("\nTime slots that would be triggered now:"))
            self.stdout.write("-" * 80)
            
            # Handle the case where the time range crosses midnight
            if five_mins_ago_time > current_time_only:
                # Time range crosses midnight
                active_slots = time_slots.filter(
                    time__gte=five_mins_ago_time
                ) | time_slots.filter(
                    time__lte=current_time_only
                )
            else:
                # Normal time range within the same day
                active_slots = time_slots.filter(
                    time__gte=five_mins_ago_time,
                    time__lte=current_time_only
                )
            
            if active_slots.exists():
                for slot in active_slots:
                    self.stdout.write(self.style.SUCCESS(
                        f"ACTIVE NOW: {slot.time.strftime('%H:%M:%S')} - {slot.user_profile.user.username}"
                    ))
            else:
                self.stdout.write(self.style.WARNING("No time slots would be triggered now"))
        
        # Display all time slots
        self.stdout.write(self.style.SUCCESS("\nAll configured time slots:"))
        self.stdout.write("-" * 80)
        
        if time_slots.exists():
            for slot in time_slots:
                user = slot.user_profile.user
                
                # Basic info
                slot_info = f"{slot.time.strftime('%H:%M:%S')} - {user.username}"
                
                # Add email if --all flag is provided
                if options['all']:
                    slot_info += f" ({user.email})"
                    
                    # Check if email is verified
                    if slot.user_profile.email_verified:
                        slot_info += " [Verified]"
                    else:
                        slot_info += " [Not Verified]"
                
                # Check if this slot would be active now
                if options['check_now']:
                    # Handle the case where the time range crosses midnight
                    is_active = False
                    if five_mins_ago_time > current_time_only:
                        # Time range crosses midnight
                        if slot.time >= five_mins_ago_time or slot.time <= current_time_only:
                            is_active = True
                    else:
                        # Normal time range within the same day
                        if five_mins_ago_time <= slot.time <= current_time_only:
                            is_active = True
                    
                    if is_active:
                        self.stdout.write(self.style.SUCCESS(f"* {slot_info} [ACTIVE NOW]"))
                    else:
                        self.stdout.write(f"  {slot_info}")
                else:
                    self.stdout.write(f"  {slot_info}")
        else:
            self.stdout.write(self.style.WARNING("No time slots configured"))
        
        # Display time zones information
        self.stdout.write(self.style.SUCCESS("\nTime zone information:"))
        self.stdout.write("-" * 80)
        self.stdout.write(f"Server time zone: {timezone.get_current_timezone_name()}")
        self.stdout.write(f"Available time zones: {len(pytz.all_timezones)}")
        self.stdout.write("Note: All times are stored and processed in UTC")

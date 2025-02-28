from django.core.management.base import BaseCommand
from django.utils import timezone
from news_app.models import NewsItem
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleans up old news items to prevent database bloat'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete news items older than this many days (default: 30)'
        )
        parser.add_argument(
            '--keep-per-section',
            type=int,
            default=100,
            help='Keep at least this many most recent items per section (default: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without deleting any data'
        )

    def handle(self, *args, **options):
        days = options['days']
        keep_per_section = options['keep_per_section']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get all news items older than the cutoff date
        old_items = NewsItem.objects.filter(created_at__lt=cutoff_date)
        
        # Count how many items we'll delete
        total_count = old_items.count()
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN: Would delete {total_count} news items older than {days} days'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'Preparing to delete {total_count} news items older than {days} days'
            ))
        
        # Get a list of all user_profile and news_section combinations
        from django.db.models import Count
        section_counts = NewsItem.objects.values('user_profile', 'news_section').annotate(
            count=Count('id')
        )
        
        # For each combination, ensure we keep at least keep_per_section items
        protected_ids = []
        
        for section_data in section_counts:
            user_profile_id = section_data['user_profile']
            news_section_id = section_data['news_section']
            
            # Get the IDs of the most recent items for this section
            recent_ids = NewsItem.objects.filter(
                user_profile_id=user_profile_id,
                news_section_id=news_section_id
            ).order_by('-created_at')[:keep_per_section].values_list('id', flat=True)
            
            protected_ids.extend(list(recent_ids))
        
        # Exclude the protected IDs from deletion
        items_to_delete = old_items.exclude(id__in=protected_ids)
        delete_count = items_to_delete.count()
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN: Would delete {delete_count} news items while protecting {len(protected_ids)} recent items'
            ))
        else:
            # Perform the deletion
            deleted, _ = items_to_delete.delete()
            
            self.stdout.write(self.style.SUCCESS(
                f'Successfully deleted {deleted} news items while protecting {len(protected_ids)} recent items'
            ))
            
            logger.info(f'Cleaned up {deleted} old news items')

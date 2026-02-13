from django.db import models
from django.contrib.auth.models import User
import random
import string
import json

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    email_verified = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"

class NewsSection(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='news_sections')
    name = models.CharField(max_length=100)
    sources = models.TextField(help_text="Enter URLs separated by commas, newlines, or spaces")
    prompt = models.TextField(help_text="Instructions for prioritizing and summarizing news")
    order = models.PositiveIntegerField(default=0, help_text="Order in which the section appears")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name
    
    def get_sources_list(self):
        # Split by multiple possible separators (commas, newlines, spaces)
        import re
        # First replace common separators with a standard delimiter
        normalized = re.sub(r'[,\n\r\s]+', '|', self.sources)
        # Then split by the standard delimiter and ensure each URL has https:// prefix
        sources = [source.strip() for source in normalized.split('|') if source.strip()]
        # Add https:// prefix if not present
        return [source if source.startswith(('http://', 'https://')) else f'https://{source}' for source in sources]

class TimeSlot(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='time_slots')
    time = models.TimeField(help_text="Time to send the newsletter")
    
    class Meta:
        unique_together = ('user_profile', 'time')
    
    def __str__(self):
        return f"{self.user_profile.user.username} - {self.time.strftime('%H:%M')}"

class VerificationCode(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='verification_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Verification code for {self.user_profile.user.username}"
    
    @classmethod
    def generate_code(cls):
        return ''.join(random.choices(string.digits, k=6))

class NewsItem(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='news_items')
    news_section = models.ForeignKey(NewsSection, on_delete=models.CASCADE, related_name='news_items')
    headline = models.CharField(max_length=255)
    details = models.TextField()
    sources = models.TextField()  # Stored as JSON
    confidence = models.CharField(max_length=10, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.headline} - {self.created_at.strftime('%Y-%m-%d')}"
    
    def get_sources_list(self):
        try:
            return json.loads(self.sources)
        except:
            return []
    
    def set_sources_list(self, sources_list):
        self.sources = json.dumps(sources_list)
    
    def is_similar_to(self, headline, details, threshold=0.7):
        """
        Check if this news item is similar to the provided headline and details.
        Returns True if they are similar, False otherwise.

        The threshold parameter controls how similar the items need to be (0.0 to 1.0).
        Uses headline similarity as the primary signal, with a secondary details
        check to catch stories with different headlines about the same event.
        """
        # Exact headline match
        if self.headline.lower() == headline.lower():
            return True

        # Word overlap approach for headlines
        headline_words = set(self.headline.lower().split())
        new_headline_words = set(headline.lower().split())

        # Calculate Jaccard similarity (intersection over union)
        if not headline_words or not new_headline_words:
            return False

        h_intersection = len(headline_words.intersection(new_headline_words))
        h_union = len(headline_words.union(new_headline_words))
        headline_similarity = h_intersection / h_union

        if headline_similarity >= threshold:
            return True

        # Secondary check: if headlines are moderately similar, also compare details
        # to catch stories with different headlines covering the same event
        if headline_similarity >= 0.4 and details and self.details:
            # Filter out very short common words for a more meaningful comparison
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
                         'of', 'for', 'with', 'by', 'is', 'are', 'was', 'were', 'that',
                         'this', 'it', 'has', 'have', 'had', 'be', 'been', 'from', 'as'}
            detail_words = set(self.details.lower().split()) - stop_words
            new_detail_words = set(details.lower().split()) - stop_words

            if detail_words and new_detail_words:
                d_intersection = len(detail_words.intersection(new_detail_words))
                d_union = len(detail_words.union(new_detail_words))
                detail_similarity = d_intersection / d_union

                # Combined score: weight headline more heavily.
                # Use a lower threshold (0.5) than pure headline matching since
                # this path is already gated on headline_similarity >= 0.4
                combined = 0.6 * headline_similarity + 0.4 * detail_similarity
                if combined >= 0.5:
                    return True

        return False

class FetchLog(models.Model):
    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
        ('SKIPPED', 'Skipped'),
    ]
    
    url = models.URLField(max_length=2000)
    domain = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=50) # Jina, Requests, Playwright, Selenium
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.FloatField(default=0.0)
    content_length = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    
    def save(self, *args, **kwargs):
        if not self.domain and self.url:
            from urllib.parse import urlparse
            try:
                self.domain = urlparse(self.url).netloc
            except:
                pass
        super().save(*args, **kwargs)
        
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['status']),
        ]
        
    def __str__(self):
        return f"{self.method} fetch for {self.domain} - {self.status}"

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

    def get_source_domains(self):
        """Unique, de-prefixed hostnames of this section's sources (for display)."""
        from urllib.parse import urlparse
        domains = []
        for url in self.get_sources_list():
            netloc = urlparse(url).netloc.lower()
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            if netloc and netloc not in domains:
                domains.append(netloc)
        return domains

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
    # Dedup support: exact-match hash of headline+details and a cached
    # embedding vector (JSON list of floats) for semantic similarity.
    content_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    embedding = models.TextField(blank=True, null=True)  # JSON-encoded list[float]
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

    def get_normalized_source_urls(self):
        from .dedup import normalized_source_urls
        return normalized_source_urls(self.get_sources_list())

    def get_embedding_vector(self):
        if not self.embedding:
            return None
        try:
            return json.loads(self.embedding)
        except (ValueError, TypeError):
            return None

    def set_embedding_vector(self, vector):
        self.embedding = json.dumps(vector) if vector else None

    def save(self, *args, **kwargs):
        if not self.content_hash:
            from .dedup import content_hash_for
            self.content_hash = content_hash_for(self.headline, self.details)
        super().save(*args, **kwargs)
    
    def is_similar_to(self, headline, details, threshold=None):
        """
        Check whether this item is lexically similar to the given headline/details.

        Thin wrapper over ``dedup.lexical_similar`` (the shared implementation,
        which also handles the not-yet-saved items in the current batch). The
        threshold defaults to ``settings.DEDUP_HEADLINE_THRESHOLD``.
        """
        from django.conf import settings
        from .dedup import lexical_similar
        if threshold is None:
            threshold = getattr(settings, 'DEDUP_HEADLINE_THRESHOLD', 0.5)
        return lexical_similar(self.headline, self.details, headline, details, threshold)

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

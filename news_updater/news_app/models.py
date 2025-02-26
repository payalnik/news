from django.db import models
from django.contrib.auth.models import User
import random
import string

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
    created_at = models.DateTimeField(auto_now_add=True)
    
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

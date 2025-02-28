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
        """
        # Simple similarity check based on headline
        if self.headline.lower() == headline.lower():
            return True
        
        # More sophisticated similarity check could be implemented here
        # For now, we'll use a simple word overlap approach
        headline_words = set(self.headline.lower().split())
        new_headline_words = set(headline.lower().split())
        
        # Calculate Jaccard similarity (intersection over union)
        if not headline_words or not new_headline_words:
            return False
            
        intersection = len(headline_words.intersection(new_headline_words))
        union = len(headline_words.union(new_headline_words))
        
        similarity = intersection / union
        
        return similarity >= threshold

from django.contrib import admin
from .models import UserProfile, NewsSection, TimeSlot, VerificationCode, NewsItem, FetchLog

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_verified')
    search_fields = ('user__username', 'user__email')

@admin.register(NewsSection)
class NewsSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'user_profile', 'created_at')
    search_fields = ('name', 'user_profile__user__username')
    list_filter = ('created_at',)

@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'time')
    list_filter = ('time',)
    search_fields = ('user_profile__user__username',)

@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'code', 'created_at', 'is_used')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user_profile__user__username', 'code')

@admin.register(NewsItem)
class NewsItemAdmin(admin.ModelAdmin):
    list_display = ('headline', 'news_section', 'user_profile', 'confidence', 'created_at')
    list_filter = ('confidence', 'created_at', 'news_section')
    search_fields = ('headline', 'details', 'user_profile__user__username')
    date_hierarchy = 'created_at'

@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ('domain', 'method', 'status', 'duration_seconds', 'content_length', 'timestamp')
    list_filter = ('status', 'method', 'timestamp', 'domain')
    search_fields = ('url', 'domain', 'error_message')
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp', 'domain', 'url', 'method', 'status', 'duration_seconds', 'content_length', 'error_message')
    
    def has_add_permission(self, request):
        return False

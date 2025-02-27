from django.apps import AppConfig
import os
import sys
from django.core.management import call_command


class NewsAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'news_app'
    
    def ready(self):
        # Only run when the server is started, not during management commands
        # This prevents the command from running twice in development
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0]:
            # Set up periodic tasks
            try:
                call_command('setup_periodic_tasks')
                print("Periodic tasks set up successfully.")
            except Exception as e:
                print(f"Error setting up periodic tasks: {str(e)}")

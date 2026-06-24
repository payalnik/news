from django.apps import AppConfig
import os
import sys
from django.core.management import call_command


def _enable_sqlite_wal(sender, connection, **kwargs):
    """Put SQLite into WAL mode so readers don't block the writer.

    Applied to every new connection (workers, gunicorn, beat). Harmless no-op
    for any non-sqlite backend.
    """
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA busy_timeout=20000;')


class NewsAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'news_app'

    def ready(self):
        from django.db.backends.signals import connection_created
        connection_created.connect(_enable_sqlite_wal, dispatch_uid='sqlite_wal')


        # Only run when the server is started, not during management commands
        # This prevents the command from running twice in development
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0]:
            # Set up periodic tasks
            try:
                call_command('setup_periodic_tasks')
                print("Periodic tasks set up successfully.")
            except Exception as e:
                print(f"Error setting up periodic tasks: {str(e)}")

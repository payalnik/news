# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
try:
    from news_updater.celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Allow the app to run without Celery
    celery_app = None
    __all__ = ()

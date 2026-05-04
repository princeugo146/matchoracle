"""Celery application for MatchOracle.

Workers are optional — when REDIS_URL is not set, CELERY_TASK_ALWAYS_EAGER
is True (set in settings.py) so every task runs synchronously in the calling
process.  This means the app works correctly with zero Celery infrastructure
while still benefiting from async processing when Redis is available.

Start a worker (requires Redis):
    celery -A matchoracle worker -l info

Start the beat scheduler (periodic tasks):
    celery -A matchoracle beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchoracle.settings')

app = Celery('matchoracle')

# Read configuration from Django settings using the CELERY_ namespace prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Utility task — prints the request for debugging."""
    print(f'Request: {self.request!r}')

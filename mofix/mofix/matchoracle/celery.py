"""
matchoracle/celery.py
─────────────────────
Celery application instance for MatchOracle.

This module is imported by the Celery worker process.  The Django web process
does NOT import it directly — it only uses @shared_task decorators, which are
resolved lazily at task dispatch time.
"""

import os
from celery import Celery

# Tell Celery which Django settings module to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchoracle.settings')

app = Celery('matchoracle')

# Load Celery config from Django settings (keys prefixed with CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Utility task for verifying the worker is alive."""
    print(f'Request: {self.request!r}')

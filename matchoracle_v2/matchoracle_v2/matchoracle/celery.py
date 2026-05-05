"""Celery application for MatchOracle.

Workers are optional. When REDIS_URL is not set, CELERY_TASK_ALWAYS_EAGER=True
means every task runs synchronously in the calling process. The app works
correctly with zero Celery infrastructure.
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchoracle.settings')

app = Celery('matchoracle')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

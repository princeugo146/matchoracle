# Load the Celery app so @shared_task decorators are registered when Django starts.
# This import is guarded so the web process doesn't crash if celery is not installed.
try:
    from .celery import app as celery_app  # noqa: F401
    __all__ = ('celery_app',)
except ImportError:
    pass

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('SECRET_KEY', 'matchoracle-secret-key-2024-change-me')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'accounts',
    'core',
    'predictions',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'matchoracle.urls'
WSGI_APPLICATION = 'matchoracle.wsgi.application'
AUTH_USER_MODEL = 'accounts.User'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'core.context_processors.global_context',
    ]},
}]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 2592000
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

CSRF_TRUSTED_ORIGINS = [
    'https://matchoracle-production.up.railway.app',
    'https://*.railway.app',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

RAILWAY_PUBLIC_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_PUBLIC_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append('https://' + RAILWAY_PUBLIC_DOMAIN)

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = 'MatchOracle <' + os.environ.get('EMAIL_HOST_USER', 'noreply@matchoracle.com') + '>'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

MATCHORACLE = {
    'CURRENCY': 'NGN',
    'CURRENCY_SYMBOL': 'NGN',
    'PLANS': {
        'free':  {'name': 'Free',  'price': 0,     'duration_days': None, 'predictions_per_day': 3,  'api_access': False},
        'basic': {'name': 'Basic', 'price': 2000,  'duration_days': 30,   'predictions_per_day': 10, 'api_access': True},
        'pro':   {'name': 'Pro',   'price': 15000, 'duration_days': 365,  'predictions_per_day': 20, 'api_access': True},
    },
    'ANTHROPIC_API_KEY': os.environ.get('ANTHROPIC_API_KEY', ''),
    'FOOTBALL_API_KEY': os.environ.get('SPORTMONKS_API_KEY', os.environ.get('FOOTBALL_API_KEY', '')),
    'PAYSTACK_SECRET_KEY': os.environ.get('PAYSTACK_SECRET_KEY', ''),
    'PAYSTACK_PUBLIC_KEY': os.environ.get('PAYSTACK_PUBLIC_KEY', ''),
    'VERSION': '2.0.0',
}

# Static files directories (where Django looks for static files before collecting)
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# ─── Self-Learning System ─────────────────────────────────────────────────────
# Set LEARNING_ENABLED=True in your Railway environment to activate background
# learning tasks.  When False (default), all learning code is bypassed and the
# main app is completely unaffected.
LEARNING_ENABLED = os.environ.get('LEARNING_ENABLED', 'False') == 'True'

# ─── Celery Configuration ─────────────────────────────────────────────────────
# Requires a Redis instance.  Set REDIS_URL in your Railway environment.
# If Redis is not configured, Celery tasks simply won't run — the app still works.
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300          # 5 minutes max per task
CELERY_TASK_SOFT_TIME_LIMIT = 240     # soft limit triggers SoftTimeLimitExceeded

# Periodic task schedule (requires celery beat)
# Wrapped in try/except so the web process starts cleanly even without celery installed.
try:
    from celery.schedules import crontab as _crontab

    CELERY_BEAT_SCHEDULE = {
        # Check match results every 6 hours
        'check-match-results': {
            'task': 'predictions.learning_tasks.check_match_results',
            'schedule': _crontab(minute=0, hour='*/6'),
            'options': {'expires': 21600},
        },
        # Update team profiles daily at 03:00
        'update-team-profiles': {
            'task': 'predictions.learning_tasks.update_team_profiles',
            'schedule': _crontab(minute=0, hour=3),
            'options': {'expires': 86400},
        },
        # Adjust engine weights every Sunday at 04:00
        'adjust-engine-weights': {
            'task': 'predictions.learning_tasks.adjust_engine_weights',
            'schedule': _crontab(minute=0, hour=4, day_of_week='sunday'),
            'options': {'expires': 604800},
        },
        # Build tactical profiles every Sunday at 05:00
        'build-tactical-profiles': {
            'task': 'predictions.learning_tasks.build_tactical_profiles',
            'schedule': _crontab(minute=0, hour=5, day_of_week='sunday'),
            'options': {'expires': 604800},
        },
    }
except ImportError:
    CELERY_BEAT_SCHEDULE = {}

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('SECRET_KEY', 'matchoracle-secret-key-2024-change-me')
DEBUG = True  # TEMPORARY: hardcoded for diagnosing 500 on /admin/login/ — revert after fix
ALLOWED_HOSTS = [
    'matchoracle-production.up.railway.app',
    '*.railway.app',
    'localhost',
    '127.0.0.1',
]

RAILWAY_PUBLIC_DOMAIN_HOST = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_PUBLIC_DOMAIN_HOST and RAILWAY_PUBLIC_DOMAIN_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN_HOST)

INSTALLED_APPS = [
    'jazzmin',  # Must be first!
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

JAZZMIN_SETTINGS = {
    "site_title": "MatchOracle Admin",
    "site_header": "MatchOracle",
    "site_brand": "MatchOracle",
    "site_logo": None,
    "welcome_sign": "Welcome to MatchOracle Intelligence Dashboard",
    "copyright": "MatchOracle 2026",
    "search_model": ["accounts.User", "predictions.Prediction"],
    "topmenu_links": [
        {"name": "Live Site", "url": "https://matchoracle-production.up.railway.app", "new_window": True},
        {"name": "View Predictions", "model": "predictions.Prediction"},
        {"name": "View Users", "model": "accounts.User"},
    ],
    "usermenu_links": [
        {"name": "Live Site", "url": "https://matchoracle-production.up.railway.app", "new_window": True},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "order_with_respect_to": [
        "accounts",
        "predictions",
        "core",
    ],
    "icons": {
        "accounts.User": "fas fa-users",
        "accounts.Payment": "fas fa-credit-card",
        "predictions.Prediction": "fas fa-chart-line",
        "predictions.TeamProfile": "fas fa-shield-alt",
        "predictions.TeamRanking": "fas fa-trophy",
        "predictions.WeeklyTip": "fas fa-lightbulb",
        "predictions.EngineAccuracy": "fas fa-brain",
        "predictions.ConversationMemory": "fas fa-comments",
        "predictions.MatchResult": "fas fa-futbol",
        "auth.Group": "fas fa-users-cog",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "custom_css": None,
    "custom_js": None,
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
    },
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-dark",
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": True,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "darkly",
    "dark_mode_theme": "darkly",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
    "actions_sticky_top": True,
}

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
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

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

# ─── Authentication Backends ──────────────────────────────────────────────────
# EmailOrUsernameBackend lets admin staff log in with either their email
# address or their username (useful when a superuser was created via
# createsuperuser which sets a username rather than an email).
AUTHENTICATION_BACKENDS = [
    'accounts.auth_backend.EmailOrUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Password reset link expires after 1 hour (3600 seconds)
PASSWORD_RESET_TIMEOUT = 3600

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
CELERY_TASK_TIME_LIMIT = 30 * 60      # 30 minutes max per task
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60 # soft limit triggers SoftTimeLimitExceeded

# Broker connection resilience — prevents crash-looping when Redis is briefly unavailable
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

# Graceful shutdown — limit prefetch so in-flight tasks finish cleanly on SIGTERM
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

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
        # Reset daily prediction counters at midnight
        'reset-daily-counters': {
            'task': 'predictions.learning_tasks.reset_daily_counters',
            'schedule': _crontab(minute=0, hour=0),
            'options': {'expires': 86400},
        },
    }
except ImportError:
    CELERY_BEAT_SCHEDULE = {}

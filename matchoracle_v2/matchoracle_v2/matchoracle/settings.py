import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-this-matchoracle-v2')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'core',
    'accounts',
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
    'core.middleware.PerformanceMiddleware',
]

ROOT_URLCONF = 'matchoracle.urls'
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

WSGI_APPLICATION = 'matchoracle.wsgi.application'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20},
        'CONN_MAX_AGE': 60,
    }
}

AUTH_USER_MODEL = 'accounts.User'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Remove STATICFILES_DIRS to avoid the /app/static warning
# Static files are served from STATIC_ROOT only

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'matchoracle-cache',
        'TIMEOUT': 300,
        'OPTIONS': {'MAX_ENTRIES': 1000}
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400 * 30
SESSION_SAVE_EVERY_REQUEST = False

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticatedOrReadOnly',),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {'anon': '30/hour', 'user': '500/hour'},
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
}

CORS_ALLOW_ALL_ORIGINS = True

# ── CSRF & SECURITY ──
CSRF_TRUSTED_ORIGINS = [
    'https://matchoracle-production.up.railway.app',
    'https://*.railway.app',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Get the Railway URL from environment if available
RAILWAY_STATIC_URL = os.environ.get('RAILWAY_STATIC_URL', '')
RAILWAY_PUBLIC_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_PUBLIC_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RAILWAY_PUBLIC_DOMAIN}')

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = False  # Allow both HTTP and HTTPS
CSRF_COOKIE_SECURE = False     # Allow both HTTP and HTTPS
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = f'MatchOracle <{os.environ.get("EMAIL_HOST_USER", "noreply@matchoracle.com")}>'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

MATCHORACLE = {
    'FREE_TRIAL_LIMIT': 6,
    'CURRENCY': 'NGN',
    'CURRENCY_SYMBOL': '₦',
    'PLANS': {
        'free':  {'name': 'Free Trial',  'price': 0,     'duration_days': None, 'predictions_per_day': 6,   'api_access': False},
        'basic': {'name': 'Basic',       'price': 2000,  'duration_days': 30,   'predictions_per_day': 100, 'api_access': True},
        'pro':   {'name': 'Pro',         'price': 15000, 'duration_days': 365,  'predictions_per_day': 500, 'api_access': True},
    },
    'ANTHROPIC_API_KEY': os.environ.get('ANTHROPIC_API_KEY', ''),
    'FOOTBALL_API_KEY':  os.environ.get('FOOTBALL_API_KEY', ''),
    'PAYSTACK_SECRET_KEY': os.environ.get('PAYSTACK_SECRET_KEY', ''),
    'PAYSTACK_PUBLIC_KEY': os.environ.get('PAYSTACK_PUBLIC_KEY', ''),
    'VERSION': '2.0.0',
}

import base64
import hashlib
import os
from pathlib import Path
from datetime import timedelta
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# Load SECRET_KEY from environment; require it in production
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY environment variable is required.')

MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL', '').strip()
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '').strip()

def env_list(name: str, default: str = '') -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]

# Helper to read boolean environment variables
def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, str(default)).lower()
    return val in ('true', '1', 'yes')

DEBUG = env_bool('DEBUG', default=True)

_TEST_CREDENTIAL_ENCRYPTION_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(b'netpulse-test-only-credential-key').digest()
).decode('ascii')
CREDENTIAL_ENCRYPTION_KEY = os.getenv('CREDENTIAL_ENCRYPTION_KEY', '').strip()
if not CREDENTIAL_ENCRYPTION_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            'CREDENTIAL_ENCRYPTION_KEY is required when DEBUG is disabled.'
        )
    CREDENTIAL_ENCRYPTION_KEY = _TEST_CREDENTIAL_ENCRYPTION_KEY

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'daphne',
    'django.contrib.staticfiles',

    # Third party
    'channels',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    # Local apps
    'apps.tenants',
    'apps.routers',
    'apps.billing',
    'apps.analytics',
    'apps.vouchers',
    'apps.services',
    'apps.radius',
    'apps.operations',
    'apps.telemetry',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'


def _default_database_config(environ):
    if 'DATABASE_URL' in environ:
        database_url = environ['DATABASE_URL'].strip()
        if not database_url:
            raise ImproperlyConfigured('DATABASE_URL is set but empty.')
        try:
            config = dj_database_url.parse(database_url)
        except Exception:
            raise ImproperlyConfigured('DATABASE_URL is invalid or unsupported.') from None
        engine = config.get('ENGINE', '')
        if engine == 'django.db.backends.postgresql' and not (config.get('HOST') and config.get('NAME')):
            raise ImproperlyConfigured('DATABASE_URL must include a PostgreSQL host and database name.')
        if engine not in {'django.db.backends.postgresql', 'django.db.backends.sqlite3'}:
            raise ImproperlyConfigured('DATABASE_URL must use PostgreSQL or SQLite.')
        if engine == 'django.db.backends.sqlite3':
            options = config.get('OPTIONS') or {}
            options.setdefault('timeout', 5)
            config['OPTIONS'] = options
        return config
    postgres_keys = ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST', 'POSTGRES_PORT')
    if any(key in environ for key in postgres_keys):
        required_keys = ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST')
        missing_keys = [key for key in required_keys if not environ.get(key, '').strip()]
        if missing_keys:
            missing = ', '.join(missing_keys)
            raise ImproperlyConfigured(f'PostgreSQL environment configuration is incomplete; set {missing}.')
        port = environ.get('POSTGRES_PORT', '').strip()
        if port:
            try:
                if not 1 <= int(port) <= 65535:
                    raise ValueError
            except ValueError:
                raise ImproperlyConfigured('POSTGRES_PORT must be an integer between 1 and 65535.') from None
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': environ['POSTGRES_DB'],
            'USER': environ['POSTGRES_USER'],
            'PASSWORD': environ['POSTGRES_PASSWORD'],
            'HOST': environ['POSTGRES_HOST'],
            'PORT': port,
        }
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 5},
    }

DATABASES = {
    'default': _default_database_config(os.environ),
    'radius_db': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'radius_db.sqlite3',
        'OPTIONS': {'timeout': 5},
    }
}

DATABASE_ROUTERS = ['core.db_routers.RadiusRouter']

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS configuration
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = list(dict.fromkeys([
    'https://netpulse-backend-i9fv.onrender.com',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://192.168.1.107:5173',
    'http://192.168.1.107:8001',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    *env_list('CORS_ALLOWED_ORIGINS'),
]))
CORS_ALLOWED_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_ALLOW_HEADERS = ['*']
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([
    'https://netpulse-backend-i9fv.onrender.com',
    'http://localhost:5173',
    'http://localhost:5174',
    'http://127.0.0.1:5173',
    'http://192.168.1.107:5173',
    'http://192.168.1.107:5174',
    'http://192.168.100.8:5173',
    'http://192.168.100.8:8001',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    *env_list('CSRF_TRUSTED_ORIGINS'),
]))

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'mpesa_stk': '10/minute',
        'paystack_stk': '10/minute',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = True  # Added for local testing without Redis

# Production security settings (enabled when DEBUG is False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', default=not DEBUG)
    SESSION_COOKIE_SECURE = not DEBUG
    CSRF_COOKIE_SECURE = not DEBUG
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_REFERRER_POLICY = "same-origin"

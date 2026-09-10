import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Default superuser password for local development
os.environ.setdefault('DJANGO_SUPERUSER_PASSWORD', 'admin1234')

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = 'django-insecure-dummy-key-change-in-production'
DEBUG = True

# Reverse proxy configuration for Render
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

def env_list(name: str, default: str = '') -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]

def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '*')

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
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
    'apps.telemetry',
    'apps.vouchers',
    'apps.services',
    'apps.radius',
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

REDIS_URL = os.environ.get('REDIS_URL', '').strip()

if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    'radius_db': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'radius_db.sqlite3',
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
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = env_bool('CORS_ALLOW_ALL_ORIGINS', True)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env_list(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.107:5173,http://192.168.1.107:8001,http://localhost:8000,http://127.0.0.1:8000'
)
CORS_ALLOWED_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_ALLOW_HEADERS = ['*']
CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    'https://netpulse-backend-i9fv.onrender.com,http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://192.168.1.107:5173,http://192.168.1.107:5174,http://192.168.100.8:5173,http://192.168.100.8:8001,http://localhost:8000,http://127.0.0.1:8000'
)

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = True  # Added for local testing without Redis

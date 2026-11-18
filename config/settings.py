"""Configuración del Sistema de Reporte de Personas Desaparecidas y Avistamientos (Sincelejo).

Toda la configuración sensible se lee de variables de entorno (o de un archivo .env),
lo que permite desplegar varias instancias idénticas (RNF-06, escalabilidad horizontal).
"""
import base64
import hashlib
import os
import sys
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    path = BASE_DIR / '.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in ('1', 'true', 'yes', 'si', 'sí')


def env_int(name, default):
    return int(env(name, default))


DEBUG = env_bool('DEBUG', True)
SECRET_KEY = env('SECRET_KEY', 'dev-insecure-key-cambiar-en-produccion')
if not DEBUG and SECRET_KEY.startswith('dev-insecure'):
    raise ImproperlyConfigured('Defina SECRET_KEY en producción.')

ALLOWED_HOSTS = [h.strip() for h in env('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'accounts',
    'cases',
    'sightings',
    'moderation',
    'notifications',
    'audit',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'notifications.context_processors.unread_notifications',
    ]},
}]

# ---------------------------------------------------------------- Base de datos
if env('DB_ENGINE', 'postgres') == 'sqlite':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', 'desaparecidos'),
        'USER': env('DB_USER', 'desap'),
        'PASSWORD': env('DB_PASSWORD', 'desap'),
        'HOST': env('DB_HOST', 'localhost'),
        'PORT': env('DB_PORT', '5432'),
        'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', 60),
    }}

# ---------------------------------------------------------------- Autenticación
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'cases:home'
LOGOUT_REDIRECT_URL = 'cases:home'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
# Argon2/bcrypt serían ideales; PBKDF2 (hash robusto con sal) es el predeterminado de Django.
PASSWORD_RESET_TIMEOUT = 60 * 60            # HU-13 CA4: enlace de un solo uso, vigencia de 60 minutos

# HU-13 CA5: cierre de sesión por inactividad de 30 minutos
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# HU-13 CA3: bloqueo tras cinco intentos fallidos durante 15 minutos
LOGIN_MAX_FAILED_ATTEMPTS = env_int('LOGIN_MAX_FAILED_ATTEMPTS', 5)
LOGIN_LOCK_MINUTES = env_int('LOGIN_LOCK_MINUTES', 15)

# ---------------------------------------------------------------- Reglas de negocio configurables
SIGHTING_RATE_LIMIT_PER_HOUR = env_int('SIGHTING_RATE_LIMIT_PER_HOUR', 5)        # HU-04 CA6 / RNF-10
SIGHTING_IP_RATE_LIMIT_PER_HOUR = env_int('SIGHTING_IP_RATE_LIMIT_PER_HOUR', 15)  # RNF-10 por dirección IP
CONTENT_REPORT_ESCALATION_THRESHOLD = env_int('CONTENT_REPORT_ESCALATION_THRESHOLD', 3)  # HU-10 CA4
MODERATION_SLA_HOURS = env_int('MODERATION_SLA_HOURS', 24)
PUBLIC_MAP_COORD_DECIMALS = 3          # ≈ 110 m de precisión (HU-08 CA6)
PUBLIC_MAP_RADIUS_METERS = 100
CASES_PER_PAGE = 12
MAX_CASE_PHOTOS = 3
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 30 * 1024 * 1024
MAX_SIGHTING_MEDIA_FILES = 3
MAP_DEFAULT_CENTER = (9.3047, -75.3978)  # Sincelejo, Sucre
TRUST_X_FORWARDED_FOR = env_bool('TRUST_X_FORWARDED_FOR', False)

# ---------------------------------------------------------------- Archivos y cifrado en reposo (RNF-02)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
PRIVATE_MEDIA_ROOT = Path(env('PRIVATE_MEDIA_ROOT', str(BASE_DIR / 'private_media')))
if len(sys.argv) > 1 and sys.argv[1] == 'test':  # las pruebas nunca escriben en la carpeta real de archivos
    PRIVATE_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix='desap_test_'))
_default_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
FIELD_ENCRYPTION_KEY = env('FIELD_ENCRYPTION_KEY', _default_key)
if not DEBUG and FIELD_ENCRYPTION_KEY == _default_key:
    raise ImproperlyConfigured('Defina FIELD_ENCRYPTION_KEY (clave Fernet) en producción.')
DATA_UPLOAD_MAX_MEMORY_SIZE = 40 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# ---------------------------------------------------------------- Correo
EMAIL_BACKEND = env('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = env_int('EMAIL_PORT', 25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'Desaparecidos Sincelejo <no-responder@desaparecidos.local>')
SITE_URL = env('SITE_URL', 'http://localhost:8000')
EMAIL_SEND_ATTEMPTS = 3  # HU-07 CA5

# ---------------------------------------------------------------- Internacionalización
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------- Seguridad (RNF-02: TLS 1.2+ en tránsito)
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
# Django envía por defecto 'same-origin' (sin Referer hacia otros sitios). Los servidores de mapas de
# OpenStreetMap exigen el Referer y bloquean las teselas sin él, por eso el mapa salía en gris/vacío.
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'
CSRF_FAILURE_VIEW = 'core.views.csrf_failure'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': env('LOG_LEVEL', 'INFO')},
}

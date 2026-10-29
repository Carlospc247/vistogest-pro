# config/settings/production.py
from .base import *
import os

# ──────────────────────────────────────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────────────────────────────────────
DEBUG      = False
SECRET_KEY = os.environ['SECRET_KEY']        # obrigatório — KeyError se ausente
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()]

# ──────────────────────────────────────────────────────────────────────────────
# Base de Dados (Engine Multi-tenant)
# ──────────────────────────────────────────────────────────────────────────────


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL or "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "vistogest",
        "TIMEOUT": 300,
    },
    # Cache do BI (usado por _invalidar_cache_bi em apps/vendas/views.py)
    "B_I": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL or "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "vistogest-bi",
        "TIMEOUT": 300,
        # Isola as chaves por schema: sem isto, os dados de BI de uma
        # empresa podem aparecer noutra.
        "KEY_FUNCTION": "django_tenants.cache.make_key",
        "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
    },
}


DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME":     os.environ['DB_NAME'],
        "USER":     os.environ['DB_USER'],
        "PASSWORD": os.environ['DB_PASSWORD'],
        "HOST":     os.environ['DB_HOST'],
        "PORT":     os.environ.get('DB_PORT', '5432'),
        "CONN_MAX_AGE": 600,
    }
}


# ──────────────────────────────────────────────────────────────────────────────
# Segurança SSL/HTTPS
# ──────────────────────────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER     = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT         = True
SESSION_COOKIE_SECURE       = True
CSRF_COOKIE_SECURE          = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER   = True

# HSTS — só activar em produção (em dev não há HTTPS)
SECURE_HSTS_SECONDS            = 31536000  # 1 ano
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD            = True

# ──────────────────────────────────────────────────────────────────────────────
# Ficheiros estáticos
# ──────────────────────────────────────────────────────────────────────────────
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY':    os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
    'SECURE':     True,
}

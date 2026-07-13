from .base import *

DEBUG = True
SECRET_KEY = 'django-insecure-dev-key'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.sotarq.local', '.localhost']

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": "sotarq_vendor",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Em desenvolvimento, o email vai para o console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# Em settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
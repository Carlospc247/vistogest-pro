# config/settings/development.py
from .base import *

DEBUG = True

SECRET_KEY = os.getenv(
    'SECRET_KEY',
    'dev-insecure-key-nao-usar-em-producao-xk9!@#$%^&*()',
)

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.sotarq.local', '.localhost']

#DATABASES comentado — a configuração vem do .env via os.getenv() abaixo

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.getenv('DB_NAME', 'sotarq_vendor'),
        "USER": os.getenv('DB_USER', 'postgres'),
        "PASSWORD": os.getenv('DB_PASSWORD', 'postgres'),
        "HOST": os.getenv('DB_HOST', 'localhost'),
        "PORT": os.getenv('DB_PORT', '5432'),
    }
}

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ──────────────────────────────────────────────────────────────────────────────
# EMAIL — Desenvolvimento
# O backend ConsoleEmailBackend imprime o email no terminal em vez de enviar.
# Permite testar o fluxo completo de reset de senha sem servidor SMTP.
# ──────────────────────────────────────────────────────────────────────────────
EMAIL_BACKEND      = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'VistoGEST DEV <noreply@localhost>'

# Em desenvolvimento o link de reset aponta para localhost
# (o Django usa request.get_host() automaticamente — sem override necessário)

# Cache: django-redis com IGNORE_EXCEPTIONS já garante fallback automático
# para LocMemCache se o Redis não estiver disponível.
# (configurado em base.py)

# config/settings/base.py

import os
from pathlib import Path
import sys
from django_tenants.middleware.main import TenantMainMiddleware
from datetime import timedelta
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ──────────────────────────────────────────────────────────────────────────────
# AGT — Faturação Eletrónica (chaves e URLs da API)
# ──────────────────────────────────────────────────────────────────────────────
AGT_SOFTWARE_PRIVATE_KEY_PEM     = os.getenv('AGT_SOFTWARE_PRIVATE_KEY_PEM')
AGT_SOFTWARE_PRIVATE_KEY_PATH    = os.getenv('AGT_SOFTWARE_PRIVATE_KEY_PATH')
AGT_SOFTWARE_PRODUCT_ID          = os.getenv('AGT_SOFTWARE_PRODUCT_ID')
AGT_SOFTWARE_PRODUCT_VERSION     = os.getenv('AGT_SOFTWARE_PRODUCT_VERSION')
AGT_SOFTWARE_VALIDATION_NUMBER   = os.getenv('AGT_SOFTWARE_VALIDATION_NUMBER')
AGT_SOFTWARE_NAME                = os.getenv('AGT_SOFTWARE_NAME')
AGT_ENVIRONMENT                  = os.getenv('AGT_ENVIRONMENT')
AGT_BASE_URL_HOMOLOGACAO         = os.getenv('AGT_BASE_URL_HOMOLOGACAO')
AGT_BASE_URL_PRODUCAO            = os.getenv('AGT_BASE_URL_PRODUCAO')
AGT_QR_CODE_BASE_URL             = os.getenv('AGT_QR_CODE_BASE_URL')
AGT_CERTIFICATE_NUMBER           = os.getenv('AGT_CERTIFICATE_NUMBER')
AGT_PRODUCER_NIF                 = os.getenv('AGT_PRODUCER_NIF')
AGT_API_USERNAME                 = os.getenv('AGT_API_USERNAME')
AGT_API_PASSWORD                 = os.getenv('AGT_API_PASSWORD')
AGT_JWS_SOFTWARE_SIGNATURE       = os.getenv('AGT_JWS_SOFTWARE_SIGNATURE')
SOFTWARE_VALIDATION_NUMBER       = os.getenv('SOFTWARE_VALIDATION_NUMBER')
ASSINATURA_REGENERATE_COOLDOWN_MINUTES = int(os.getenv('ASSINATURA_REGENERATE_COOLDOWN_MINUTES', '60'))

# ──────────────────────────────────────────────────────────────────────────────
# CRIPTOGRAFIA
# ──────────────────────────────────────────────────────────────────────────────
# Chave AES para cifrar campos sensíveis (chaves AGT do contribuinte na BD)
AES_KEY = os.getenv('AES_KEY')

# Chave Fernet para encriptar credenciais de integrações externas
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

# Alias legado Fernet (compatibilidade)
ASSINATURA_FERNET_KEY = os.getenv('ASSINATURA_FERNET_KEY')

# ──────────────────────────────────────────────────────────────────────────────
# DATABASE ROUTER (django-tenants)
# ──────────────────────────────────────────────────────────────────────────────
DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "core.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# APPS
# ──────────────────────────────────────────────────────────────────────────────
SHARED_APPS = [
    "django_tenants",
    "apps.empresas",
    "apps.licenca",
    "apps.parceiros",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
    "apps.core",
    "apps.auditoria_publica",
]

TENANT_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "cloudinary",
    "cloudinary_storage",
    "rest_framework",
    "corsheaders",
    "crispy_forms",
    "django_celery_beat",
    "apps.core_tenants",
    "apps.produtos",
    "apps.analytics",
    "apps.fornecedores",
    "apps.estoque",
    "apps.clientes",
    "apps.vendas",
    "apps.funcionarios",
    "apps.servicos",
    "apps.financeiro",
    "apps.relatorios",
    "apps.configuracoes",
    "apps.integracoes",
    "apps.fiscal",
    "apps.saft",
    "apps.compras",
    "apps.site",
    "apps.comunicacao",
]

INSTALLED_APPS = SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]

# ──────────────────────────────────────────────────────────────────────────────
# TENANT DEBUG HELPER (apenas em DEBUG — patch no middleware)
# ──────────────────────────────────────────────────────────────────────────────
def _debug_get_tenant(self, domain_model, hostname):
    try:
        tenant = domain_model.objects.select_related('tenant').get(domain=hostname).tenant
        print(f"\n[SOTARQ_DEBUG] Schema: {tenant.schema_name} | Host: {hostname}")
        return tenant
    except domain_model.DoesNotExist:
        print(f"\n[SOTARQ_DEBUG] FALHA: '{hostname}' não encontrado na BD!")
        return None

TenantMainMiddleware.get_tenant = _debug_get_tenant

# ──────────────────────────────────────────────────────────────────────────────
# URL ROUTING (django-tenants)
# ──────────────────────────────────────────────────────────────────────────────
ROOT_URLCONF = 'config.urls_tenants'
PUBLIC_SCHEMA_URLCONF = 'config.urls_public'
TENANT_URLCONF        = 'config.urls_tenants' # pode eliminar
TENANT_MODEL          = "empresas.Empresa"
TENANT_DOMAIN_MODEL   = "empresas.Domain"
REMOVE_PORT_FROM_HOST   = True
SHOW_PUBLIC_IF_NO_TENANT = True
PUBLIC_SCHEMA_NAME      = 'public'
TENANT_CREATION_FUNCTIONS = ["django_tenants.utils.schema_exists"]
AUTO_CREATE_SCHEMA        = True

# ──────────────────────────────────────────────────────────────────────────────
# CELERY
# ──────────────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL        = os.getenv('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND    = os.getenv('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT    = ['json']
CELERY_TASK_SERIALIZER   = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE          = 'Africa/Luanda'
CELERY_ENABLE_UTC        = False
CELERY_REDIS_MAX_CONNECTIONS = 50

CELERY_BEAT_SCHEDULE = {
    'polling-estado-agt-15-minutos': {
        'task': 'fiscal.polling_global_agt',
        'schedule': 900.0,
    },
    'sincronizar-series-agt-diario': {
        'task': 'fiscal.sincronizar_series_agt_global',
        'schedule': crontab(hour=3, minute=0),
    },
    'expirar-licencas-parceiros-diario': {
        'task': 'parceiros.expirar_licencas_global',
        'schedule': crontab(hour=3, minute=30),
    },
    'backup_diario': {
        'task': 'apps.configuracoes.tasks.backup_automatico_diario',
        'schedule': crontab(hour=2, minute=0),
    },
    'verificar_margem_critica_diaria': {
        'task': 'apps.vendas.tasks.verificar_margem_critica',
        'schedule': timedelta(days=1),
    },
    'verificar_stock_critico_horario': {
        'task': 'apps.vendas.tasks.verificar_stock_critico',
        'schedule': timedelta(hours=1),
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# ──────────────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    # Rate Limiting — antes de AuthenticationMiddleware (sem queries ao BD)
    'apps.core.middleware.RateLimitLoginMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Middlewares de tenant (saltam automaticamente no schema public)
    'apps.core_tenants.middleware.ModuloAcessMiddleware',
    'apps.core_tenants.middleware.TwoFactorIPMiddleware',
    'apps.core.middleware.ThreadLocalUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.AccountsProfileRedirectMiddleware',
]

# ──────────────────────────────────────────────────────────────────────────────
# CLOUDINARY
# ──────────────────────────────────────────────────────────────────────────────
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY':    os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
    'SECURE':     True,
}

# ──────────────────────────────────────────────────────────────────────────────
# FICHEIROS ESTÁTICOS E MEDIA
# ──────────────────────────────────────────────────────────────────────────────
STATIC_URL       = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT      = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / "media"

# ──────────────────────────────────────────────────────────────────────────────
# CACHE — Redis
# ──────────────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv('REDIS_URL')

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

# ──────────────────────────────────────────────────────────────────────────────
# RATE LIMITING & BRUTE-FORCE PROTECTION
# ──────────────────────────────────────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS_IP          = int(os.getenv('LOGIN_MAX_ATTEMPTS_IP',          '10'))
LOGIN_MAX_ATTEMPTS_USER        = int(os.getenv('LOGIN_MAX_ATTEMPTS_USER',          '5'))
LOGIN_RATE_WINDOW_SECONDS      = int(os.getenv('LOGIN_RATE_WINDOW_SECONDS',      '300'))
LOGIN_LOCKOUT_DURATION_SECONDS = int(os.getenv('LOGIN_LOCKOUT_DURATION_SECONDS', '900'))
LOGIN_CAPTCHA_THRESHOLD        = int(os.getenv('LOGIN_CAPTCHA_THRESHOLD',          '3'))

# hCaptcha — chaves de teste oficiais como default (funcionam em DEV sem conta).
# Em PRODUÇÃO definir HCAPTCHA_SITE_KEY e HCAPTCHA_SECRET_KEY no .env.
HCAPTCHA_SITE_KEY   = os.getenv('HCAPTCHA_SITE_KEY',   '10000000-ffff-ffff-ffff-000000000001')
HCAPTCHA_SECRET_KEY = os.getenv('HCAPTCHA_SECRET_KEY', '0x0000000000000000000000000000000000000000')
HCAPTCHA_VERIFY_URL = 'https://hcaptcha.com/siteverify'

# Segredo para verificação HMAC de webhooks externos
GATEWAY_WEBHOOK_SECRET = os.getenv('GATEWAY_WEBHOOK_SECRET')

# ──────────────────────────────────────────────────────────────────────────────
# SEGURANÇA HTTP (cabeçalhos)
# HSTS, X-Frame-Options, etc. — activados aqui para ambos os ambientes.
# SESSION/CSRF SECURE e SSL_REDIRECT ficam em production.py.
# ──────────────────────────────────────────────────────────────────────────────
X_FRAME_OPTIONS     = "DENY"
REFERRER_POLICY     = "same-origin"

# ──────────────────────────────────────────────────────────────────────────────
# EMAIL
# O backend é definido aqui como SMTP (produção).
# development.py sobrepõe EMAIL_BACKEND para ConsoleEmailBackend.
# ──────────────────────────────────────────────────────────────────────────────
EMAIL_BACKEND       = os.getenv('EMAIL_BACKEND')
EMAIL_HOST          = os.getenv('EMAIL_HOST')
EMAIL_PORT          = int(os.getenv('EMAIL_PORT', '465'))
EMAIL_USE_SSL       = os.getenv('EMAIL_USE_SSL',  'True').lower()  == 'true'
EMAIL_USE_TLS       = os.getenv('EMAIL_USE_TLS',  'False').lower() == 'true'
EMAIL_HOST_USER     = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL  = os.getenv('DEFAULT_FROM_EMAIL')
SERVER_EMAIL        = os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
SUPPORT_EMAIL       = os.getenv('SUPPORT_EMAIL')

# ──────────────────────────────────────────────────────────────────────────────
# PASSWORD RESET
# ──────────────────────────────────────────────────────────────────────────────
# Duração do token de reset (segundos). Django default = 3 dias.
# Valor recomendado: 3600 (1 hora). Configurável via .env.
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', '3600'))

# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # context_processors de tenant — têm guard IS_PUBLIC, seguros em ambos
                "apps.core_tenants.context_processors.notifications_context",
                "apps.core_tenants.context_processors.notifications",
                "apps.core.context_processors.regime_context",
                "apps.core_tenants.context_processors.dashboard_data",
                "apps.configuracoes.context_processors.interface_prefs",
                "apps.core_tenants.context_processors.modules_context",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.i18n",
            ],
        },
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# DJANGO REST FRAMEWORK
# ──────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# WHATSAPP
# ──────────────────────────────────────────────────────────────────────────────
WHATSAPP_API_TOKEN = os.getenv('WHATSAPP_API_TOKEN')
WHATSAPP_API_URL   = os.getenv('WHATSAPP_API_URL')

# ──────────────────────────────────────────────────────────────────────────────
# OUTROS
# ──────────────────────────────────────────────────────────────────────────────
SESSION_COOKIE_DOMAIN   = None
CSRF_COOKIE_DOMAIN      = None
SESSION_COOKIE_HTTPONLY = True

WSGI_APPLICATION   = 'config.wsgi.application'
AUTH_USER_MODEL    = 'core.Usuario'
SITE_ID            = 1
LANGUAGE_CODE      = 'pt-pt'
TIME_ZONE          = 'Africa/Luanda'
USE_I18N           = True
USE_TZ             = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL           = 'core:login'
LOGIN_REDIRECT_URL  = 'core_tenants:dashboard'
LOGOUT_REDIRECT_URL = 'core:login'

DEFAULT_CANDIDATE_PASSWORD = os.getenv('DEFAULT_CANDIDATE_PASSWORD')
SENTRY_DSN = os.getenv('SENTRY_DSN')

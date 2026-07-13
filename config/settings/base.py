# base.py
import os
from pathlib import Path
import ssl
import sys
from django_tenants.middleware.main import TenantMainMiddleware
from datetime import timedelta
from celery.schedules import crontab
from dotenv import load_dotenv
import os

load_dotenv()

# Segurança Django
SECRET_KEY = os.getenv('SECRET_KEY')


raw_key = os.environ.get('SOTARQ_PRIVATE_KEY', '')# O replace corrige a string vinda do .env para o formato PEM real
SOTARQ_PRIVATE_KEY_BYTES = raw_key.replace('\\n', '\n').encode('utf-8')

AES_KEY = os.getenv('AES_KEY') # Criptografia de Dados (AES)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Roteador Multi-tenant (O Cérebro)
DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)



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
        "level": "INFO",  # <--- ESSENCIAL: mostra logger.info() # 'ERROR' para erros apenas
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "produtos": {  # substitui pelo nome do teu app se for outro
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}



SHARED_APPS = [
    "django_tenants",
    "apps.empresas",
    "apps.licenca",
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
    "apps.fiscal",
    "apps.saft",
    "apps.compras",
    "apps.site",
]

INSTALLED_APPS = SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]



def debug_get_tenant(self, domain_model, hostname):
    try:
        tenant = domain_model.objects.select_related('tenant').get(domain=hostname).tenant
        print(f"\n[SOTARQ_DEBUG] SUCESSO: Conectado ao Schema: {tenant.schema_name}")
        return tenant
    except domain_model.DoesNotExist:
        print(f"\n[SOTARQ_DEBUG] FALHA: Domínio '{hostname}' não existe no banco de dados!")
        return None

# Aplica o patch no middleware
TenantMainMiddleware.get_tenant = debug_get_tenant



# Configurações Multi-tenant de URL
ROOT_URLCONF = 'pharmassys.urls_public' 
PUBLIC_SCHEMA_URLCONF = 'pharmassys.urls_public'
TENANT_URLCONF = 'pharmassys.urls_tenants'

TENANT_MODEL = "empresas.Empresa"
TENANT_DOMAIN_MODEL = "empresas.Domain"

CELERY_BEAT_SCHEDULE = {
    'sincronizar-facturas-agt-cada-5-minutos': {
        'task': 'task_processar_polling_global_agt', # O Celery vai procurar esta função
        'schedule': 300.0,
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

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.TwoFactorIPMiddleware',
    'apps.core.middleware.ThreadLocalUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.AccountsProfileRedirectMiddleware',
]

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
    'SECURE': True,
}


# URL para acessar os arquivos via navegador
STATIC_URL = '/static/'

# Local onde o Django buscará arquivos estáticos durante o desenvolvimento
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Local onde o Django colocará todos os arquivos estáticos ao rodar 'collectstatic'
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Configuração para Media (Uploads como fotos de usuários/logos)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"


#REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")  # VAR na Render (SEM ?ssl_cert_reqs na URL!)


#CACHES = {
#    "default": {
#        "BACKEND": "django.core.cache.backends.redis.RedisCache",
#        "LOCATION": REDIS_URL,
#        "OPTIONS": {
#            "ssl_cert_reqs": ssl.CERT_REQUIRED,
#            "ssl_ca_certs": "/etc/ssl/certs/ca-certificates.crt",  # Ubuntu padrão
#        },
#        "TIMEOUT": 60 * 15,  # 15 min
#    },

#    "B_I": {  # dashboard BI que usas nas views
#        "BACKEND": "django.core.cache.backends.redis.RedisCache",
#        "LOCATION": REDIS_URL,
#        "OPTIONS": {
#            "ssl_cert_reqs": ssl.CERT_REQUIRED,
#        },
#        "TIMEOUT": 60 * 5,  # mais curto, BI deve ser fresco
#    }
#}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery
#CELERY_BROKER_URL = REDIS_URL
#CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Luanda'
CELERY_ENABLE_UTC = False
CELERY_REDIS_MAX_CONNECTIONS = 50

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "same-origin"

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.hostinger.com'           # Ex: smtp.sendgrid.net
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False
EMAIL_HOST_USER = 'geral@vistogest.pro' # Usuário do provedor
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD') # Senha ou API Key
DEFAULT_FROM_EMAIL = 'VistoGEST <suporte@vistogest.com>'
SUPPORT_EMAIL = 'suporte@vistogest.com'

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
                "apps.core.context_processors.notifications_context",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.i18n",
                "apps.core.context_processors.dashboard_data",
            ],
        },
    },
]


REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    #
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication', # Chave para o Mobile
        'rest_framework.authentication.SessionAuthentication', # Para o Navegador
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

ASSINATURA_REGENERATE_COOLDOWN_MINUTES = int(os.environ.get('ASSINATURA_REGENERATE_COOLDOWN_MINUTES', '60'))


WHATSAPP_API_TOKEN = os.getenv('WHATSAPP_API_TOKEN')
WHATSAPP_API_URL = os.getenv('WHATSAPP_API_URL')

REMOVE_PORT_FROM_HOST = True
SHOW_PUBLIC_IF_NO_TENANT = True
PUBLIC_SCHEMA_NAME = 'public'


SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_HTTPONLY = True

WSGI_APPLICATION = 'pharmassys.wsgi.application'
AUTH_USER_MODEL = 'core.Usuario'
SITE_ID = 1
LANGUAGE_CODE = 'pt-pt'
TIME_ZONE = 'Africa/Luanda'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



LOGIN_URL = 'core:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:login'
# funciona também com root_redirect em core/urls.py
# A ioutra forma é esta:
#LOGIN_URL = '/login/'
#LOGIN_REDIRECT_URL = '/'
#LOGOUT_REDIRECT_URL = '/login/'
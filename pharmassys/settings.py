import os
from pathlib import Path
import django
from django.core.management.utils import get_random_secret_key
from celery.schedules import crontab
from datetime import timedelta
import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary_storage.storage import RawMediaCloudinaryStorage
from cloudinary_storage.storage import MediaCloudinaryStorage
from cloudinary_storage.storage import StaticHashedCloudinaryStorage
import dj_database_url
import dj_database_url
import os
import logging
import sys


# =========================================
# Diretórios base
# =========================================
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================
# Core
# =========================================
SECRET_KEY = os.getenv('SECRET_KEY', get_random_secret_key())
#DEBUG = os.getenv("DEBUG", "False") == "True"
print("DATABASE_URL:", os.getenv("DATABASE_URL"))

#ALLOWED_HOSTS = [
#    'localhost',
#    '127.0.0.1',
#    'vistogest.pro',
#    'www.vistogest.pro',
#    'vistogestpro.onrender.com',
#    'www.vistogestpro.onrender.com',
#]
DEBUG = True
ALLOWED_HOSTS = ['*']

#LOGGING = {
#    'version': 1,
#    'disable_existing_loggers': False,
#    'handlers': {
#        'console': {'class': 'logging.StreamHandler'},
#    },
#    'root': {
#        'handlers': ['console'],
#        'level': 'ERROR',
#    },
#}

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
        "level": "INFO",  # <--- ESSENCIAL: mostra logger.info()
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


# =========================================
# Aplicações
# =========================================
INSTALLED_APPS = [
    # Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'whitenoise.runserver_nostatic',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',
    'cloudinary',
    'cloudinary_storage',

    # Terceiros
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'corsheaders',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'crispy_forms',
    'crispy_tailwind',
    'widget_tweaks',
    'django_filters',

    # Apps internos
    'apps.core',
    'apps.produtos',
    'apps.licenca',
    'apps.fornecedores',
    'apps.estoque',
    'apps.clientes',
    'apps.analytics',
    'apps.vendas',
    'apps.funcionarios',
    'apps.servicos',
    'apps.comandas',
    'apps.financeiro',
    'apps.relatorios',
    'apps.configuracoes',
    'apps.fiscal',
    'apps.saft',
    'apps.compras',
]



# =========================================
# Middleware
# =========================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'apps.core.middleware.AccountsProfileRedirectMiddleware',
]

ROOT_URLCONF = 'pharmassys.urls'
WSGI_APPLICATION = 'pharmassys.wsgi.application'


# =========================================
# Database (Render - PostgreSQL)
# =========================================

#DATABASE_URL = os.getenv("DATABASE_URL")

#if not DATABASE_URL:
#    raise Exception("❌ Variável DATABASE_URL não encontrada no ambiente Render!")

#DATABASES = {
#    'default': dj_database_url.parse(
#        DATABASE_URL,
#        conn_max_age=600,
#        ssl_require=True
#    )
#}
import os
import dj_database_url
from pathlib import Path


# ========================
# Banco de dados remoto
# ========================
# Defina diretamente a URL do banco remoto do Render
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://admin_master:YX3R9ZL8MBjzhTXqgHHZmauckw79zQMB@dpg-d46fc1fdiees739q5nvg-a.oregon-postgres.render.com:5432/vistogestpro")

if not DATABASE_URL or DATABASE_URL.strip() == "":
    raise Exception("❌ DATABASE_URL não encontrada ou vazia!")

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=True  # necessário no Render
    )
}

print("Conectando ao banco remoto:", DATABASES["default"]["NAME"])

# =========================================
# Cloudinary
# =========================================


CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
    'SECURE': True,
}


# Media e Static files
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
STATICFILES_STORAGE = 'cloudinary_storage.storage.StaticHashedCloudinaryStorage'

MEDIA_URL = '/media/'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"


# =========================================
# Celery (tarefas agendadas)
# =========================================
CELERY_BEAT_SCHEDULE = {
    'backup_diario': {
        'task': 'apps.configuracoes.tasks.backup_automatico_diario',
        'schedule': crontab(hour=2, minute=0),
    },
    'check_critical_margin_daily': {
        'task': 'apps.vendas.tasks.verificar_margem_critica',
        'schedule': timedelta(days=1),
    },
    'check_critical_stock_hourly': {
        'task': 'apps.vendas.tasks.verificar_stock_critico',
        'schedule': timedelta(hours=1),
    },
}


# =========================================
# Caches (Redis + BI)
# =========================================

# forneceido pelo upstash e adicionado no render em enviroments
REDIS_URL="rediss://default:AXYnAAIncDI1ZDc0MWE5MzkzNGU0NDVhOWI2NzMxYTc4NTgyNjg0ZXAyMzAyNDc@welcomed-jaguar-30247.upstash.io:6379"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "ssl_cert_reqs": None,  # SSL sem validação de certificado (necessário no Upstash)
        },
        "TIMEOUT": 60 * 15,
    },
    "B_I": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "ssl_cert_reqs": None,
        },
        "TIMEOUT": 60 * 60 * 2,
    },
}




# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": None}
CELERY_RESULT_BACKEND_USE_SSL = {"ssl_cert_reqs": None}


# =========================================
# Templates
# =========================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.notifications_context',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.i18n',
                'apps.core.context_processors.dashboard_data',
            ],
        },
    },
]

# =========================================
# Password validation
# =========================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =========================================
# Internacionalização
# =========================================
LANGUAGE_CODE = 'pt-pt'
TIME_ZONE = 'Africa/Luanda'
USE_I18N = True
USE_TZ = True

# =========================================
# Segurança dinâmica
# =========================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
else:
    SECURE_SSL_REDIRECT = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False


# =========================================
# Email
# =========================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.exemplo.com'
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_HOST_USER = 'geral@vistogest.pro'
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL="VistoGest <geral@vistogest.pro>"
SUPPORT_EMAIL='suporte@vistogest.pro'
#DEFAULT_FROM_EMAIL = 'no-reply@example.com
# =========================================
# Allauth (versão atualizada e sem warnings)
# =========================================
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Novo formato (Allauth >= 0.63)
ACCOUNT_LOGIN_METHODS = {"email"}  # apenas login via email
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"  # exige verificação por email

# =========================================
# CORS
# =========================================
CSRF_TRUSTED_ORIGINS = [
    'https://vistogest.pro',
    'https://www.vistogest.pro',
    'https://vistogestpro.onrender.com',
]


# =========================================
# REST Framework / JWT
# =========================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
}

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"  # se estiveres a usar tailwind
CRISPY_TEMPLATE_PACK = "tailwind"
#CRISPY_TEMPLATE_PACK = "bootstrap5"



PRODUCT_COMPANY_TAX_ID = "5002764377"  # NIF da empresa produtora do software
SOFTWARE_VALIDATION_NUMBER = "123/AGT/2019"  # Número de validação AGT (ex: "123/AGT/2024")
ERP_PRODUCT_ID = "SOTARQ SOFTWARE ERP"  # Ex: "MeuERP/MinhaEmpresa Lda"
ERP_PRODUCT_VERSION = "1.0.0"


ASSINATURA_FERNET_KEY = os.environ.get('ASSINATURA_FERNET_KEY')  # obrigatória
ASSINATURA_REGENERATE_COOLDOWN_MINUTES = int(os.environ.get('ASSINATURA_REGENERATE_COOLDOWN_MINUTES', '60'))

# =========================================
# Configuração padrão de PK
# =========================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.Usuario'

import os
from pathlib import Path
import django
#from django.core.management.utils import get_random_secret_key
from celery.schedules import crontab
from datetime import timedelta
import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary_storage.storage import RawMediaCloudinaryStorage
from cloudinary_storage.storage import MediaCloudinaryStorage
from cloudinary_storage.storage import StaticHashedCloudinaryStorage
import dj_database_url
import os
import logging
import sys
import ssl



# =========================================
# Diretórios base
# =========================================
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================
# Core
# =========================================
SECRET_KEY = os.getenv('SECRET_KEY')


DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = [
    'vistogest.pro',
    'www.vistogest.pro',
    'vistogestpro.onrender.com',
]

#DEBUG = True
#ALLOWED_HOSTS = ['*']


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


# =========================================
# Aplicações
# =========================================
INSTALLED_APPS = [
    # Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
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
    'django_celery_beat',

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
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
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


import os
import dj_database_url
from pathlib import Path


# ========================
# Banco de dados remoto
# ========================
# Defina diretamente a URL do banco remoto do Render
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não definido — abortando startup.")


DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=True  # necessário no Render
    )
}

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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
#STATICFILES_STORAGE = 'cloudinary_storage.storage.StaticHashedCloudinaryStorage' #Anteroior

MEDIA_URL = '/media/'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]  # ← ADICIONA ISTO


# ============================
# Scheduler de tarefas (Celery Beat)
# ============================
CELERY_BEAT_SCHEDULE = {
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

import ssl

broker_use_ssl = {
    "ssl_cert_reqs": ssl.CERT_REQUIRED   # obrigatório
}


# ============================
# Cache Redis (SSL)
# ============================
from django.core.cache import caches


import ssl
import os

REDIS_URL = os.getenv("REDIS_URL")  # VAR na Render (SEM ?ssl_cert_reqs na URL!)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
            "ssl_ca_certs": "/etc/ssl/certs/ca-certificates.crt",  # Ubuntu padrão
        },
        "TIMEOUT": 60 * 15,  # 15 min
    },

    "B_I": {  # dashboard BI que usas nas views
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
        },
        "TIMEOUT": 60 * 5,  # mais curto, BI deve ser fresco
    }
}


# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Luanda'
CELERY_ENABLE_UTC = False
CELERY_REDIS_MAX_CONNECTIONS = 50

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
EMAIL_HOST = 'smtp.hostinger.com'
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


ASSINATURA_REGENERATE_COOLDOWN_MINUTES = int(os.environ.get('ASSINATURA_REGENERATE_COOLDOWN_MINUTES', '60'))

# =========================================
# Configuração padrão de PK
# =========================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.Usuario'
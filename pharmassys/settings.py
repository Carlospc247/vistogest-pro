import os
from pathlib import Path
from django.core.management.utils import get_random_secret_key
import dj_database_url
from celery.schedules import crontab
from datetime import timedelta

# =========================================
# Diretórios base
# =========================================
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================
# Core
# =========================================
SECRET_KEY = os.getenv('SECRET_KEY', get_random_secret_key())
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = ['*']

# =========================================
# Logging
# =========================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'ERROR'},
}

# =========================================
# Apps
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
# Database - PostgreSQL local
# =========================================
# Se não houver DATABASE_URL, cria padrão local
DATABASE_URL = os.getenv("DATABASE_URL", f"postgres://admin_master:postgres@127.0.0.1:5432/vistogest_db")

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        #ssl_require=False  # Local não precisa de SSL
    )
}

# =========================================
# Cloudinary
# =========================================
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', 'demo'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY', 'demo'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', 'demo'),
    'SECURE': True,
}

DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage" if DEBUG else "cloudinary_storage.storage.MediaCloudinaryStorage"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage" if DEBUG else "cloudinary_storage.storage.StaticHashedCloudinaryStorage"

MEDIA_URL = '/media/'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

# =========================================
# Celery
# =========================================
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": None}
CELERY_RESULT_BACKEND_USE_SSL = {"ssl_cert_reqs": None}

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
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.i18n',
                'apps.core.context_processors.dashboard_data',
            ],
        },
    },
]

# =========================================
# Auth / Allauth
# =========================================
AUTH_USER_MODEL = 'core.Usuario'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"

# =========================================
# REST Framework
# =========================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
}

# =========================================
# Internacionalização
# =========================================
LANGUAGE_CODE = 'pt-pt'
TIME_ZONE = 'Africa/Luanda'
USE_I18N = True
USE_TZ = True

# =========================================
# Segurança
# =========================================
SECURE_SSL_REDIRECT = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

# =========================================
# Emails
# =========================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.exemplo.com'
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_HOST_USER = 'geral@vistogest.pro'
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = "VistoGest <geral@vistogest.pro>"
SUPPORT_EMAIL = 'suporte@vistogest.pro'

# =========================================
# CORS
# =========================================
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# =========================================
# Crispy Forms
# =========================================
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# =========================================
# Configurações ERP / Fiscal
# =========================================
PRODUCT_COMPANY_TAX_ID = "5002764377"
SOFTWARE_VALIDATION_NUMBER = "123/AGT/2019"
ERP_PRODUCT_ID = "SOTARQ SOFTWARE ERP"
ERP_PRODUCT_VERSION = "1.0.0"

ASSINATURA_FERNET_KEY = os.environ.get('ASSINATURA_FERNET_KEY', 'fernet_local')
ASSINATURA_REGENERATE_COOLDOWN_MINUTES = int(os.environ.get('ASSINATURA_REGENERATE_COOLDOWN_MINUTES', '60'))

# =========================================
# Configuração padrão de PK
# =========================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

from .base import *
import os

# =========================================
# Segurança e Core
# =========================================
DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# =========================================
# Banco de Dados (Engine Multi-tenant)
# =========================================
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.environ.get('DB_NAME'),
        "USER": os.environ.get('DB_USER'),
        "PASSWORD": os.environ.get('DB_PASSWORD'),
        "HOST": os.environ.get('DB_HOST'),
        "PORT": os.environ.get('DB_PORT', '5432'),
        "CONN_MAX_AGE": 600, # Otimização de conexão em produção
    }
}

# =========================================
# Segurança de Cookies e Protocolo SSL
# =========================================
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000 # 1 ano de HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# =========================================
# Performance de Arquivos Estáticos
# =========================================
# Whitenoise para servir estáticos eficientemente em produção
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Cloudinary para Media (Já herdado da base, mas garantindo chaves de prod)
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_NAME'),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}


# =========================================
# Email
# =========================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.hostinger.com'           # Ex: smtp.sendgrid.net
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False
EMAIL_HOST_USER = 'geral@vistogest.pro' # Usuário do provedor
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD') # Senha ou API Key
DEFAULT_FROM_EMAIL = 'VistoGEST <suporte@vistogest.com>'
SUPPORT_EMAIL = 'suporte@vistogest.com'


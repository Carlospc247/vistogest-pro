# vistogest-pro/pharmassys/tasks_celery.py
import ssl
import os
from celery import Celery
from django.conf import settings

# RIGOR: Em produção, o Render define essa variável automaticamente. 
# Se não estiver definida, ele usa development.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmassys.settings.development")

app = Celery("pharmassys")

# Configurações prefixadas com CELERY_ no settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# --- RIGOR SOTARQ: TRATAMENTO DE SSL DINÂMICO ---
# O Render exige SSL. O seu PC provavelmente não.
if os.environ.get('RENDER'): 
    app.conf.broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }
    app.conf.redis_backend_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }
else:
    # Localmente (Windows), desativamos para não dar erro de conexão
    app.conf.broker_use_ssl = False
    app.conf.redis_backend_use_ssl = False
#vistogest-pro/pharmassys/tasks_celery.py
import ssl, os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmassys.settings")

app = Celery("pharmassys")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# -- SSL obrigatório no Render:
app.conf.broker_use_ssl = {
    "ssl_cert_reqs": ssl.CERT_REQUIRED,
}

app.conf.redis_backend_use_ssl = {
    "ssl_cert_reqs": ssl.CERT_REQUIRED,
}

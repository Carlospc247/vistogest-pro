#vistogest-pro/pharmassys/task_celery.py
import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmassys.settings")

app = Celery("pharmassys")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

app.conf.broker_url = os.environ.get("REDIS_URL")
app.conf.result_backend = os.environ.get("REDIS_URL")
app.conf.accept_content = ["json"]
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.timezone = "Africa/Luanda"
app.conf.enable_utc = False

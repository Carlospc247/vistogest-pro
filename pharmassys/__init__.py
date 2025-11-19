# vistogest-pro/pharmassys/__init__.py

from .tasks_celery import app as celery_app

__all__ = ("celery_app",)

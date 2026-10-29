Para confirmar as tasks registadas:

powershell
celery -A config.tasks_celery inspect registered

Para testar o beat em desenvolvimento no Windows:

powershell
celery -A config.tasks_celery worker --pool=solo -l info
celery -A config.tasks_celery beat -l info
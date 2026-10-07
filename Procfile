# Procfile — VistoGest Pro / SOTARQ Software
# Usado por Render, Heroku e plataformas compatíveis com Procfile.
# Cada linha define um tipo de processo que a plataforma vai gerir.
#
# web:    Servidor HTTP principal (gunicorn). Responde aos pedidos HTTP.
#         $PORT é injectado automaticamente pela plataforma (Render/Heroku).
#
# worker: Celery Worker — processa tarefas assíncronas (AGT, emails, etc.).
#         A flag --without-gossip --without-mingle reduz o tráfego Redis.
#
# beat:   Celery Beat — agendador de tarefas periódicas.
#         IMPORTANTE: deve correr apenas 1 instância de beat em toda a infra.
#         Nunca escalar beat para múltiplas instâncias — causaria duplicação.
#
# release: Comando executado ANTES de iniciar os processos após cada deploy.
#          Aplica migrações automaticamente sem intervenção manual.

web:     gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
worker:  celery -A config.tasks_celery worker --loglevel=info --concurrency=2 --without-gossip --without-mingle
beat:    celery -A config.tasks_celery beat --loglevel=info --schedule=/tmp/celerybeat-schedule
release: python manage.py migrate_schemas --schema=public --noinput && python manage.py migrate --noinput

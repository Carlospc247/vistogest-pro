# apps/configuracoes/tasks.py
from celery import shared_task
from django.contrib.auth import get_user_model
from apps.configuracoes.services.backup_service import executar_backup, limpar_backups_antigos

@shared_task
def backup_automatico_diario():
    limpar_backups_antigos(dias=30)

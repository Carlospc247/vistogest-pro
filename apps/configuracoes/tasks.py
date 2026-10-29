# apps/configuracoes/tasks.py
from datetime import timedelta
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context
from apps.empresas.models import Empresa

@shared_task(bind=True, name="configuracoes.backup_automatico_diario", autoretry_for=(), max_retries=0)
def backup_automatico_diario(self):
    """Tarefa de verificação horária: executa backups de tenants cujo horário/frequência chegou."""
    from apps.configuracoes.models import BackupConfiguracao
    from apps.configuracoes.services.backup_service import executar_backup, limpar_backups_antigos
    agora=timezone.localtime(timezone.now())
    executados=[]; erros=[]
    for tenant in Empresa.objects.exclude(schema_name="public").iterator():
        try:
            with schema_context(tenant.schema_name):
                config=BackupConfiguracao.objects.first()
                if not config:
                    continue
                limpar_backups_antigos(config.dias_retencao_backup)
                if not config.backup_automatico or agora.time().replace(tzinfo=None) < config.horario_backup:
                    continue
                ultimo=config.ultimo_backup
                due=(ultimo is None or config.status_ultimo_backup == "erro")
                if ultimo and config.status_ultimo_backup != "erro":
                    ultimo_local=timezone.localtime(ultimo)
                    if config.frequencia_backup == "diario": due=ultimo_local.date() < agora.date()
                    elif config.frequencia_backup == "semanal": due=(agora.date()-ultimo_local.date()).days >= 7
                if not due:
                    continue
                try:
                    backup=executar_backup(tipo="automatico",user=None,tenant=tenant)
                    executados.append({"schema":tenant.schema_name,"backup_id":backup.pk})
                except Exception as exc:
                    erros.append({"schema":tenant.schema_name,"erro":str(exc)[:1000]})
                    if config.notificar_erro and config.email_notificacao:
                        try:
                            send_mail("Falha no backup automático",f"Empresa: {tenant.schema_name}\nErro: {exc}",getattr(settings,"DEFAULT_FROM_EMAIL",None),[config.email_notificacao],fail_silently=True)
                        except Exception: pass
        except Exception as exc:
            erros.append({"schema":tenant.schema_name,"erro":str(exc)[:1000]})
    return {"executados":executados,"erros":erros}

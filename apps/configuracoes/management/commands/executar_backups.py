import os
import subprocess
import zipfile
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_tenant_model, get_public_schema_name, schema_context

from apps.configuracoes.models import BackupConfiguracao, HistoricoBackup


class Command(BaseCommand):
    help = 'Executa backups automáticos para todos os tenants que têm a funcionalidade ativa.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Iniciando tarefa de backups automáticos...'))
        
        TenantModel = get_tenant_model()
        # Obtém todos os tenants ativos ignorando o schema público
        tenants = TenantModel.objects.exclude(schema_name=get_public_schema_name())

        for tenant in tenants:
            # Alterna a execução do ORM para o schema do tenant atual
            with schema_context(tenant.schema_name):
                # Busca a configuração de backup do tenant atual
                config = BackupConfiguracao.objects.filter(backup_automatico=True).first()
                if not config:
                    continue

                agora = timezone.localtime(timezone.now()).time()
                horario_backup = config.horario_backup
                
                # Verifica se está na janela de execução (margem de 15 minutos)
                if not (horario_backup.hour == agora.hour and horario_backup.minute <= agora.minute < horario_backup.minute + 15):
                    continue  # Pula se não for o horário configurado

                # Verifica a frequência considerando o histórico deste tenant
                ultimo_sucesso = HistoricoBackup.objects.filter(
                    tipo='automatico', 
                    status='sucesso'
                ).order_by('-data_criacao').first()

                if ultimo_sucesso:
                    dias_desde_ultimo = (timezone.now() - ultimo_sucesso.data_criacao).days
                    if config.frequencia_backup == 'diario' and dias_desde_ultimo < 1:
                        continue  # Já realizou backup hoje
                    if config.frequencia_backup == 'semanal' and dias_desde_ultimo < 7:
                        continue  # Já realizou backup esta semana

                self.stdout.write(f"  -> Processando backup para o tenant: {tenant.schema_name}")
                
                # Regista o histórico dentro do schema do tenant
                backup = HistoricoBackup.objects.create(
                    tipo='automatico',
                    status='processando',
                    solicitado_por=None  # Execução automática via script
                )
                
                try:
                    self._executar_backup_logica(backup, tenant)
                    self.stdout.write(self.style.SUCCESS(f"     Backup para {tenant.schema_name} concluído com sucesso."))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"     Falha no backup para {tenant.schema_name}: {e}"))
                    backup.status = 'erro'
                    backup.detalhes_erro = str(e)
                    backup.save()

        self.stdout.write(self.style.SUCCESS('Tarefa de backups automáticos finalizada.'))
    
    def _executar_backup_logica(self, backup_obj, tenant):
        """
        Executa o pg_dump filtrando apenas o schema do tenant informado.
        """
        db_settings = settings.DATABASES['default']
        backup_dir = getattr(settings, 'BACKUP_DIR', os.path.join(settings.BASE_DIR, 'backups'))
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"backup_auto_{tenant.schema_name}_{timestamp}"
        sql_filepath = os.path.join(backup_dir, f"{filename_base}.sql")
        zip_filepath = os.path.join(backup_dir, f"{filename_base}.zip")

        # Importante: A flag '-n <schema_name>' extrai apenas o schema deste tenant específico
        command = (
            f"pg_dump -U {db_settings['USER']} -h {db_settings['HOST']} "
            f"-p {db_settings['PORT']} -n {tenant.schema_name} {db_settings['NAME']} > {sql_filepath}"
        )
        
        env = os.environ.copy()
        env['PGPASSWORD'] = db_settings['PASSWORD']
        
        process = subprocess.run(command, shell=True, env=env, capture_output=True, text=True)

        if process.returncode != 0:
            raise Exception(f"Erro no pg_dump: {process.stderr}")

        # Compacta o ficheiro SQL
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(sql_filepath, os.path.basename(sql_filepath))
        
        # Remove o ficheiro .sql bruto após a compactação
        os.remove(sql_filepath)
        
        # Atualiza o registo de histórico no banco de dados do tenant
        backup_obj.status = 'sucesso'
        backup_obj.tamanho_ficheiro = os.path.getsize(zip_filepath)
        backup_obj.ficheiro_backup.name = os.path.relpath(zip_filepath, settings.MEDIA_ROOT)
        backup_obj.save()


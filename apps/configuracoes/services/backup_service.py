# apps/configuracoes/services/backup_service.py
import os
import subprocess
import zipfile
from datetime import datetime, timedelta
from django.conf import settings
from django.db import connection

from apps.configuracoes.models import HistoricoBackup


def executar_backup(tipo='manual', user=None, tenant=None):
    """
    Executa backup do schema do tenant ativo (ou informado) no PostgreSQL
    e grava o ficheiro compactado em MEDIA_ROOT/backups.
    Retorna o objeto HistoricoBackup.
    """
    # Se o tenant não for passado explicitamente, obtém do contexto da conexão ativa
    if tenant is None:
        tenant = getattr(connection, 'tenant', None)

    if not tenant:
        raise ValueError("Nenhum tenant ativo foi identificado para a execução do backup.")

    schema_name = tenant.schema_name
    db_settings = settings.DATABASES['default']
    backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename_base = f"backup_{schema_name}_{timestamp}"

    sql_filepath = os.path.join(backup_dir, f"{filename_base}.sql")
    zip_filepath = os.path.join(backup_dir, f"{filename_base}.zip")

    # Regista o histórico dentro do schema do tenant atual
    backup_obj = HistoricoBackup.objects.create(
        tipo=tipo,
        status='processando',
        solicitado_por=user
    )

    try:
        # --- Executar pg_dump apenas no schema do tenant ---
        command = (
            f'pg_dump -U {db_settings["USER"]} -h {db_settings["HOST"]} '
            f'-p {db_settings["PORT"]} -n {schema_name} {db_settings["NAME"]} > "{sql_filepath}"'
        )
        env = os.environ.copy()
        env['PGPASSWORD'] = db_settings['PASSWORD']
        
        process = subprocess.run(command, shell=True, env=env, capture_output=True, text=True)
        if process.returncode != 0:
            raise Exception(f"Erro no pg_dump: {process.stderr}")

        # --- Compactar o ficheiro SQL ---
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(sql_filepath, os.path.basename(sql_filepath))
        
        os.remove(sql_filepath)

        # --- Atualizar registo de backup ---
        backup_obj.status = 'sucesso'
        backup_obj.tamanho_ficheiro = os.path.getsize(zip_filepath)
        backup_obj.ficheiro_backup.name = os.path.join('backups', os.path.basename(zip_filepath))
        backup_obj.save()

        return backup_obj

    except Exception as e:
        backup_obj.status = 'erro'
        backup_obj.detalhes_erro = str(e)
        backup_obj.save()
        raise e


def limpar_backups_antigos(dias=30):
    """
    Apaga registos de histórico e ficheiros de backup mais antigos que 'dias'
    no schema do tenant atual.
    """
    limite = datetime.now() - timedelta(days=dias)
    antigos = HistoricoBackup.objects.filter(data_criacao__lt=limite)
    
    for b in antigos:
        try:
            if b.ficheiro_backup and os.path.isfile(b.ficheiro_backup.path):
                os.remove(b.ficheiro_backup.path)
        except Exception:
            pass
        b.delete()

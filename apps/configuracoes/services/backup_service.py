# apps/configuracoes/services/backup_services.py
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import connection
from django.utils import timezone
from apps.configuracoes.models import HistoricoBackup, BackupConfiguracao

def _tenant_atual(tenant=None):
    tenant = tenant or getattr(connection, "tenant", None)
    if not tenant or getattr(tenant,"schema_name","public")=="public":
        raise ValueError("Não foi possível identificar um tenant válido para o backup.")
    return tenant

def _db_params():
    cfg=settings.DATABASES["default"]
    if "postgresql" not in cfg.get("ENGINE", "").lower():
        raise RuntimeError("O backup desta implementação requer PostgreSQL e pg_dump/psql instalados no servidor.")
    return cfg

def _env_db(cfg):
    env=os.environ.copy()
    if cfg.get("PASSWORD") is not None: env["PGPASSWORD"]=str(cfg["PASSWORD"])
    return env

def _db_args(cfg):
    args=[]
    if cfg.get("USER"): args += ["--username", str(cfg["USER"])]
    if cfg.get("HOST"): args += ["--host", str(cfg["HOST"])]
    if cfg.get("PORT"): args += ["--port", str(cfg["PORT"])]
    args += ["--dbname", str(cfg["NAME"])]
    return args

def _media_root_for_tenant(schema_name):
    """Só inclui mídia se estiver explicitamente isolada por tenant em MEDIA_ROOT/tenants/<schema>."""
    base=getattr(settings,"MEDIA_ROOT",None)
    if not base: return None
    candidate=Path(base)/"tenants"/schema_name
    return candidate if candidate.is_dir() else None

def executar_backup(tipo="manual", user=None, tenant=None):
    """Gera ZIP com dump SQL do schema do tenant e, se existir, mídia local isolada desse tenant."""
    tenant=_tenant_atual(tenant); schema=tenant.schema_name; cfg=_db_params()
    stamp=timezone.now().strftime("%Y%m%d_%H%M%S")
    base=f"backup_{schema}_{stamp}"
    backup=HistoricoBackup.objects.create(tipo=tipo,status="processando",solicitado_por=user)
    config=BackupConfiguracao.objects.first()
    if config:
        config.status_ultimo_backup="em_andamento"
        config.save(update_fields=["status_ultimo_backup"])
    try:
        with tempfile.TemporaryDirectory(prefix="vistogest_backup_") as tmp:
            tmp_path=Path(tmp); sql_path=tmp_path/f"{base}.sql"; zip_path=tmp_path/f"{base}.zip"
            command=[getattr(settings,"PG_DUMP_PATH","pg_dump"), "--no-owner", "--no-privileges", "--clean", "--if-exists", "--format=plain", "--schema", schema, *_db_args(cfg), "--file", str(sql_path)]
            result=subprocess.run(command, env=_env_db(cfg), capture_output=True, text=True, timeout=getattr(settings,"BACKUP_PG_DUMP_TIMEOUT",3600), check=False)
            if result.returncode != 0:
                raise RuntimeError(f"pg_dump falhou (código {result.returncode}): {(result.stderr or result.stdout)[-4000:]}")
            if not sql_path.exists() or sql_path.stat().st_size == 0: raise RuntimeError("pg_dump terminou sem produzir um ficheiro SQL.")
            media_dir=_media_root_for_tenant(schema)
            manifest={"format_version":1,"schema_name":schema,"database_name":str(cfg.get("NAME","")),"created_at":timezone.now().isoformat(),"tipo":tipo,"database_dump":sql_path.name,"media_included":bool(media_dir),"media_folder":str(media_dir.relative_to(settings.MEDIA_ROOT)) if media_dir else None,"note":"O dump cobre o schema indicado. Ficheiros Cloudinary ou mídia partilhada não são exportados por este pacote."}
            with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
                archive.write(sql_path, arcname=sql_path.name)
                archive.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
                if media_dir:
                    for path in media_dir.rglob("*"):
                        if path.is_file(): archive.write(path,arcname=(Path("tenant_media")/path.relative_to(media_dir)).as_posix())
            relative=f"backups/{timezone.now():%Y/%m}/{base}.zip"
            with zip_path.open("rb") as file_obj:
                saved_name=default_storage.save(relative,File(file_obj, name=f"{base}.zip"))
            backup.ficheiro_backup.name=saved_name
            backup.status="sucesso"; backup.tamanho_ficheiro=default_storage.size(saved_name); backup.data_conclusao=timezone.now(); backup.detalhes_erro=""
            backup.save(update_fields=["ficheiro_backup","status","tamanho_ficheiro","data_conclusao","detalhes_erro"])
            config=BackupConfiguracao.objects.first()
            if config:
                config.ultimo_backup=timezone.now(); config.status_ultimo_backup="sucesso"; config.save(update_fields=["ultimo_backup","status_ultimo_backup"])
            return backup
    except Exception as exc:
        backup.status="erro"; backup.detalhes_erro=str(exc)[:10000]; backup.data_conclusao=timezone.now(); backup.save(update_fields=["status","detalhes_erro","data_conclusao"])
        config=BackupConfiguracao.objects.first()
        if config:
            config.ultimo_backup=timezone.now(); config.status_ultimo_backup="erro"; config.save(update_fields=["ultimo_backup","status_ultimo_backup"])
        raise

def limpar_backups_antigos(dias=30):
    """Remove ficheiros e registos de backup antigos do schema corrente."""
    limite=timezone.now()-timedelta(days=max(1,int(dias)))
    antigos=HistoricoBackup.objects.filter(data_criacao__lt=limite)
    total=0
    for backup in antigos.iterator():
        if backup.ficheiro_backup:
            try: default_storage.delete(backup.ficheiro_backup.name)
            except Exception: pass
        backup.delete(); total+=1
    return total

def restaurar_backup(backup, tenant=None):
    """Restaura um dump apenas no schema indicado; chama-se somente após autorização e confirmação explícitas."""
    tenant=_tenant_atual(tenant); cfg=_db_params()
    if not backup.ficheiro_backup or not default_storage.exists(backup.ficheiro_backup.name): raise FileNotFoundError("O ficheiro do backup não existe.")
    with tempfile.TemporaryDirectory(prefix="vistogest_restore_") as tmp:
        tmp_path=Path(tmp); zip_path=tmp_path/"backup.zip"
        with default_storage.open(backup.ficheiro_backup.name,"rb") as source, zip_path.open("wb") as target: shutil.copyfileobj(source,target)
        with zipfile.ZipFile(zip_path,"r") as archive:
            names=archive.namelist()
            if "manifest.json" not in names: raise ValueError("Backup não tem manifesto; não é seguro restaurar automaticamente.")
            manifest=json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("schema_name") != tenant.schema_name: raise PermissionError("O backup pertence a outro schema.")
            sql_name=manifest.get("database_dump")
            if not sql_name or sql_name not in names or Path(sql_name).name != sql_name: raise ValueError("O arquivo SQL do backup é inválido.")
            sql_path=tmp_path/sql_name
            sql_path.write_bytes(archive.read(sql_name))
        command=[getattr(settings,"PSQL_PATH","psql"),"--no-psqlrc","--set","ON_ERROR_STOP=1","--single-transaction",*_db_args(cfg),"--file",str(sql_path)]
        result=subprocess.run(command,env=_env_db(cfg),capture_output=True,text=True,timeout=getattr(settings,"BACKUP_PSQL_TIMEOUT",3600),check=False)
        if result.returncode != 0: raise RuntimeError(f"Restauração falhou (código {result.returncode}): {(result.stderr or result.stdout)[-4000:]}")
        if manifest.get("media_included"):
            target=Path(settings.MEDIA_ROOT)/"tenants"/tenant.schema_name
            staged=tmp_path/"restored_tenant_media"
            staged.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path,"r") as archive:
                for member in archive.namelist():
                    if not member.startswith("tenant_media/") or member.endswith("/"):
                        continue
                    relative=Path(member[len("tenant_media/"):])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("O backup contém um caminho de mídia inválido.")
                    destination=staged/relative
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(archive.read(member))
            old=tmp_path/"previous_tenant_media"
            if target.exists(): shutil.move(str(target),str(old))
            try:
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.move(str(staged),str(target))
            except Exception:
                if old.exists() and not target.exists(): shutil.move(str(old),str(target))
                raise
        return manifest

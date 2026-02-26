#apps/fiscal/tasks.py
import logging
import os
import zipfile
from datetime import datetime, date, timedelta
from typing import Dict, List
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from apps.empresas.models import Empresa
from apps.fiscal.models import DocumentoFiscal, AssinaturaDigital, RetencaoFonte
from apps.fiscal.services.polling_service import FiscalPollingService
from apps.fiscal.services.utils import SAFTExportService
from django.apps import apps
from django_tenants.utils import schema_context
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService



logger = logging.getLogger('fiscal.tasks')

# ============================================================
# 1. CORE: SINCRONIZAÇÃO EM TEMPO REAL (POLLING AGT)
# ============================================================


# ============================================================
# 3. CORE: ASSINATURA DIGITAL RSA (SEGURANÇA SOTARQ)
# ============================================================

@shared_task(name="processar_assinatura_documento", bind=True, max_retries=3)
def processar_assinatura_documento(self, empresa_id, documento_id, documento_type, dados_documento):
    """
    Assina digitalmente faturas e recibos de forma assíncrona.
    Evita que o tempo de processamento RSA (lento) trave o PDV do cliente.
    """
    try:
        empresa = Empresa.objects.get(id=empresa_id)
        
        # RIGOR SOTARQ: Muda para o schema do inquilino para gravar o hash no documento certo
        with schema_context(empresa.schema_name):
            # Obtém o model dinamicamente (Venda, FaturaCredito, etc.)
            # Nota: Centralizamos na app 'vendas' conforme sua estrutura de signals
            Model = apps.get_model(app_label='vendas', model_name=documento_type)
            instance = Model.objects.get(id=documento_id)
            
            # Chama o AssinaturaDigitalService que o senhor já possui
            # O service faz o trabalho pesado de RSA e gestão da cadeia de hashes
            resultado = AssinaturaDigitalService.assinar_documento(empresa, dados_documento)
            
            # Grava os selos AGT no banco de dados do tenant
            instance.hash_documento = resultado['hash']
            instance.assinatura_digital = resultado['assinatura']
            instance.hash_anterior = resultado['hash_anterior']
            instance.atcud = resultado['atcud']
            
            # RIGOR: update_fields impede que signals post_save disparem de novo (loop infinito)
            instance.save(update_fields=['hash_documento', 'assinatura_digital', 'hash_anterior', 'atcud'])
            
            logger.info(f"✔ Sucesso SOTARQ: Documento {documento_type} {documento_id} assinado.")

    except Exception as exc:
        logger.error(f"✘ Erro Crítico na Assinatura {documento_id}: {exc}")
        # Tenta novamente em 60 segundos se o erro for temporário
        raise self.retry(exc=exc, countdown=60)



@shared_task(name="task_processar_polling_global_agt")
def task_processar_polling_global_agt():
    """
    Varre todas as empresas em busca de RequestIDs pendentes de validação na AGT.
    Conforme regras de processamento assíncrono da Faturação Eletrónica.
    """
    docs_pendentes = DocumentoFiscal.objects.filter(
        status='confirmed',
        metadados__has_key='request_id_agt'
    ).exclude(status__in=['posted', 'cancelled']).distinct('empresa')

    empresas_ids = docs_pendentes.values_list('empresa_id', flat=True)

    for empresa_id in empresas_ids:
        task_sincronizar_empresa_agt.delay(empresa_id)


@shared_task(name="task_sincronizar_empresa_agt")
def task_sincronizar_empresa_agt(empresa_id):
    """Sincroniza RequestIDs de uma empresa específica."""
    try:
        empresa = Empresa.objects.get(pk=empresa_id)
        polling_service = FiscalPollingService(empresa)

        docs = DocumentoFiscal.objects.filter(
            empresa=empresa,
            status='confirmed',
            metadados__has_key='request_id_agt'
        ).exclude(status__in=['posted', 'cancelled'])

        # Extrai RequestIDs únicos para evitar chamadas redundantes à API
        request_ids = {d.metadados.get('request_id_agt') for d in docs if d.metadados.get('request_id_agt')}

        for rid in request_ids:
            logger.info(f"Polling AGT - Empresa: {empresa.nome} | RID: {rid}")
            resultado = polling_service.consultar_estado_documento(rid)
            
            if resultado == "FINISHED":
                logger.info(f"Sincronização FINALIZADA para RID: {rid}")
            elif resultado == "PROCESSING":
                logger.info(f"RID {rid} ainda em processamento na AGT.")

    except Empresa.DoesNotExist:
        logger.error(f"Empresa ID {empresa_id} inexistente.")
    except Exception as e:
        logger.exception(f"Erro no polling da empresa {empresa_id}: {e}")

# ============================================================
# 2. MANUTENÇÃO: BACKUPS E LIMPEZA (ENTERPRISE STANDARD)
# ============================================================

@shared_task
def limpeza_arquivos_temporarios():
    """Remove exports de SAF-T e backups antigos (>30 dias) para poupar disco."""
    try:
        dias_manter = 30
        diretorios = [
            os.path.join(settings.MEDIA_ROOT, 'saft_exports'),
            os.path.join(settings.MEDIA_ROOT, 'backups_fiscal')
        ]
        
        removidos = 0
        for diretorio in diretorios:
            if not os.path.exists(diretorio): continue
            for filename in os.listdir(diretorio):
                file_path = os.path.join(diretorio, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if (datetime.now() - file_time).days > dias_manter:
                        os.remove(file_path)
                        removidos += 1
        return {'success': True, 'arquivos_removidos': removidos}
    except Exception as e:
        logger.error(f"Erro na limpeza: {e}")
        return {'success': False, 'error': str(e)}

# ============================================================
# 3. RELATÓRIOS E EXPORTAÇÕES AGENDADAS
# ============================================================

@shared_task(bind=True)
def gerar_saft_async(self, empresa_id: int, data_inicio: str, data_fim: str):
    """Gera o XML SAF-T AO 1.01 de forma assíncrona para não travar o worker principal."""
    try:
        empresa = Empresa.objects.get(id=empresa_id)
        di = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        df = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        xml_content = SAFTExportService.gerar_saft_ao(empresa, di, df)
        
        filename = f"SAFT_AO_{empresa.nif}_{data_inicio}_{data_fim}.xml"
        path = os.path.join(settings.MEDIA_ROOT, 'saft_exports', filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'wb') as f:
            f.write(xml_content if isinstance(xml_content, bytes) else xml_content.encode('utf-8'))
            
        return {'success': True, 'file': filename}
    except Exception as e:
        logger.error(f"Erro SAF-T Async: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name="task_backup_fiscal_diario_global", bind=True, max_retries=3)
def task_backup_fiscal_diario_global(self):
    """
    Orquestrador de Backup Fiscal Diário.
    Varre todas as empresas ativas e gera snapshots de segurança.
    """
    empresas = Empresa.objects.filter(ativo=True)
    logs_sucesso = 0
    logs_erro = 0

    for empresa in empresas:
        try:
            # Chamada direta ao signal de backup
            signal_backup(empresa)
            logs_sucesso += 1
            logger.info(f"Backup automático concluído: {empresa.nome}")
        except Exception as e:
            logs_erro += 1
            logger.error(f"Erro no backup automático da empresa {empresa.nome}: {e}")

    return {
        "status": "concluido",
        "sucesso": logs_sucesso,
        "falhas": logs_erro,
        "data": timezone.now().isoformat()
    }



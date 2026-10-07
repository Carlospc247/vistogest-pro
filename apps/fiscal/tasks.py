# apps/fiscal/tasks.py
"""
Tarefas Celery para o módulo fiscal — Faturação Electrónica AGT.

Fase 10 do PLANO_IMPLEMENTACAO.md:
  - submeter_fatura_agt: submete um DocumentoFiscal à API AGT.
  - polling_estado_agt: consulta o estado de documentos pendentes.
  - sincronizar_series_agt: sincroniza as séries com a AGT.

Execução assíncrona (design do Decreto 683/25, Modelo Validação a Posteriori):
  1. O documento é emitido e assinado localmente de forma síncrona.
  2. A submissão à AGT é assíncrona — vai para fila Celery.
  3. O polling verifica o resultado diferido a cada 15 minutos.

Contexto multi-tenant: cada tarefa recebe o `schema_name` do tenant e
activa o schema correcto antes de executar — sem que a fila de mensagens
misture dados de tenants diferentes.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger('fiscal.tasks')


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — Submeter fatura à AGT
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5 minutos entre retentativas
    name='fiscal.submeter_fatura_agt',
)
def submeter_fatura_agt(self, schema_name: str, documento_fiscal_id: int):
    """
    Submete um DocumentoFiscal à API AGT (/registarFactura).

    Args:
        schema_name:         Schema PostgreSQL do tenant (ex.: 'empresa_abc').
        documento_fiscal_id: PK do DocumentoFiscal a submeter.

    Comportamento:
        - Activa o schema do tenant antes de qualquer acesso à BD.
        - Só submete documentos com status 'confirmed' e sem requestID.
        - Em caso de erro de rede, recoloca na fila (max 3 retentativas).
        - Em caso de erro de negócio (AGT recusa), regista nos metadados
          e NÃO recoloca (o operador terá de corrigir manualmente).
    """
    with schema_context(schema_name):
        from apps.fiscal.models import DocumentoFiscal
        from apps.fiscal.services.submissao_fatura_service import SubmissaoFaturaService
        from apps.fiscal.services.utils import FiscalServiceError
        import requests

        try:
            doc = DocumentoFiscal.objects.get(pk=documento_fiscal_id)
        except DocumentoFiscal.DoesNotExist:
            logger.error(
                "[%s] submeter_fatura_agt: DocumentoFiscal #%d não encontrado.",
                schema_name, documento_fiscal_id,
            )
            return {'success': False, 'error': 'DocumentoFiscal não encontrado'}

        # Verificar se já foi submetido
        if doc.metadados.get('request_id_agt'):
            logger.info(
                "[%s] DocumentoFiscal #%d já submetido (requestID=%s). A saltar.",
                schema_name, documento_fiscal_id, doc.metadados['request_id_agt'],
            )
            return {'success': True, 'already_submitted': True}

        # Só submete documentos confirmados
        if doc.status != 'confirmed':
            logger.warning(
                "[%s] DocumentoFiscal #%d tem status '%s' — não pode ser submetido.",
                schema_name, documento_fiscal_id, doc.status,
            )
            return {'success': False, 'error': f"Status inválido para submissão: {doc.status}"}

        try:
            service = SubmissaoFaturaService()
            resultado = service.submeter_documento(doc)
            logger.info(
                "[%s] DocumentoFiscal #%d submetido. RequestID: %s",
                schema_name, documento_fiscal_id, resultado.get('requestID'),
            )
            return resultado

        except requests.exceptions.RequestException as exc:
            # Erro de rede — retentar
            logger.warning(
                "[%s] Erro de rede ao submeter #%d: %s. Retentativa %d/%d.",
                schema_name, documento_fiscal_id, exc,
                self.request.retries + 1, self.max_retries,
            )
            raise self.retry(exc=exc)

        except FiscalServiceError as exc:
            # Erro de negócio — não retentar, registar nos metadados
            logger.error(
                "[%s] Erro de negócio ao submeter #%d: %s",
                schema_name, documento_fiscal_id, exc,
            )
            if not doc.metadados:
                doc.metadados = {}
            doc.metadados['erro_submissao_agt'] = str(exc)
            doc.metadados['erro_submissao_ts'] = timezone.now().isoformat()
            doc.save(update_fields=['metadados'])
            return {'success': False, 'error': str(exc)}

        except Exception as exc:
            logger.exception(
                "[%s] Erro inesperado ao submeter #%d: %s",
                schema_name, documento_fiscal_id, exc,
            )
            raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — Polling do estado de validação AGT
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=900,   # 15 minutos
    name='fiscal.polling_estado_agt',
)
def polling_estado_agt(self, schema_name: str, documento_fiscal_id: int):
    """
    Consulta o estado de validação de um DocumentoFiscal junto da AGT
    (/obterEstado) e actualiza o status local.

    Deve ser agendado ~5 minutos após submeter_fatura_agt ter registado
    o requestID, e repetido a cada 15 minutos enquanto o estado for
    'PROCESSING' (resultCode=8).

    Args:
        schema_name:         Schema PostgreSQL do tenant.
        documento_fiscal_id: PK do DocumentoFiscal a consultar.
    """
    with schema_context(schema_name):
        from apps.fiscal.models import DocumentoFiscal
        from apps.fiscal.services.polling_service import FiscalPollingService
        import requests

        try:
            doc = DocumentoFiscal.objects.get(pk=documento_fiscal_id)
        except DocumentoFiscal.DoesNotExist:
            logger.error(
                "[%s] polling_estado_agt: DocumentoFiscal #%d não encontrado.",
                schema_name, documento_fiscal_id,
            )
            return

        request_id = (doc.metadados or {}).get('request_id_agt')
        if not request_id:
            logger.warning(
                "[%s] DocumentoFiscal #%d sem requestID — polling impossível.",
                schema_name, documento_fiscal_id,
            )
            return

        # Não faz polling de documentos já validados ou inválidos
        if doc.status in ('posted', 'cancelled'):
            logger.info(
                "[%s] DocumentoFiscal #%d já tem estado final '%s'. A saltar.",
                schema_name, documento_fiscal_id, doc.status,
            )
            return

        try:
            service = FiscalPollingService()
            resultado = service.consultar_estado_documento(request_id)

            if resultado == 'PROCESSING':
                logger.info(
                    "[%s] DocumentoFiscal #%d ainda em processamento. Reagendar polling.",
                    schema_name, documento_fiscal_id,
                )
                # Recolocar na fila para tentar novamente em 15 minutos
                raise self.retry(countdown=900)

            elif resultado == 'FINISHED':
                logger.info(
                    "[%s] DocumentoFiscal #%d processado pela AGT.",
                    schema_name, documento_fiscal_id,
                )

            else:
                logger.warning(
                    "[%s] DocumentoFiscal #%d — resultado inesperado do polling: %s",
                    schema_name, documento_fiscal_id, resultado,
                )

        except self.MaxRetriesExceededError:
            logger.error(
                "[%s] DocumentoFiscal #%d — máximo de retentativas de polling atingido.",
                schema_name, documento_fiscal_id,
            )
            if not doc.metadados:
                doc.metadados = {}
            doc.metadados['polling_max_retries'] = True
            doc.save(update_fields=['metadados'])

        except requests.exceptions.RequestException as exc:
            logger.warning(
                "[%s] Erro de rede no polling de #%d: %s",
                schema_name, documento_fiscal_id, exc,
            )
            raise self.retry(exc=exc)

        except Exception as exc:
            logger.exception(
                "[%s] Erro inesperado no polling de #%d: %s",
                schema_name, documento_fiscal_id, exc,
            )
            raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 — Sincronizar séries com a AGT (periódica)
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(
    name='fiscal.sincronizar_series_agt',
)
def sincronizar_series_agt(schema_name: str):
    """
    Sincroniza as séries de numeração com a AGT (/listarSeries) para um tenant.
    Deve correr uma vez por dia, de madrugada.

    Args:
        schema_name: Schema PostgreSQL do tenant.
    """
    with schema_context(schema_name):
        from apps.fiscal.services.serie_fiscal_service import SerieFiscalService
        from apps.fiscal.services.utils import FiscalServiceError

        try:
            service = SerieFiscalService()
            series = service.sincronizar_series()
            logger.info(
                "[%s] sincronizar_series_agt: %d série(s) sincronizadas.",
                schema_name, len(series),
            )
            return {'success': True, 'total': len(series)}
        except FiscalServiceError as exc:
            logger.error(
                "[%s] sincronizar_series_agt: FiscalServiceError — %s",
                schema_name, exc,
            )
            return {'success': False, 'error': str(exc)}
        except Exception as exc:
            logger.exception(
                "[%s] sincronizar_series_agt: erro inesperado — %s",
                schema_name, exc,
            )
            return {'success': False, 'error': str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de agendamento — usados pelas views quando um doc é confirmado
# ─────────────────────────────────────────────────────────────────────────────

def agendar_submissao(schema_name: str, documento_fiscal_id: int, atraso_minutos: int = 5):
    """
    Agenda a submissão de um documento à AGT com um atraso (default: 5 minutos).
    Regra AGT: prazo de 24 horas sem penalização.

    Chame esta função após confirmar o DocumentoFiscal:
        from apps.fiscal.tasks import agendar_submissao
        agendar_submissao(connection.schema_name, doc.pk)
    """
    submeter_fatura_agt.apply_async(
        args=[schema_name, documento_fiscal_id],
        countdown=atraso_minutos * 60,
    )
    # Agendar polling 5 minutos depois da submissão
    polling_estado_agt.apply_async(
        args=[schema_name, documento_fiscal_id],
        countdown=(atraso_minutos + 5) * 60,
    )
    logger.info(
        "[%s] DocumentoFiscal #%d agendado para submissão em %d min.",
        schema_name, documento_fiscal_id, atraso_minutos,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 4 — Processar assinatura de documento fiscal (chamada pelo signal)
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='fiscal.processar_assinatura_documento',
)
def processar_assinatura_documento(
    self,
    schema_name: str,
    documento_id: int,
    documento_type: str,
    dados_documento: dict,
):
    """
    Processa a assinatura JWS de um documento fiscal de forma assíncrona.

    Chamado pelo signal `assinar_documento_fiscal` em signals.py logo após
    a criação de uma Venda, FaturaCredito, NotaCredito, NotaDebito ou Recibo.

    Args:
        schema_name:     Schema PostgreSQL do tenant (ex.: 'empresa_abc').
        documento_id:    PK do documento no modelo respectivo.
        documento_type:  Nome do modelo Django (ex.: 'Venda', 'FaturaCredito').
        dados_documento: Dict com campos obrigatórios AGT para a assinatura
                         (tipo_documento, serie, numero, data, valor_total).

    Comportamento:
        - Activa o schema do tenant antes de qualquer acesso à BD.
        - Obtém a configuração de assinatura digital do tenant.
        - Se a chave do contribuinte não estiver configurada, regista aviso
          e termina sem erro (o utilizador configurará depois).
        - Assina os dados e regista o hash na cadeia interna.
        - Em caso de erro de rede/serviço, recoloca na fila (max 3 tentativas).
    """
    with schema_context(schema_name):
        from apps.fiscal.models import AssinaturaDigital
        from apps.fiscal.services.assinatura_service import (
            AssinaturaDigitalService,
            FiscalServiceError,
        )

        try:
            config = AssinaturaDigital.obter_configuracao()

            if not config or not config.esta_configurada:
                logger.info(
                    "[%s] processar_assinatura_documento: chave do contribuinte não "
                    "configurada — assinatura de %s #%d ignorada.",
                    schema_name, documento_type, documento_id,
                )
                return {
                    'success': False,
                    'reason': 'chave_nao_configurada',
                    'documento_type': documento_type,
                    'documento_id': documento_id,
                }

            # Assinar os dados do documento
            jws = AssinaturaDigitalService.assinar_documento(dados_documento)

            # Avançar a cadeia interna de hash para a série
            serie = dados_documento.get('serie', 'DEFAULT')
            numero = dados_documento.get('numero', str(documento_id))
            hash_doc = AssinaturaDigitalService.calcular_hash_documento(dados_documento)
            hash_anterior = AssinaturaDigitalService.obter_hash_anterior(serie)
            novo_hash = AssinaturaDigitalService.calcular_hash_documento(
                dados_documento, hash_anterior
            )
            AssinaturaDigitalService.atualizar_cadeia_interna(serie, numero, novo_hash)

            logger.info(
                "[%s] processar_assinatura_documento: %s #%d assinado com sucesso "
                "(série=%s, jws=%s...)",
                schema_name, documento_type, documento_id,
                serie, jws[:20] if jws else '?',
            )
            return {
                'success': True,
                'documento_type': documento_type,
                'documento_id': documento_id,
                'serie': serie,
            }

        except FiscalServiceError as exc:
            logger.error(
                "[%s] processar_assinatura_documento: FiscalServiceError em %s #%d — %s",
                schema_name, documento_type, documento_id, exc,
            )
            # Não retentar por erro de negócio (chave inválida, etc.)
            return {'success': False, 'error': str(exc)}

        except Exception as exc:
            logger.exception(
                "[%s] processar_assinatura_documento: erro inesperado em %s #%d — %s",
                schema_name, documento_type, documento_id, exc,
            )
            raise self.retry(exc=exc)

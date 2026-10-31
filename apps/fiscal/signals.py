# apps/fiscal/signals.py
import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import connection, transaction
from django.db.models.signals import post_save, pre_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from .models import DocumentoFiscal, TaxaIVAAGT, AssinaturaDigital, RetencaoFonte

logger = logging.getLogger('fiscal.signals')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _schema_actual() -> str:
    """Retorna o schema PostgreSQL do tenant activo."""
    return getattr(connection, 'schema_name', 'public')


def _obter_tipo_documento(sender_name: str) -> str:
    mapping = {
        'Venda':         'FR',
        'FaturaCredito': 'FT',
        'NotaCredito':   'NC',
        'NotaDebito':    'ND',
        'Recibo':        'RC',
    }
    return mapping.get(sender_name, 'DOC')


def _obter_numero_documento(instance) -> str:
    for attr in ('numero_documento', 'numero_nota', 'numero_recibo'):
        if hasattr(instance, attr):
            val = getattr(instance, attr)
            if val:
                return str(val)
    return str(instance.pk)


def _obter_data_documento(instance):
    for attr in ('data_venda', 'data_emissao', 'data_recibo', 'data_nota', 'data_documento'):
        if hasattr(instance, attr):
            val = getattr(instance, attr)
            if val:
                return val
    return getattr(instance, 'created_at', timezone.now())


def _obter_valor_total(instance) -> Decimal:
    for attr in ('total', 'total_faturado', 'total_credito', 'total_debito', 'valor_recebido'):
        if hasattr(instance, attr):
            val = getattr(instance, attr)
            if val is not None:
                return Decimal(str(val))
    return Decimal('0.00')


# ─────────────────────────────────────────────────────────────────────────────
# Signals de assinatura digital — documentos de venda
# ─────────────────────────────────────────────────────────────────────────────

def _registar_assinatura_async(sender, instance):
    """
    Agenda a task processar_assinatura_documento para o documento recém-criado.
    Só actua se a chave do contribuinte estiver configurada para este tenant.
    Usa `on_commit` para garantir que o documento já existe na BD antes de
    o Celery worker o tentar ler.
    """
    schema = _schema_actual()

    if schema == 'public':
        return  # schema public não tem documentos fiscais de tenant

    try:
        config = AssinaturaDigital.obter_configuracao()
        if not config or not config.esta_configurada:
            return  # chave não configurada — assinatura será feita após configurar
    except Exception:
        return

    dados_documento = {
        'tipo_documento': _obter_tipo_documento(sender.__name__),
        'serie':          getattr(instance, 'serie', 'DEFAULT'),
        'numero':         _obter_numero_documento(instance),
        'data':           _obter_data_documento(instance).strftime('%Y-%m-%d'),
        'valor_total':    str(_obter_valor_total(instance)),
    }

    def _agendar():
        from apps.fiscal.tasks import processar_assinatura_documento
        processar_assinatura_documento.delay(
            schema_name=schema,
            documento_id=instance.pk,
            documento_type=sender.__name__,
            dados_documento=dados_documento,
        )
        logger.info(
            "[%s] Assinatura agendada para %s #%d",
            schema, sender.__name__, instance.pk,
        )

    transaction.on_commit(_agendar)


@receiver(post_save, sender='vendas.Venda')
@receiver(post_save, sender='vendas.FaturaCredito')
@receiver(post_save, sender='vendas.NotaCredito')
@receiver(post_save, sender='vendas.NotaDebito')
@receiver(post_save, sender='vendas.Recibo')
def assinar_documento_fiscal(sender, instance, created, **kwargs):
    """Agenda assinatura JWS quando um documento fiscal é criado."""
    if created:
        _registar_assinatura_async(sender, instance)


# ─────────────────────────────────────────────────────────────────────────────
# Signals de cache — AssinaturaDigital
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=AssinaturaDigital)
def cache_invalidate_assinatura(sender, instance, **kwargs):
    """Invalida o cache de configuração de assinatura quando actualizada."""
    schema = _schema_actual()
    cache.delete(f"assinatura_configurada_{schema}")
    logger.debug("[%s] Cache de assinatura invalidado.", schema)


# ─────────────────────────────────────────────────────────────────────────────
# Signals de Retenções na Fonte
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=RetencaoFonte)
def calcular_valor_retido_automatico(sender, instance, **kwargs):
    """
    Calcula automaticamente o valor retido (base × taxa / 100)
    se ainda não foi definido manualmente.
    """
    if instance.valor_base and instance.taxa_retencao:
        calculado = instance.valor_base * (instance.taxa_retencao / Decimal('100.00'))
        if not instance.valor_retido or instance.valor_retido != calculado:
            instance.valor_retido = calculado


@receiver(post_save, sender=RetencaoFonte)
def invalidar_cache_retencoes(sender, instance, **kwargs):
    """Invalida caches relacionados com retenções após alteração."""
    schema = _schema_actual()
    keys = [
        f"relatorio_retencoes_{schema}",
        f"dashboard_fiscal_{schema}",
    ]
    if hasattr(instance, 'data_retencao') and instance.data_retencao:
        keys.append(
            f"metricas_retencoes_{schema}"
            f"_{instance.data_retencao.month}_{instance.data_retencao.year}"
        )
    cache.delete_many(keys)


# ─────────────────────────────────────────────────────────────────────────────
# Signals de Taxas de IVA
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=TaxaIVAAGT)
def invalidar_cache_taxas_iva(sender, instance, **kwargs):
    """Invalida caches de taxas IVA após alteração."""
    schema = _schema_actual()
    cache.delete_many([
        f"taxas_iva_ativas_{schema}",
        f"saft_tax_table_{schema}",
        f"dashboard_fiscal_{schema}",
    ])


@receiver(post_save, sender=TaxaIVAAGT)
def log_alteracao_taxa_iva(sender, instance, created, **kwargs):
    """Regista alterações em taxas de IVA para auditoria."""
    schema = _schema_actual()
    acao = "criada" if created else "actualizada"
    logger.info(
        "[%s] Taxa IVA %s: %s (código=%s, percentagem=%s%%)",
        schema, acao,
        getattr(instance, 'nome', ''),
        getattr(instance, 'tax_code', ''),
        getattr(instance, 'tax_percentage', ''),
    )


@receiver(pre_delete, sender=TaxaIVAAGT)
def verificar_taxa_em_uso(sender, instance, **kwargs):
    """Avisa (mas não bloqueia) se a taxa está em uso antes de apagar."""
    try:
        from apps.vendas.models import ItemVenda, ItemFatura
        em_uso = (
            ItemVenda.objects.filter(taxa_iva=instance).exists() or
            ItemFatura.objects.filter(taxa_iva=instance).exists()
        )
        if em_uso:
            logger.warning(
                "[%s] Taxa IVA #%d (%s) está em uso — a ser apagada mesmo assim.",
                _schema_actual(), instance.pk,
                getattr(instance, 'tax_code', ''),
            )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Auditoria geral (log de CREATE/UPDATE/DELETE em modelos fiscais)
# ─────────────────────────────────────────────────────────────────────────────

_MODELOS_AUDITAVEIS = frozenset({
    'TaxaIVAAGT', 'AssinaturaDigital', 'RetencaoFonte',
    'Venda', 'FaturaCredito', 'NotaCredito', 'NotaDebito', 'Recibo',
})


@receiver(post_save)
def log_auditoria_fiscal(sender, instance, created, **kwargs):
    if sender.__name__ not in _MODELOS_AUDITAVEIS:
        return
    acao = "CREATE" if created else "UPDATE"
    logger.info(
        "AUDIT %s %s #%s [schema=%s]",
        acao, sender.__name__,
        getattr(instance, 'pk', '?'),
        _schema_actual(),
    )


@receiver(pre_delete)
def log_auditoria_fiscal_delete(sender, instance, **kwargs):
    if sender.__name__ not in _MODELOS_AUDITAVEIS:
        return
    logger.warning(
        "AUDIT DELETE %s #%s [schema=%s]",
        sender.__name__,
        getattr(instance, 'pk', '?'),
        _schema_actual(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sinal customizado para eventos fiscais
# ─────────────────────────────────────────────────────────────────────────────

import django.dispatch

evento_fiscal = django.dispatch.Signal()


@receiver(evento_fiscal)
def processar_evento_fiscal(sender, **kwargs):
    """Processa eventos fiscais customizados."""
    evento_type = kwargs.get('evento_type')
    schema      = kwargs.get('schema_name') or _schema_actual()
    dados       = kwargs.get('dados', {})

    logger.info("[%s] Evento fiscal: %s", schema, evento_type)

    if evento_type == 'integridade_comprometida':
        logger.error(
            "[%s] CRÍTICO: integridade fiscal comprometida — %s",
            schema, dados,
        )


def disparar_evento_fiscal(evento_type: str, schema_name: str = None, dados: dict = None):
    """Utilitário para disparar eventos fiscais customizados."""
    evento_fiscal.send(
        sender=None,
        evento_type=evento_type,
        schema_name=schema_name or _schema_actual(),
        dados=dados or {},
    )

# ─────────────────────────────────────────────────────────────────────────────
# Inspector AGT — detecção da emissão de DocumentoFiscal
# ─────────────────────────────────────────────────────────────────────────────

@receiver(
    pre_save,
    sender=DocumentoFiscal,
    dispatch_uid="fiscal.documento_fiscal.capturar_estado_anterior_agt",
)
def capturar_estado_anterior_documento_agt(
    sender,
    instance,
    raw=False,
    **kwargs,
):
    """
    Guarda o estado anterior para identificar uma transição real.

    Assim, uma actualização normal de um documento confirmed não volta
    a ser interpretada como uma nova emissão.
    """

    if raw:
        return

    if not instance.pk:
        instance._agt_status_anterior = None
        return

    try:
        instance._agt_status_anterior = (
            sender.objects
            .filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )
    except Exception:
        # A emissão local não deve depender da disponibilidade do Inspector.
        instance._agt_status_anterior = None
        logger.exception(
            "[%s] Não foi possível obter o estado anterior do DocumentoFiscal #%s.",
            _schema_actual(),
            instance.pk,
        )


@receiver(
    post_save,
    sender=DocumentoFiscal,
    dispatch_uid="fiscal.documento_fiscal.observar_emissao_agt",
)
def observar_emissao_documento_agt(
    sender,
    instance,
    created=False,
    raw=False,
    **kwargs,
):
    """
    Detecta a emissão local e, se configurado, agenda a submissão automática.

    A emissão considerada é:
        draft -> confirmed

    Um documento que passe depois para posted ou paid não deve originar
    uma segunda submissão.
    """

    if raw:
        return

    estado_anterior = getattr(
        instance,
        "_agt_status_anterior",
        None,
    )

    if hasattr(instance, "_agt_status_anterior"):
        delattr(instance, "_agt_status_anterior")

    # Só consideramos a primeira emissão.
    emissao_detectada = (
        (created and instance.status == "confirmed")
        or (
            estado_anterior == "draft"
            and instance.status == "confirmed"
        )
    )

    if not emissao_detectada:
        return

    schema = _schema_actual()

    if schema == "public":
        logger.warning(
            "Tentativa de observar DocumentoFiscal no schema public."
        )
        return

    documento_id = instance.pk
    tipo_documento = instance.tipo_documento

    # Verificar a elegibilidade com a mesma lista do Builder.
    try:
        from apps.fiscal.services.agt_payload_builder import (
            AGT_DOCUMENT_TYPES,
        )

        elegivel = tipo_documento in AGT_DOCUMENT_TYPES

    except Exception:
        logger.exception(
            "[%s] Não foi possível verificar a elegibilidade AGT do documento #%s.",
            schema,
            documento_id,
        )
        elegivel = False

    def _apos_commit():
        """
        Executado apenas depois de a transacção de emissão ser confirmada.
        """

        # 1. O Inspector regista a emissão independentemente da submissão.
        try:
            from apps.fiscal.payload_listener import (
                PayloadListenerService,
            )

            PayloadListenerService.registar_emissao(
                documento_id=documento_id,
                schema_name=schema,
            )

        except Exception:
            logger.exception(
                "[%s] Falha do Listener Inspector no documento #%s. "
                "A emissão local permanece válida.",
                schema,
                documento_id,
            )

        # 2. A submissão automática é uma decisão configurável.
        if not elegivel:
            return

        if not getattr(
            settings,
            "AGT_SUBMISSAO_AUTOMATICA",
            False,
        ):
            logger.info(
                "[%s] Documento #%s emitido. "
                "Submissão automática desactivada.",
                schema,
                documento_id,
            )
            return

        # 3. Agendar a tarefa Celery.
        try:
            from apps.fiscal.tasks import agendar_submissao

            agendar_submissao(
                schema_name=schema,
                documento_fiscal_id=documento_id,
                atraso_minutos=0,
            )

        except Exception:
            logger.exception(
                "[%s] Falha ao agendar submissão AGT do documento #%s.",
                schema,
                documento_id,
            )

    transaction.on_commit(_apos_commit)

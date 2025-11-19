import logging
from django.db.models.signals import post_save, pre_save, post_delete, pre_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal

from .models import TaxaIVAAGT, AssinaturaDigital, RetencaoFonte
from .services import AssinaturaDigitalService, RetencaoFonteService, FiscalServiceError
from apps.vendas.models import Venda, FaturaCredito, NotaCredito, NotaDebito, Recibo
from apps.financeiro.models import LancamentoFinanceiro, MovimentacaoFinanceira
from apps.core.models import Empresa
from .tasks import (
    processar_assinatura_documento,
    notificar_retencao_criada, verificar_integridade_cadeia
)
import io
import csv
import logging
from datetime import datetime
from django.utils import timezone
from django.db.models import Sum, F
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from apps.fiscal.models import TaxaIVAAGT

logger = logging.getLogger('fiscal.signals')

# =====================================
# Signals para Assinatura Digital
# =====================================

@receiver(post_save, sender=Venda)
@receiver(post_save, sender=FaturaCredito)
@receiver(post_save, sender=NotaCredito)
@receiver(post_save, sender=NotaDebito)
@receiver(post_save, sender=Recibo)
def assinar_documento_fiscal(sender, instance, created, **kwargs):
    """
    Assina automaticamente documentos fiscais quando são criados ou atualizados
    """
    if not created:
        return
    
    try:
        # Verificar se a empresa tem assinatura digital configurada
        if not hasattr(instance, 'empresa'):
            logger.warning(f"Documento {sender.__name__} sem empresa definida")
            return
        
        empresa = instance.empresa
        assinatura_exists = AssinaturaDigital.objects.filter(empresa=empresa).exists()
        
        if not assinatura_exists:
            logger.info(f"Empresa {empresa.id} não possui assinatura digital configurada")
            return
        
        # Preparar dados do documento para assinatura
        dados_documento = {
            'tipo_documento': _obter_tipo_documento(sender, instance),
            'serie': getattr(instance, 'serie', 'DEFAULT'),
            'numero': _obter_numero_documento(instance),
            'data': _obter_data_documento(instance).strftime('%Y-%m-%d'),
            'valor_total': str(_obter_valor_total(instance))
        }
        
        # Processar assinatura de forma assíncrona
        processar_assinatura_documento.delay(
            empresa_id=empresa.id,
            documento_id=instance.id,
            documento_type=sender.__name__,
            dados_documento=dados_documento
        )
        
        logger.info(
            f"Assinatura digital agendada para {sender.__name__} {instance.id}",
            extra={
                'empresa_id': empresa.id,
                'documento_id': instance.id,
                'documento_type': sender.__name__
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar assinatura digital: {e}")


def _obter_tipo_documento(sender, instance):
    """Obtém o tipo de documento para SAF-T"""
    mapping = {
        'Venda': 'FR',  # Fatura Recibo
        'FaturaCredito': 'FT',  # Fatura
        'NotaCredito': 'NC',  # Nota de Crédito
        'NotaDebito': 'ND',  # Nota de Débito
        'Recibo': 'RC'  # Recibo
    }
    return mapping.get(sender.__name__, 'DOC')


def _obter_numero_documento(instance):
    """Obtém o número do documento"""
    for attr in ['numero_documento', 'numero_documento', 'numero_documento', 'numero_documento', 'numero_documento']:
        if hasattr(instance, attr):
            return getattr(instance, attr)
    return str(instance.id)


def _obter_data_documento(instance):
    """Obtém a data do documento"""
    for attr in ['data_venda', 'data_emissao', 'data_recibo', 'data_documento']:
        if hasattr(instance, attr):
            return getattr(instance, attr)
    return instance.created_at.date()


def _obter_valor_total(instance):
    """Obtém o valor total do documento"""
    for attr in ['total', 'total_faturado', 'total_credito', 'total_debito', 'valor_recebido']:
        if hasattr(instance, attr):
            value = getattr(instance, attr)
            return value if value is not None else Decimal('0.00')
    return Decimal('0.00')


@receiver(post_save, sender=AssinaturaDigital)
def cache_invalidate_assinatura(sender, instance, **kwargs):
    """Invalida cache quando assinatura digital é atualizada"""
    cache_key = f"assinatura_digital_{instance.empresa.id}"
    cache.delete(cache_key)
    
    logger.debug(f"Cache invalidado para assinatura digital da empresa {instance.empresa.id}")


# =====================================
# Signals para Retenções na Fonte
# =====================================

@receiver(post_save, sender=RetencaoFonte)
def processar_retencao_criada(sender, instance, created, **kwargs):
    """
    Processa retenção na fonte criada: gera lançamentos e notificações
    """
    if not created:
        return
    
    try:
        # Gerar lançamentos contábeis se ainda não foram gerados
        if not LancamentoFinanceiro.objects.filter(
            empresa=instance.empresa,
            descricao__icontains=f"Retenção {instance.id}"
        ).exists():
            
            # Usar service para gerar lançamentos
            RetencaoFonteService._gerar_lancamento_contabil(instance)
        
        # Notificar criação de retenção de forma assíncrona
        notificar_retencao_criada.delay(
            retencao_id=instance.id,
            empresa_id=instance.empresa.id
        )
        
        logger.info(
            f"Retenção na fonte processada: {instance.id}",
            extra={
                'retencao_id': instance.id,
                'tipo_retencao': instance.tipo_retencao,
                'valor_retido': float(instance.valor_retido),
                'empresa_id': instance.empresa.id
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar retenção criada: {e}")


@receiver(pre_save, sender=RetencaoFonte)
def calcular_valor_retido_automatico(sender, instance, **kwargs):
    """
    Calcula automaticamente o valor retido baseado na base e taxa
    """
    if instance.valor_base and instance.taxa_retencao:
        valor_calculado = instance.valor_base * (instance.taxa_retencao / Decimal('100.00'))
        
        # Só atualizar se o valor não foi definido manualmente ou mudou
        if not instance.valor_retido or instance.valor_retido != valor_calculado:
            instance.valor_retido = valor_calculado
            
            logger.debug(
                f"Valor retido calculado automaticamente: {valor_calculado}",
                extra={
                    'retencao_id': getattr(instance, 'id', 'novo'),
                    'valor_base': float(instance.valor_base),
                    'taxa_retencao': float(instance.taxa_retencao)
                }
            )


@receiver(post_save, sender=RetencaoFonte)
def invalidar_cache_relatorios_retencao(sender, instance, **kwargs):
    """Invalida cache de relatórios quando retenção é atualizada"""
    cache_keys = [
        f"relatorio_retencoes_{instance.empresa.id}",
        f"dashboard_fiscal_{instance.empresa.id}",
        f"metricas_retencoes_{instance.empresa.id}_{instance.data_retencao.month}_{instance.data_retencao.year}"
    ]
    
    cache.delete_many(cache_keys)
    logger.debug(f"Cache de relatórios invalidado para empresa {instance.empresa.id}")


# =====================================
# Signals para Taxas de IVA
# =====================================

@receiver(post_save, sender=TaxaIVAAGT)
def invalidar_cache_taxas_iva(sender, instance, **kwargs):
    """Invalida cache quando taxas de IVA são atualizadas"""
    cache_keys = [
        f"taxas_iva_ativas_{instance.empresa.id}",
        f"saft_tax_table_{instance.empresa.id}",
        f"dashboard_fiscal_{instance.empresa.id}"
    ]
    
    cache.delete_many(cache_keys)
    logger.debug(f"Cache de taxas IVA invalidado para empresa {instance.empresa.id}")


@receiver(post_save, sender=TaxaIVAAGT)
def log_alteracao_taxa_iva(sender, instance, created, **kwargs):
    """
    Log detalhado de alterações em taxas de IVA para auditoria
    """
    acao = "criada" if created else "atualizada"
    
    logger.info(
        f"Taxa IVA {acao}: {instance.nome}",
        extra={
            'empresa_id': instance.empresa.id,
            'taxa_id': instance.id,
            'tax_type': instance.tax_type,
            'tax_code': instance.tax_code,
            'tax_percentage': float(instance.tax_percentage) if instance.tax_percentage else None,
            'ativa': instance.ativo,
            'acao': acao
        }
    )


@receiver(pre_delete, sender=TaxaIVAAGT)
def verificar_taxa_em_uso(sender, instance, **kwargs):
    """
    Verifica se a taxa está sendo usada antes de permitir exclusão
    """
    # Verificar se a taxa está sendo usada em vendas
    from apps.vendas.models import ItemVenda, ItemFatura
    
    em_uso_vendas = ItemVenda.objects.filter(taxa_iva=instance).exists()
    em_uso_faturas = ItemFatura.objects.filter(taxa_iva=instance).exists()
    
    if em_uso_vendas or em_uso_faturas:
        logger.warning(
            f"Tentativa de excluir taxa IVA em uso: {instance.id}",
            extra={
                'taxa_id': instance.id,
                'empresa_id': instance.empresa.id,
                'em_uso_vendas': em_uso_vendas,
                'em_uso_faturas': em_uso_faturas
            }
        )
        # Pode lançar uma exceção aqui se necessário
        # raise ValidationError("Não é possível excluir taxa que está em uso")


def gerar_backup_fiscal(empresa):
    """
    Gera um backup fiscal completo em formato ZIP contendo:
    - Relatórios de retenções e taxas IVA (CSV)
    - Exportações SAF-T
    - Chave pública de assinatura (se houver)
    """
    import zipfile
    buffer = io.BytesIO()
    nome_zip = f"backup_fiscal_{empresa.nif}_{timezone.now().strftime('%Y%m%d_%H%M')}.zip"

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Relatórios CSV
        try:
            ret_csv, _, _ = gerar_relatorio_retencoes(empresa, "csv")
            zipf.writestr("relatorio_retencoes.csv", ret_csv)
        except Exception as e:
            logger.warning(f"Falha ao incluir relatório de retenções: {e}")

        try:
            taxa_csv, _, _ = gerar_relatorio_taxas(empresa, "csv")
            zipf.writestr("relatorio_taxas_iva.csv", taxa_csv)
        except Exception as e:
            logger.warning(f"Falha ao incluir relatório de taxas IVA: {e}")

        # Chave pública (se existir)
        assinatura = getattr(empresa, "assinatura_fiscal", None)
        if assinatura and assinatura.chave_publica:
            zipf.writestr("chave_publica.pem", assinatura.chave_publica)

        # Metadados
        meta = f"Empresa: {empresa.nome}\nNIF: {empresa.nif}\nData: {timezone.now()}\n"
        zipf.writestr("INFO.txt", meta)

    buffer.seek(0)
    return buffer.getvalue(), nome_zip


# =====================================
# Signals para Backup e Integridade
# =====================================

@receiver(post_save, sender=MovimentacaoFinanceira)
def agendar_backup_fiscal(sender, instance, created, **kwargs):
    """
    Agenda backup fiscal quando há movimentações importantes
    """
    if not created:
        return
    
    # Agendar backup apenas para movimentações confirmadas de valor alto
    if instance.confirmada and instance.valor >= Decimal('100000.00'):  # 100k AOA
        gerar_backup_fiscal.delay(
            empresa_id=instance.empresa.id,
            data_referencia=instance.data_movimentacao.isoformat(),
            motivo=f"Movimentação importante: {instance.id}"
        )
        
        logger.info(
            f"Backup fiscal agendado para movimentação: {instance.id}",
            extra={
                'empresa_id': instance.empresa.id,
                'valor': float(instance.valor),
                'motivo': 'movimentacao_importante'
            }
        )


@receiver(post_save, sender=AssinaturaDigital)
def verificar_integridade_assinatura(sender, instance, **kwargs):
    """
    Verifica integridade da cadeia de assinatura quando atualizada
    """
    # Agendar verificação de integridade
    verificar_integridade_cadeia.delay(
        empresa_id=instance.empresa.id,
        verificar_todas_series=True
    )
    
    logger.info(
        f"Verificação de integridade agendada para empresa {instance.empresa.id}",
        extra={'empresa_id': instance.empresa.id}
    )


# =====================================
# Signals para Auditoria Geral
# =====================================

@receiver(post_save)
def log_auditoria_fiscal(sender, instance, created, **kwargs):
    """
    Log geral de auditoria para modelos fiscais importantes
    """
    modelos_fiscais = [
        'TaxaIVAAGT', 'AssinaturaDigital', 'RetencaoFonte',
        'Venda', 'FaturaCredito', 'NotaCredito', 'NotaDebito', 'Recibo'
    ]
    
    if sender.__name__ in modelos_fiscais:
        acao = "CREATE" if created else "UPDATE"
        
        # Obter empresa se possível
        empresa_id = None
        if hasattr(instance, 'empresa'):
            empresa_id = instance.empresa.id
        elif hasattr(instance, 'empresa_id'):
            empresa_id = instance.empresa_id
        
        logger.info(
            f"AUDIT: {acao} {sender.__name__}",
            extra={
                'action': acao,
                'model': sender.__name__,
                'object_id': getattr(instance, 'id', None),
                'empresa_id': empresa_id,
                'timestamp': timezone.now().isoformat()
            }
        )


@receiver(pre_delete)
def log_auditoria_fiscal_delete(sender, instance, **kwargs):
    """
    Log de auditoria para exclusões
    """
    modelos_fiscais = [
        'TaxaIVAAGT', 'AssinaturaDigital', 'RetencaoFonte',
        'Venda', 'FaturaCredito', 'NotaCredito', 'NotaDebito', 'Recibo'
    ]
    
    if sender.__name__ in modelos_fiscais:
        empresa_id = None
        if hasattr(instance, 'empresa'):
            empresa_id = instance.empresa.id
        elif hasattr(instance, 'empresa_id'):
            empresa_id = instance.empresa_id
        
        logger.warning(
            f"AUDIT: DELETE {sender.__name__}",
            extra={
                'action': 'DELETE',
                'model': sender.__name__,
                'object_id': getattr(instance, 'id', None),
                'empresa_id': empresa_id,
                'timestamp': timezone.now().isoformat()
            }
        )


# =====================================
# Signals para Cache e Performance
# =====================================

@receiver(post_save, sender=Empresa)
def inicializar_cache_empresa_fiscal(sender, instance, created, **kwargs):
    """
    Inicializa cache fiscal quando uma nova empresa é criada
    """
    if created:
        # Pré-carregar dados fiscais essenciais no cache
        cache_keys = {
            f"taxas_iva_ativas_{instance.id}": [],
            f"assinatura_configurada_{instance.id}": False,
            f"dashboard_fiscal_{instance.id}": {},
        }
        
        cache.set_many(cache_keys, timeout=3600)  # 1 hora
        
        logger.info(
            f"Cache fiscal inicializado para nova empresa: {instance.id}",
            extra={'empresa_id': instance.id}
        )


# =====================================
# Signal personalizado para eventos fiscais
# =====================================

import django.dispatch

# Sinal customizado para eventos fiscais importantes
evento_fiscal = django.dispatch.Signal()

@receiver(evento_fiscal)
def processar_evento_fiscal(sender, **kwargs):
    """
    Processa eventos fiscais customizados
    """
    evento_type = kwargs.get('evento_type')
    empresa_id = kwargs.get('empresa_id')
    dados = kwargs.get('dados', {})
    
    logger.info(
        f"Evento fiscal processado: {evento_type}",
        extra={
            'evento_type': evento_type,
            'empresa_id': empresa_id,
            'dados': dados
        }
    )
    
    # Processar diferentes tipos de eventos
    if evento_type == 'documento_assinado':
        # Lógica específica para documento assinado
        pass
    elif evento_type == 'backup_necessario':
        # Agendar backup
        gerar_backup_fiscal.delay(empresa_id=empresa_id, motivo=dados.get('motivo'))
    elif evento_type == 'integridade_comprometida':
        # Notificar administradores
        logger.error(
            f"CRÍTICO: Integridade fiscal comprometida para empresa {empresa_id}",
            extra={'empresa_id': empresa_id, 'detalhes': dados}
        )


# =====================================
# Utilitários para disparar eventos
# =====================================

def disparar_evento_fiscal(evento_type: str, empresa_id: int, dados: dict = None):
    """
    Função utilitária para disparar eventos fiscais customizados
    """
    evento_fiscal.send(
        sender=None,
        evento_type=evento_type,
        empresa_id=empresa_id,
        dados=dados or {}
    )





logger = logging.getLogger(__name__)



def gerar_relatorio_retencoes(empresa, formato: str):
    """
    Gera relatório de retenções na fonte da empresa.
    Suporta formatos: PDF, XLSX, CSV.

    Retorna (ficheiro, nome_arquivo, content_type)
    """
    formato = formato.lower().strip()
    qs = (
        RetencaoFonte.objects.filter(empresa=empresa)
        .values("id", "nome_exibicao", "valor_bruto", "valor_retido", "data_pagamento", "estado")
        .order_by("-data_pagamento")
    )

    if not qs.exists():
        raise ValueError("Não há retenções registadas para gerar relatório.")

    nome_arquivo_base = f"relatorio_retencoes_{empresa.nif}_{timezone.now().strftime('%Y%m%d_%H%M')}"
    logger.info(f"Gerando relatório de retenções ({formato}) para empresa {empresa.nome}")

    # === CSV ===
    if formato == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["ID", "Fornecedor", "Valor Bruto", "Valor Retido", "Data Pagamento", "Estado"])
        for r in qs:
            writer.writerow([
                r["id"],
                r["fornecedor__nome"],
                f"{r['valor_bruto']:.2f}",
                f"{r['valor_retido']:.2f}",
                r["data_pagamento"].strftime("%d/%m/%Y") if r["data_pagamento"] else "",
                r["estado"],
            ])
        content = buffer.getvalue().encode("utf-8")
        return content, f"{nome_arquivo_base}.csv", "text/csv"

    # === XLSX ===
    elif formato in ["xls", "xlsx"]:
        buffer = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = "Retenções"
        ws.append(["ID", "Fornecedor", "Valor Bruto", "Valor Retido", "Data Pagamento", "Estado"])
        for r in qs:
            ws.append([
                r["id"],
                r["fornecedor__nome"],
                float(r["valor_bruto"]),
                float(r["valor_retido"]),
                r["data_pagamento"].strftime("%d/%m/%Y") if r["data_pagamento"] else "",
                r["estado"],
            ])
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue(), f"{nome_arquivo_base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # === PDF ===
    elif formato == "pdf":
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setTitle("Relatório de Retenções na Fonte")
        width, height = A4
        p.drawString(50, height - 50, f"Relatório de Retenções - {empresa.nome}")
        p.drawString(50, height - 70, f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        p.drawString(50, height - 90, f"NIF: {empresa.nif}")

        y = height - 120
        p.setFont("Helvetica-Bold", 9)
        p.drawString(50, y, "Fornecedor")
        p.drawString(200, y, "Bruto")
        p.drawString(270, y, "Retido")
        p.drawString(340, y, "Data")
        p.drawString(420, y, "Estado")
        p.setFont("Helvetica", 9)
        y -= 20

        for r in qs[:50]:  # limitar 50 linhas por página
            p.drawString(50, y, r["fornecedor__nome"][:25])
            p.drawString(200, y, f"{r['valor_bruto']:.2f}")
            p.drawString(270, y, f"{r['valor_retido']:.2f}")
            p.drawString(340, y, r["data_pagamento"].strftime("%d/%m/%Y") if r["data_pagamento"] else "")
            p.drawString(420, y, r["estado"])
            y -= 18
            if y < 80:
                p.showPage()
                y = height - 80

        p.showPage()
        p.save()
        buffer.seek(0)
        return buffer.getvalue(), f"{nome_arquivo_base}.pdf", "application/pdf"

    else:
        raise ValueError("Formato de relatório inválido. Use pdf, xlsx ou csv.")


def gerar_relatorio_taxas(empresa, formato: str):
    """
    Gera relatório de taxas de IVA da empresa.
    Suporta formatos: PDF, XLSX, CSV.

    Retorna (ficheiro, nome_arquivo, content_type)
    """
    formato = formato.lower().strip()
    qs = (
        TaxaIVAAGT.objects.filter(empresa=empresa)
        .values("codigo", "descricao", "percentual", "vigente_desde", "vigente_ate", "ativo")
        .order_by("codigo")
    )

    if not qs.exists():
        raise ValueError("Nenhuma taxa de IVA encontrada para esta empresa.")

    nome_arquivo_base = f"relatorio_taxas_iva_{empresa.nif}_{timezone.now().strftime('%Y%m%d_%H%M')}"
    logger.info(f"Gerando relatório de taxas IVA ({formato}) para empresa {empresa.nome}")

    # === CSV ===
    if formato == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["Código", "Descrição", "% IVA", "Desde", "Até", "Ativo"])
        for t in qs:
            writer.writerow([
                t["codigo"],
                t["descricao"],
                f"{t['percentual']:.2f}%",
                t["vigente_desde"].strftime("%d/%m/%Y") if t["vigente_desde"] else "",
                t["vigente_ate"].strftime("%d/%m/%Y") if t["vigente_ate"] else "",
                "Sim" if t["ativo"] else "Não",
            ])
        content = buffer.getvalue().encode("utf-8")
        return content, f"{nome_arquivo_base}.csv", "text/csv"

    # === XLSX ===
    elif formato in ["xls", "xlsx"]:
        buffer = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = "Taxas IVA"
        ws.append(["Código", "Descrição", "% IVA", "Desde", "Até", "Ativo"])
        for t in qs:
            ws.append([
                t["codigo"],
                t["descricao"],
                float(t["percentual"]),
                t["vigente_desde"].strftime("%d/%m/%Y") if t["vigente_desde"] else "",
                t["vigente_ate"].strftime("%d/%m/%Y") if t["vigente_ate"] else "",
                "Sim" if t["ativo"] else "Não",
            ])
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue(), f"{nome_arquivo_base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # === PDF ===
    elif formato == "pdf":
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setTitle("Relatório de Taxas de IVA")
        width, height = A4
        p.drawString(50, height - 50, f"Relatório de Taxas de IVA - {empresa.nome}")
        p.drawString(50, height - 70, f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        p.drawString(50, height - 90, f"NIF: {empresa.nif}")

        y = height - 120
        p.setFont("Helvetica-Bold", 9)
        p.drawString(50, y, "Código")
        p.drawString(120, y, "Descrição")
        p.drawString(300, y, "% IVA")
        p.drawString(360, y, "Desde")
        p.drawString(440, y, "Até")
        p.drawString(520, y, "Ativo")
        p.setFont("Helvetica", 9)
        y -= 20

        for t in qs[:50]:
            p.drawString(50, y, t["codigo"])
            p.drawString(120, y, t["descricao"][:30])
            p.drawString(300, y, f"{t['percentual']:.2f}%")
            p.drawString(360, y, t["vigente_desde"].strftime("%d/%m/%Y") if t["vigente_desde"] else "")
            p.drawString(440, y, t["vigente_ate"].strftime("%d/%m/%Y") if t["vigente_ate"] else "")
            p.drawString(520, y, "Sim" if t["ativo"] else "Não")
            y -= 18
            if y < 80:
                p.showPage()
                y = height - 80

        p.showPage()
        p.save()
        buffer.seek(0)
        return buffer.getvalue(), f"{nome_arquivo_base}.pdf", "application/pdf"

    else:
        raise ValueError("Formato inválido. Use pdf, xlsx ou csv.")







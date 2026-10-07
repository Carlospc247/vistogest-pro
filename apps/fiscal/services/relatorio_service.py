# apps/fiscal/services/relatorio_service.py
"""
Serviço de relatórios e backup fiscal.

Funções:
  - gerar_backup_fiscal(empresa)            → (bytes_zip, nome_ficheiro)
  - gerar_relatorio_retencoes(empresa, fmt) → (bytes, nome, content_type)
  - gerar_relatorio_taxas(empresa, fmt)     → (bytes, nome, content_type)

Formatos suportados: pdf | xlsx | xls | csv
"""
import csv
import io
import logging
import zipfile
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger('fiscal.relatorios')


# ──────────────────────────────────────────────────────────────────────────────
# BACKUP FISCAL (ZIP com CSV + chave pública)
# ──────────────────────────────────────────────────────────────────────────────

def gerar_backup_fiscal(empresa):
    """
    Gera um backup fiscal completo em ZIP contendo:
      - relatorio_retencoes.csv
      - relatorio_taxas_iva.csv
      - chave_publica.pem  (se disponível)
      - INFO.txt

    Retorna:
        (bytes_zip, nome_ficheiro: str)
    """
    from apps.fiscal.models import RetencaoFonte, TaxaIVAAGT, AssinaturaDigital

    buffer = io.BytesIO()
    nif = getattr(empresa, 'nif', 'sem_nif')
    ts  = timezone.now().strftime('%Y%m%d_%H%M')
    nome_zip = f"backup_fiscal_{nif}_{ts}.zip"

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:

        # ── Retenções CSV ──────────────────────────────────────────────────
        try:
            conteudo_csv, _, _ = gerar_relatorio_retencoes(empresa, 'csv')
            zf.writestr('relatorio_retencoes.csv', conteudo_csv)
        except Exception as exc:
            logger.warning("Backup fiscal: retenções indisponíveis — %s", exc)

        # ── Taxas IVA CSV ─────────────────────────────────────────────────
        try:
            taxas_csv, _, _ = gerar_relatorio_taxas(empresa, 'csv')
            zf.writestr('relatorio_taxas_iva.csv', taxas_csv)
        except Exception as exc:
            logger.warning("Backup fiscal: taxas IVA indisponíveis — %s", exc)

        # ── Chave pública ─────────────────────────────────────────────────
        try:
            assinatura = AssinaturaDigital.obter_configuracao()
            if assinatura and assinatura.chave_contribuinte_publica:
                zf.writestr('chave_publica.pem', assinatura.chave_contribuinte_publica)
        except Exception as exc:
            logger.warning("Backup fiscal: chave pública indisponível — %s", exc)

        # ── Metadados ─────────────────────────────────────────────────────
        meta = (
            f"Empresa: {getattr(empresa, 'nome', '?')}\n"
            f"NIF: {nif}\n"
            f"Data geração: {timezone.now().strftime('%d/%m/%Y %H:%M')}\n"
        )
        zf.writestr('INFO.txt', meta)

    buffer.seek(0)
    logger.info("Backup fiscal gerado: %s (%d bytes)", nome_zip, buffer.getbuffer().nbytes)
    return buffer.getvalue(), nome_zip


# ──────────────────────────────────────────────────────────────────────────────
# RELATÓRIO DE RETENÇÕES NA FONTE
# ──────────────────────────────────────────────────────────────────────────────

def gerar_relatorio_retencoes(empresa, formato: str):
    """
    Gera relatório de retenções na fonte.

    Args:
        empresa: instância de Empresa (tenant activo).
        formato: 'pdf', 'xlsx' / 'xls', ou 'csv'.

    Retorna:
        (bytes, nome_arquivo: str, content_type: str)
    """
    from apps.fiscal.models import RetencaoFonte

    fmt = formato.lower().strip()
    nif = getattr(empresa, 'nif', 'sem_nif')
    ts  = timezone.now().strftime('%Y%m%d_%H%M')
    base = f"relatorio_retencoes_{nif}_{ts}"

    qs = (
        RetencaoFonte.objects
        .select_related('fornecedor')
        .order_by('-data_retencao')
    )

    # ── CSV ───────────────────────────────────────────────────────────────
    if fmt == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow(['ID', 'Fornecedor', 'Ref. Documento', 'Valor Base',
                    'Taxa (%)', 'Valor Retido', 'Tipo', 'Data Retenção'])
        for r in qs:
            w.writerow([
                r.pk,
                getattr(r.fornecedor, 'nome', '') if r.fornecedor else '',
                getattr(r, 'referencia_documento', ''),
                _fmt_decimal(getattr(r, 'valor_base', 0)),
                _fmt_decimal(getattr(r, 'taxa_retencao', 0)),
                _fmt_decimal(getattr(r, 'valor_retido', 0)),
                getattr(r, 'tipo_retencao', ''),
                r.data_retencao.strftime('%d/%m/%Y') if r.data_retencao else '',
            ])
        return buf.getvalue().encode('utf-8'), f"{base}.csv", 'text/csv'

    # ── XLSX ─────────────────────────────────────────────────────────────
    elif fmt in ('xls', 'xlsx'):
        from openpyxl import Workbook
        buf = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = 'Retenções'
        ws.append(['ID', 'Fornecedor', 'Ref. Documento', 'Valor Base',
                   'Taxa (%)', 'Valor Retido', 'Tipo', 'Data Retenção'])
        for r in qs:
            ws.append([
                r.pk,
                getattr(r.fornecedor, 'nome', '') if r.fornecedor else '',
                getattr(r, 'referencia_documento', ''),
                float(getattr(r, 'valor_base', 0) or 0),
                float(getattr(r, 'taxa_retencao', 0) or 0),
                float(getattr(r, 'valor_retido', 0) or 0),
                getattr(r, 'tipo_retencao', ''),
                r.data_retencao.strftime('%d/%m/%Y') if r.data_retencao else '',
            ])
        wb.save(buf)
        buf.seek(0)
        ct = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return buf.getvalue(), f"{base}.xlsx", ct

    # ── PDF ──────────────────────────────────────────────────────────────
    elif fmt == 'pdf':
        return _relatorio_retencoes_pdf(empresa, qs, base)

    raise ValueError(f"Formato inválido: '{formato}'. Use pdf, xlsx ou csv.")


def _relatorio_retencoes_pdf(empresa, qs, base):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    p   = rl_canvas.Canvas(buf, pagesize=landscape(A4))
    p.setTitle('Relatório de Retenções na Fonte')
    w, h = landscape(A4)

    p.setFont('Helvetica-Bold', 11)
    p.drawString(40, h - 40, f"Retenções na Fonte — {getattr(empresa, 'nome', '')}")
    p.setFont('Helvetica', 9)
    p.drawString(40, h - 58, f"NIF: {getattr(empresa, 'nif', '')}   |   Gerado: {datetime.now():%d/%m/%Y %H:%M}")

    y = h - 82
    p.setFont('Helvetica-Bold', 8)
    for x, label in [(40,'Fornecedor'),(180,'Ref. Doc.'),(290,'V. Base'),(350,'Taxa%'),
                     (400,'V. Retido'),(460,'Tipo'),(520,'Data')]:
        p.drawString(x, y, label)
    p.setFont('Helvetica', 8)
    y -= 16

    for r in qs[:60]:
        if y < 50:
            p.showPage()
            y = h - 60
        p.drawString(40,  y, (getattr(r.fornecedor,'nome','') if r.fornecedor else '')[:20])
        p.drawString(180, y, str(getattr(r,'referencia_documento',''))[:14])
        p.drawString(290, y, _fmt_decimal(getattr(r,'valor_base',0)))
        p.drawString(350, y, _fmt_decimal(getattr(r,'taxa_retencao',0)))
        p.drawString(400, y, _fmt_decimal(getattr(r,'valor_retido',0)))
        p.drawString(460, y, str(getattr(r,'tipo_retencao',''))[:8])
        p.drawString(520, y, r.data_retencao.strftime('%d/%m/%Y') if r.data_retencao else '')
        y -= 14

    p.showPage()
    p.save()
    buf.seek(0)
    return buf.getvalue(), f"{base}.pdf", 'application/pdf'


# ──────────────────────────────────────────────────────────────────────────────
# RELATÓRIO DE TAXAS DE IVA
# ──────────────────────────────────────────────────────────────────────────────

def gerar_relatorio_taxas(empresa, formato: str):
    """
    Gera relatório de taxas de IVA.

    Retorna:
        (bytes, nome_arquivo: str, content_type: str)
    """
    from apps.fiscal.models import TaxaIVAAGT

    fmt = formato.lower().strip()
    nif = getattr(empresa, 'nif', 'sem_nif')
    ts  = timezone.now().strftime('%Y%m%d_%H%M')
    base = f"relatorio_taxas_iva_{nif}_{ts}"

    qs = TaxaIVAAGT.objects.order_by('tax_code')

    # ── CSV ───────────────────────────────────────────────────────────────
    if fmt == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow(['ID', 'Nome', 'Tax Type', 'Tax Code', '% Taxa',
                    'Motivo Isenção', 'Activa'])
        for t in qs:
            w.writerow([
                t.pk,
                getattr(t, 'nome', ''),
                getattr(t, 'tax_type', ''),
                getattr(t, 'tax_code', ''),
                _fmt_decimal(getattr(t, 'tax_percentage', 0)),
                getattr(t, 'exemption_reason', ''),
                'Sim' if getattr(t, 'ativa', True) else 'Não',
            ])
        return buf.getvalue().encode('utf-8'), f"{base}.csv", 'text/csv'

    # ── XLSX ─────────────────────────────────────────────────────────────
    elif fmt in ('xls', 'xlsx'):
        from openpyxl import Workbook
        buf = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = 'Taxas IVA'
        ws.append(['ID', 'Nome', 'Tax Type', 'Tax Code', '% Taxa',
                   'Motivo Isenção', 'Activa'])
        for t in qs:
            ws.append([
                t.pk,
                getattr(t, 'nome', ''),
                getattr(t, 'tax_type', ''),
                getattr(t, 'tax_code', ''),
                float(getattr(t, 'tax_percentage', 0) or 0),
                getattr(t, 'exemption_reason', ''),
                'Sim' if getattr(t, 'ativa', True) else 'Não',
            ])
        wb.save(buf)
        buf.seek(0)
        ct = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return buf.getvalue(), f"{base}.xlsx", ct

    # ── PDF ──────────────────────────────────────────────────────────────
    elif fmt == 'pdf':
        return _relatorio_taxas_pdf(empresa, qs, base)

    raise ValueError(f"Formato inválido: '{formato}'. Use pdf, xlsx ou csv.")


def _relatorio_taxas_pdf(empresa, qs, base):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    p   = rl_canvas.Canvas(buf, pagesize=A4)
    p.setTitle('Taxas de IVA — AGT')
    w, h = A4

    p.setFont('Helvetica-Bold', 11)
    p.drawString(40, h - 40, f"Taxas de IVA — {getattr(empresa, 'nome', '')}")
    p.setFont('Helvetica', 9)
    p.drawString(40, h - 58, f"NIF: {getattr(empresa, 'nif', '')}   |   Gerado: {datetime.now():%d/%m/%Y %H:%M}")

    y = h - 82
    p.setFont('Helvetica-Bold', 9)
    for x, label in [(40,'Nome'),(170,'Tax Type'),(240,'Tax Code'),(310,'% Taxa'),
                     (380,'Isenção'),(480,'Activa')]:
        p.drawString(x, y, label)
    p.setFont('Helvetica', 9)
    y -= 16

    for t in qs[:50]:
        if y < 60:
            p.showPage()
            y = h - 60
        p.drawString(40,  y, str(getattr(t, 'nome', ''))[:20])
        p.drawString(170, y, str(getattr(t, 'tax_type', '')))
        p.drawString(240, y, str(getattr(t, 'tax_code', '')))
        p.drawString(310, y, _fmt_decimal(getattr(t, 'tax_percentage', 0)))
        p.drawString(380, y, str(getattr(t, 'exemption_reason', ''))[:14])
        p.drawString(480, y, 'Sim' if getattr(t, 'ativa', True) else 'Não')
        y -= 14

    p.showPage()
    p.save()
    buf.seek(0)
    return buf.getvalue(), f"{base}.pdf", 'application/pdf'


# ──────────────────────────────────────────────────────────────────────────────
# Utilitário interno
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_decimal(valor) -> str:
    """Formata um valor numérico para string com 2 casas decimais."""
    try:
        return f"{Decimal(str(valor)):.2f}"
    except Exception:
        return '0.00'

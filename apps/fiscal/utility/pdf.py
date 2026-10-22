# apps/fiscal/utils/pdf.py
"""Geração de PDF com os dados reais do modelo AssinaturaDigital."""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.fiscal.models import AssinaturaDigital


def gerar_pdf_submissao_agt(empresa, assinatura: AssinaturaDigital):
    """Gera uma folha de submissão usando apenas a chave pública e metadados."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margem = 40

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margem, height - 60, f"Certificação AGT - Empresa: {empresa.nome}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margem, height - 80, f"NIF: {getattr(empresa, 'nif', '')}")
    configurada_em = getattr(assinatura, "data_configuracao_chave", None)
    pdf.drawString(margem, height - 100, f"Data de configuração: {configurada_em or 'Não configurada'}")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margem, height - 130, "Chave pública / certificado PEM:")
    pdf.setFont("Courier", 7)
    texto = pdf.beginText(margem, height - 148)
    linhas = (getattr(assinatura, "chave_contribuinte_publica", "") or "").splitlines()
    y = height - 148
    for linha in linhas:
        if y < 70:
            pdf.drawText(texto)
            pdf.showPage()
            texto = pdf.beginText(margem, height - 50)
            y = height - 50
            pdf.setFont("Courier", 7)
        texto.textLine(linha[:150])
        y -= 9
    pdf.drawText(texto)

    y -= 20
    if y < 70:
        pdf.showPage()
        y = height - 60
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margem, y, "Rastreio de séries fiscais")
    y -= 16
    pdf.setFont("Helvetica", 8)
    for serie, meta in (getattr(assinatura, "dados_series_fiscais", {}) or {}).items():
        linha = f"Série: {serie} | Último documento: {meta.get('ultimo_documento', '')} | Último hash: {str(meta.get('ultimo_hash', ''))[:18]}"
        if y < 55:
            pdf.showPage()
            y = height - 55
            pdf.setFont("Helvetica", 8)
        pdf.drawString(margem, y, linha[:155])
        y -= 12

    pdf.save()
    buffer.seek(0)
    return buffer

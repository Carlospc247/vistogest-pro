# apps/fiscal/utils/pdf.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

from apps.fiscal.models import AssinaturaDigital


def gerar_pdf_submissao_agt(empresa, assinatura: AssinaturaDigital):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height-60, f"Certificação AGT - Empresa: {empresa.nome}")
    c.setFont("Helvetica", 10)
    c.drawString(40, height-80, f"NIF: {getattr(empresa, 'nif', '')}")
    c.drawString(40, height-100, f"Data geração: {assinatura.data_geracao}")

    c.drawString(40, height-140, "Chave Pública (PEM):")
    text = c.beginText(40, height-160)
    for line in (assinatura.chave_publica or "").splitlines():
        text.textLine(line)
    c.drawText(text)

    # Dados séries
    y = height - 160 - (12 * (len((assinatura.chave_publica or "").splitlines()) + 1))
    c.drawString(40, y, "Dados por série:")
    y -= 14
    for serie, meta in (assinatura.dados_series_fiscais or {}).items():
        c.drawString(46, y, f"Série: {serie} - Último ATCUD: {meta.get('ultimo_atcud', '')}")
        y -= 12
        if y < 80:
            c.showPage()
            y = height - 60

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

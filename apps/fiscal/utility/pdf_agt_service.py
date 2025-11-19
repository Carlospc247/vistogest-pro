# apps/fiscal/services/pdf_agt_service.py
import base64
from datetime import datetime
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.http import HttpResponse

class PDFAGTService:
    """
    Gera o PDF para submissão na AGT.
    Conforme modelo oficial do Manual SAF-T AO.
    """

    @staticmethod
    def gerar_pdf_declaracao(empresa, assinatura):
        """
        Recebe Empresa e AssinaturaDigital
        Retorna HttpResponse com PDF pronto para download.
        """

        response = HttpResponse(content_type='application/pdf')
        filename = f"DECLARACAO_AGT_{empresa.nif}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        pdf = canvas.Canvas(response, pagesize=A4)
        width, height = A4

        y = height - 50
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "DECLARAÇÃO OFICIAL PARA AGT – ASSINATURA DIGITAL")
        y -= 50

        # Dados da empresa
        pdf.setFont("Helvetica", 11)
        pdf.drawString(40, y, f"Nome da Empresa: {empresa.nome}")
        y -= 20
        pdf.drawString(40, y, f"NIF: {empresa.nif}")
        y -= 20
        pdf.drawString(40, y, f"Endereço: {empresa.endereco}, {empresa.cidade}")
        y -= 40

        # Chave pública
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Chave Pública (RSA):")
        y -= 20
        pdf.setFont("Helvetica", 9)

        chave_publica = assinatura.chave_publica.strip()
        for linha in chave_publica.split('\n'):
            pdf.drawString(40, y, linha)
            y -= 12

        y -= 25
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Último Hash Gerado (Cadeia de Integridade):")
        y -= 20
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y, assinatura.ultimo_hash or "Ainda não gerado")
        y -= 40

        # Séries fiscais e ATCUDs
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Séries fiscais validadas pela AGT:")
        y -= 25

        pdf.setFont("Helvetica", 9)
        for serie, dados in assinatura.dados_series_fiscais.items():
            atcud = dados.get('atcud', 'N/D')
            pdf.drawString(40, y, f"Série: {serie} | ATCUD: {atcud}")
            y -= 15

        y -= 35
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Declaração Técnica:")
        y -= 20
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y,
            "Declaro, para os devidos efeitos legais, que os documentos emitidos obedecem ao regime")
        y -= 12
        pdf.drawString(40, y,
            "de integridade fiscal digital, conforme modelo definido pela AGT e normativos SAF-T AO.")
        y -= 40

        # Data da geração
        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, 50, f"Luanda, {timezone.now().strftime('%d/%m/%Y %H:%M')}")
        pdf.showPage()
        pdf.save()

        return response

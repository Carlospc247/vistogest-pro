# apps/fiscal/services/pdf_agt_service.py
import io
import logging
import os
import qrcode
from datetime import datetime
from decimal import Decimal, ROUND_UP
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
import requests

class PDFDeclaracaoService:
    """
    Gera o PDF para submissão administrativa na AGT.
    Foco: Cadastro de Chaves e Séries Fiscais (Processo de Certificação).
    """
    @staticmethod
    def gerar_pdf_declaracao(empresa, assinatura):
        response = HttpResponse(content_type='application/pdf')
        filename = f"DECLARACAO_AGT_{empresa.nif}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        pdf = canvas.Canvas(response, pagesize=A4)
        width, height = A4
        y = height - 50
        
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "DECLARAÇÃO OFICIAL PARA AGT - ASSINATURA DIGITAL")
        y -= 50

        # Dados da empresa
        pdf.setFont("Helvetica", 11)
        pdf.drawString(40, y, f"Nome da Empresa: {empresa.nome}")
        y -= 20
        pdf.drawString(40, y, f"NIF: {empresa.nif}")
        y -= 20
        pdf.drawString(40, y, f"Endereço: {empresa.endereco}, {empresa.cidade}")
        y -= 40
        
        # Chave Pública RSA
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Chave Pública (RSA):")
        y -= 20
        pdf.setFont("Courier", 8)
        chave_publica = assinatura.chave_publica.strip() if assinatura.chave_publica else ""
        for linha in chave_publica.split('\n'):
            pdf.drawString(40, y, linha)
            y -= 10

        y -= 25
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Último Hash Gerado (Cadeia de Integridade):")
        y -= 20
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y, assinatura.ultimo_hash or "Ainda não gerado")
        
        # Séries e ATCUDs
        y -= 40
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Séries fiscais validadas pela AGT:")
        y -= 25
        pdf.setFont("Helvetica", 9)
        for serie, dados in assinatura.dados_series_fiscais.items():
            atcud = dados.get('atcud', 'N/D')
            pdf.drawString(40, y, f"Série: {serie} | ATCUD: {atcud}")
            y -= 15

        # Termos Legais
        pdf.drawString(40, 70, "Declaro que os documentos emitidos obedecem ao regime de integridade fiscal digital.")
        pdf.drawString(40, 50, f"Luanda, {timezone.now().strftime('%d/%m/%Y %H:%M')}")

        pdf.showPage()
        pdf.save()
        return response





logger = logging.getLogger('fiscal.pdf')


# apps/fiscal/utility/pdf_agt_service.py
import io
import os
import qrcode
import requests
import logging
from PIL import Image
from decimal import Decimal, ROUND_UP
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('fiscal.pdf')

class PDFDocumentoService:
    def __init__(self, venda_obj, tamanho="a4"):
        self.venda = venda_obj
        self.empresa = venda_obj.empresa
        self.tamanho = tamanho
        self.buffer = io.BytesIO()
        
        if tamanho == "80mm":
            self.width = 80 * mm
            # Altura inicial grande para evitar quebra, o PDF cortará no showPage
            self.p = canvas.Canvas(self.buffer, pagesize=(self.width, 400 * mm))
            self.margem = 4 * mm
        else:
            self.p = canvas.Canvas(self.buffer, pagesize=A4)
            self.width, self.height = A4
            self.margem_esq = 1.5 * cm
            self.margem_dir = 19.5 * cm

    def _format_kz(self, valor):
        return f"{Decimal(str(valor or 0)).quantize(Decimal('0.01'), rounding=ROUND_UP):,.2f} Kz"

    def _get_4_char_hash(self):
        h = self.venda.hash_documento or ""
        return f"{h[0]}{h[10]}{h[20]}{h[30]}".upper() if len(h) >= 31 else "DEMO"

    def _gerar_url_qr(self):
        nif = self.empresa.nif
        doc_no = self.venda.numero_documento.replace(" ", "%20")
        return f"https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor={nif}&document={doc_no}"

    def _obter_logo_empresa_io(self):
        """Helper para baixar logo do Cloudinary/URL"""
        if self.empresa.foto:
            try:
                response = requests.get(self.empresa.foto.url, timeout=5)
                return io.BytesIO(response.content)
            except Exception as e:
                logger.error(f"Erro logo empresa: {e}")
        return None

    def _gerar_qr_com_logo_agt(self, box_size=10):
        """Gera o QR Code com o Logo da AGT centralizado (Pillow)"""
        qr = qrcode.QRCode(version=4, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=2)
        qr.add_data(self._gerar_url_qr())
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        
        agt_logo_path = os.path.join(settings.STATIC_ROOT, 'img/fiscal/logo_agt_qr.png')
        if os.path.exists(agt_logo_path):
            logo = Image.open(agt_logo_path)
            # Centraliza o logo no QR
            qr_w, qr_h = qr_img.size
            logo_size = int(qr_w * 0.2) # 20% da área
            logo = logo.resize((logo_size, logo_size))
            pos = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
            qr_img.paste(logo, pos)

        qr_io = io.BytesIO()
        qr_img.save(qr_io, format='PNG')
        qr_io.seek(0)
        return qr_io


    def gerar(self):
        """Fluxo de construção do documento."""
        if self.tamanho == "80mm":
            return self._gerar_termico()
        
        # Se não for térmico, segue fluxo A4 original
        self._desenhar_cabecalho()
        self._desenhar_infos_documento()
        self._desenhar_corpo_itens()
        self._desenhar_totais_e_fiscal()
        self._desenhar_rodape()
        self.p.showPage()
        self.p.save()
        self.buffer.seek(0)
        return self.buffer

    def _gerar_termico(self):
        """Layout 80mm unificado para Vendas (FR/VD) e Recibos (RC)."""
        y = 390 * mm 
        
        # 1. Logo Empresa
        logo_io = self._obter_logo_empresa_io()
        if logo_io:
            self.p.drawInlineImage(logo_io, (self.width/2)-15*mm, y-15*mm, width=30*mm, preserveAspectRatio=True)
            y -= 20*mm

        # 2. Cabeçalho Empresa
        self.p.setFont("Helvetica-Bold", 10)
        self.p.drawCentredString(self.width/2, y, self.empresa.nome.upper())
        y -= 5*mm
        self.p.setFont("Helvetica", 7)
        self.p.drawCentredString(self.width/2, y, f"NIF: {self.empresa.nif}")
        y -= 4*mm
        self.p.drawCentredString(self.width/2, y, self.empresa.endereco[:45])
        
        # 3. Info do Documento (Dinâmico)
        y -= 8*mm
        # Detectar tipo (Venda ou Recibo)
        is_recibo = hasattr(self.venda, 'fatura') # Recibos possuem FK para fatura
        if is_recibo:
            tipo_nome = "RECIBO DE QUITAÇÃO"
            doc_numero = self.venda.numero_recibo
            data_doc = self.venda.data_recibo
        else:
            tipo_nome = dict(self.venda.TIPO_VENDA_CHOICES).get(self.venda.tipo_venda, "DOC. FISCAL")
            doc_numero = self.venda.numero_documento
            data_doc = self.venda.data_venda

        self.p.setFont("Helvetica-Bold", 9)
        self.p.drawString(self.margem, y, f"{tipo_nome}")
        self.p.drawRightString(self.width - self.margem, y, f"Nº {doc_numero}")
        y -= 5*mm
        self.p.setFont("Helvetica", 7)
        self.p.drawString(self.margem, y, f"Data: {data_doc.strftime('%d/%m/%Y %H:%M')}")
        
        y -= 3*mm
        self.p.line(self.margem, y, self.width - self.margem, y)
        
        # 4. Conteúdo (Híbrido: Itens de Venda ou Detalhe do Pagamento)
        y -= 5*mm
        self.p.setFont("Helvetica-Bold", 7)
        
        if is_recibo:
            # Layout para Recibo
            self.p.drawString(self.margem, y, "REF. DOCUMENTO")
            self.p.drawRightString(self.width - self.margem, y, "VALOR PAGO")
            y -= 4*mm
            self.p.setFont("Helvetica", 7)
            # No recibo, listamos a Fatura que foi liquidada
            desc_fatura = f"Liq. Fatura {self.venda.fatura.numero_documento}"
            self.p.drawString(self.margem, y, desc_fatura)
            self.p.drawRightString(self.width - self.margem, y, self._format_kz(self.venda.valor_pago))
            y -= 4*mm
            # Exibir forma de pagamento
            self.p.drawString(self.margem, y, f"Meio: {self.venda.forma_pagamento.nome}")
            y -= 4*mm
        else:
            # Layout para Venda (FR/VD)
            self.p.drawString(self.margem, y, "DESCRIÇÃO")
            self.p.drawRightString(self.width - self.margem, y, "TOTAL")
            y -= 4*mm
            self.p.setFont("Helvetica", 7)
            for item in self.venda.itens.all():
                desc = item.nome_produto if item.produto else item.nome_servico
                self.p.drawString(self.margem, y, f"{int(item.quantidade)}x {desc[:28]}")
                self.p.drawRightString(self.width - self.margem, y, self._format_kz(item.total))
                y -= 4*mm
        
        self.p.line(self.margem, y+1*mm, self.width - self.margem, y+1*mm)

        # 5. Totais
        y -= 5*mm
        self.p.setFont("Helvetica-Bold", 9)
        total_final = self.venda.valor_pago if is_recibo else self.venda.total
        self.p.drawString(self.margem, y, "TOTAL:")
        self.p.drawRightString(self.width - self.margem, y, self._format_kz(total_final))

        # 6. QR Code com Logo AGT
        y -= 35*mm
        qr_io = self._gerar_qr_com_logo_agt(box_size=5)
        self.p.drawInlineImage(qr_io, (self.width/2)-15*mm, y, width=30*mm, height=30*mm)

        # 7. Rodapé Legal (Regra SAF-T)
        y -= 8*mm
        self.p.setFont("Helvetica", 6)
        hash_4 = self._get_4_char_hash()
        self.p.drawCentredString(self.width/2, y, f"{hash_4} - Processado por programa certificado n.º {settings.AGT_CERTIFICATE_NUMBER}")
        y -= 4*mm
        self.p.drawCentredString(self.width/2, y, f"{settings.AGT_SOFTWARE_NAME} v{settings.AGT_SOFTWARE_VERSION}")

        self.p.showPage()
        self.p.save()
        self.buffer.seek(0)
        return self.buffer

    def _desenhar_cabecalho(self):
        # 1️⃣ LOGOTIPO DA EMPRESA (Cloudinary / URL)
        logo_empresa_width = 0
        if self.empresa.foto:
            try:
                response = requests.get(self.empresa.foto.url, timeout=5)
                img_data = io.BytesIO(response.content)
                self.p.drawInlineImage(img_data, self.margem_esq, self.height - 3*cm, width=4*cm, preserveAspectRatio=True)
                logo_empresa_width = 4.5 * cm
            except Exception as e:
                logger.error(f"Erro ao processar logo da empresa via URL: {e}")

        # Dados da Empresa (Posicionamento dinâmico conforme existência de logo)
        x_text = self.margem_esq + logo_empresa_width
        self.p.setFont("Helvetica-Bold", 12)
        self.p.drawString(x_text, self.height - 1.5*cm, self.empresa.nome.upper())
        self.p.setFont("Helvetica", 9)
        self.p.drawString(x_text, self.height - 2.0*cm, f"NIF: {self.empresa.nif}")
        self.p.drawString(x_text, self.height - 2.4*cm, f"Endereço: {self.empresa.endereco}, {self.empresa.cidade}")
        self.p.drawString(x_text, self.height - 2.8*cm, f"Tel: {self.empresa.telefone}")

        # Título do Documento
        tipo_nome = dict(self.venda.TIPO_VENDA_CHOICES).get(self.venda.tipo_venda, "DOCUMENTO FISCAL")
        self.p.setFont("Helvetica-Bold", 14)
        self.p.drawRightString(self.margem_dir, self.height - 1.5*cm, tipo_nome.upper())
        self.p.setFont("Helvetica-Bold", 11)
        self.p.drawRightString(self.margem_dir, self.height - 2.1*cm, f"Nº {self.venda.numero_documento}")

    def _desenhar_infos_documento(self):
        y = self.height - 5*cm
        # Box do Cliente
        self.p.setStrokeColor(colors.lightgrey)
        self.p.roundRect(self.margem_esq, y - 1.8*cm, 10*cm, 1.8*cm, 4, fill=0)
        self.p.setFont("Helvetica-Bold", 9)
        self.p.drawString(self.margem_esq + 0.3*cm, y - 0.5*cm, "EXCELENTÍSSIMO(A):")
        self.p.setFont("Helvetica", 9)
        cliente_nome = self.venda.cliente.nome_completo if self.venda.cliente else "Consumidor Final"
        self.p.drawString(self.margem_esq + 0.3*cm, y - 1.0*cm, cliente_nome)
        nif_cli = self.venda.cliente.nif if self.venda.cliente and self.venda.cliente.nif else "999999999"
        self.p.drawString(self.margem_esq + 0.3*cm, y - 1.4*cm, f"NIF: {nif_cli}")

    def _desenhar_corpo_itens(self):
        y = self.height - 8*cm
        # Cabeçalho da Tabela (Design Moderno Gray-50)
        self.p.setFillColor(colors.HexColor("#F3F4F6"))
        self.p.rect(self.margem_esq, y, 18*cm, 0.7*cm, fill=1, stroke=0)
        self.p.setFillColor(colors.black)
        self.p.setFont("Helvetica-Bold", 8)
        self.p.drawString(self.margem_esq + 0.2*cm, y + 0.2*cm, "DESCRIÇÃO")
        self.p.drawRightString(13*cm, y + 0.2*cm, "QTD")
        self.p.drawRightString(16*cm, y + 0.2*cm, "P. UNIT")
        self.p.drawRightString(self.margem_dir - 0.2*cm, y + 0.2*cm, "TOTAL")

        y -= 0.6*cm
        self.p.setFont("Helvetica", 8)
        # Lógica Híbrida: Itera entre Itens de Produto e de Serviço
        for item in self.venda.itens.all():
            desc = item.nome_produto if item.produto else item.nome_servico
            self.p.drawString(self.margem_esq + 0.2*cm, y, desc[:60])
            self.p.drawRightString(13*cm, y, str(item.quantidade))
            self.p.drawRightString(16*cm, y, self._format_kz(item.preco_unitario))
            self.p.drawRightString(self.margem_dir - 0.2*cm, y, self._format_kz(item.total))
            y -= 0.5*cm
            if y < 4*cm: # Controle de quebra de página
                self.p.showPage()
                y = self.height - 2*cm

    def _desenhar_totais_e_fiscal(self):
        y = 5*cm
        self.p.setFont("Helvetica-Bold", 10)
        self.p.drawRightString(16*cm, y, "TOTAL DOCUMENTO:")
        self.p.drawRightString(self.margem_dir, y, self._format_kz(self.venda.total))

        # 2️⃣ QR CODE COM LOGO DA AGT (Norma AGT 2026)
        qr = qrcode.QRCode(version=4, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(self._gerar_url_qr())
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        
        # Logo da AGT guardado em Assets/Static
        agt_logo_path = os.path.join(settings.STATIC_ROOT, 'img/fiscal/logo_agt_qr.png')
        if os.path.exists(agt_logo_path):
            logo = Image.open(agt_logo_path)
            box = (qr_img.size[0] // 2 - 25, qr_img.size[1] // 2 - 25, qr_img.size[0] // 2 + 25, qr_img.size[1] // 2 + 25)
            logo = logo.resize((50, 50))
            qr_img.paste(logo, box)

        qr_io = io.BytesIO()
        qr_img.save(qr_io, format='PNG')
        qr_io.seek(0)
        self.p.drawInlineImage(qr_io, self.margem_esq, 1.5*cm, width=3*cm, height=3*cm)

    def _desenhar_rodape(self):
        y = 1.2*cm
        self.p.setFont("Helvetica", 7)
        # Assinatura Legal e Dados do Software Certificado
        hash_4 = self._get_4_char_hash()
        legenda = f"{hash_4} - Processado por programa certificado n.º {settings.AGT_CERTIFICATE_NUMBER} {settings.AGT_SOFTWARE_NAME}"
        self.p.drawCentredText(self.width/2, y, legenda)
        
        req_id = self.venda.metadados.get('request_id_agt', 'VALIDAÇÃO ASSÍNCRONA')
        self.p.drawCentredText(self.width/2, y - 0.4*cm, f"Identificador de Submissão AGT (RequestID): {req_id}")




# apps/fiscal/services/pdf_agt_service.py
"""
Serviço de geração de PDFs fiscais — VistoGest Pro / SOTARQ Software.

Secção 4 do PLANO_IMPLEMENTACAO.md — redesign baseado no modelo AGT
(modelo_fatura.pdf) com identidade própria SOTARQ.

Layout A4 e 80mm suportados. Variantes por tipo de documento.

Campos AGT obrigatórios garantidos:
  - 4 caracteres do hash + " - Processado por programa válido n{numero}"
  - QR Code v4, error correction M, logo AGT ≤ 18% da área
  - Período Contabilístico (mês/ano)
  - operationType por linha
  - Regime fiscal da empresa no rodapé
  - Marca d'água "ANULADO" em documentos cancelados
  - Comentários/observações quando preenchidos
"""
import io
import logging
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP

import qrcode
import requests
from PIL import Image

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

logger = logging.getLogger('fiscal.pdf')

# ─────────────────────────────────────────────────────────────────────────────
# Constantes de cor (paleta SOTARQ)
# ─────────────────────────────────────────────────────────────────────────────
COR_PRIMARIA    = colors.HexColor('#1E40AF')   # azul SOTARQ
COR_CINZA_CABEC = colors.HexColor('#F3F4F6')   # fundo cabeçalho tabela
COR_CINZA_LINHA = colors.HexColor('#F9FAFB')   # linha alternada
COR_BORDA       = colors.HexColor('#E5E7EB')   # bordas finas
COR_ANULADO     = colors.Color(1, 0, 0, alpha=0.18)  # vermelho semitransparente


# ─────────────────────────────────────────────────────────────────────────────
# Helpers partilhados
# ─────────────────────────────────────────────────────────────────────────────

def _get_validation_number() -> str:
    val = getattr(settings, 'AGT_SOFTWARE_VALIDATION_NUMBER', '') or ''
    return val or '0'


def _get_4_char_hash(hash_documento: str) -> str:
    """Posições 0, 10, 20, 30 do SHA-256 — conforme notificação AGT."""
    h = hash_documento or ''
    if len(h) >= 31:
        return f"{h[0]}{h[10]}{h[20]}{h[30]}".upper()
    return '0000'


def _rodape_legal(p, width: float, y: float, hash_documento: str) -> None:
    """Linha obrigatória AGT: XXXX - Processado por programa válido n..."""
    hash_4 = _get_4_char_hash(hash_documento)
    num    = _get_validation_number()
    msg    = f"{hash_4} - Processado por programa válido n{num}"
    p.setFont("Helvetica", 6)
    p.drawCentredString(width / 2, y, msg)


def _marca_dagua_anulado(p, width: float, height: float) -> None:
    """Marca d'água diagonal vermelha 'ANULADO' para documentos cancelados."""
    p.saveState()
    p.setFillColor(COR_ANULADO)
    p.setFont("Helvetica-Bold", 80)
    p.translate(width / 2, height / 2)
    p.rotate(45)
    p.drawCentredString(0, 0, "ANULADO")
    p.restoreState()


def _gerar_qr_com_logo_agt(url: str, box_size: int = 10) -> io.BytesIO:
    """QR Code v4, error correction M, logo AGT ≤ 18%."""
    qr = qrcode.QRCode(
        version=4,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    logo_path = os.path.join(
        getattr(settings, 'STATIC_ROOT', ''), 'img/fiscal/logo_agt_qr.png'
    )
    if os.path.exists(logo_path):
        logo = Image.open(logo_path)
        qr_w, qr_h = qr_img.size
        logo_size = int(qr_w * 0.18)   # ≤ 18% — exigência AGT Decreto 683/25
        logo = logo.resize((logo_size, logo_size))
        pos = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
        qr_img.paste(logo, pos)

    buf = io.BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def _url_qr(nif_empresa: str, numero_documento: str) -> str:
    """URL do QR Code — Portal do Parceiro AGT (decisão do dono do sistema)."""
    doc_no = numero_documento.replace(' ', '%20')
    base = getattr(
        settings, 'AGT_QR_CODE_BASE_URL',
        'https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe',
    )
    return f"{base}?emissor={nif_empresa}&document={doc_no}"


def _fmt_kz(valor, casas: int = 2) -> str:
    """Formato monetário angolano com arredondamento por excesso."""
    if valor is None:
        return "0,00 Kz"
    v = Decimal(str(valor)).quantize(Decimal(f'1.{"0"*casas}'), rounding=ROUND_UP)
    return f"{v:,.2f} Kz".replace(',', 'X').replace('.', ',').replace('X', '.')


def _fmt_unit(valor) -> str:
    """Preço unitário com 4 casas decimais (norma SAF-T)."""
    if valor is None:
        return "0,0000"
    v = Decimal(str(valor)).quantize(Decimal('1.0000'), rounding=ROUND_HALF_UP)
    return f"{v:,.4f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _regime_label(regime: str) -> str:
    """
    Converte o código de regime fiscal AGT para label legível.
    Nota: Os valores do campo 'regime' (tipo de actividade: COMERCIO/SERVICOS/MISTO)
    NÃO devem ser passados aqui — este helper é para o campo 'regime_fiscal'.
    """
    labels = {
        'GERAL':        'Regime Geral',
        'SIMPLIFICADO': 'Regime Simplificado',
        'EXCLUSAO':     'Regime de Exclusão',
        'ESPECIAL':     'Regime Especial',
        # compatibilidade com valores em minúsculas (versões antigas)
        'geral':        'Regime Geral',
        'simplificado': 'Regime Simplificado',
        'exclusao':     'Regime de Exclusão',
        'especial':     'Regime Especial',
    }
    return labels.get(regime, regime or '')


def _operation_type_label(code: str) -> str:
    """Converte código operationType para descrição curta."""
    labels = {
        'SE': 'Serv. Território Nacional', 'SS': 'Serv. Estrangeiro',
        'STP': 'Telecom./Via Electrónica', 'SR': 'Serv. Imóveis',
        'SIF': 'Interm. Financeira',       'SHS': 'Hotelaria',
        'ST': 'Transporte',                'SG': 'Serv. Geral',
        'TB': 'Transmissão de Bens',       'AS': 'Aquisição Serviços',
        'QT': 'Outras Operações',          'RD': 'Regularizações',
    }
    return labels.get(code, code or '')


# ─────────────────────────────────────────────────────────────────────────────
# PDFDeclaracaoService — declaração de chaves para certificação AGT
# ─────────────────────────────────────────────────────────────────────────────

class PDFDeclaracaoService:
    """Gera o PDF de declaração para o processo de certificação junto da AGT."""

    @staticmethod
    def gerar_pdf_declaracao(empresa, assinatura):
        response = HttpResponse(content_type='application/pdf')
        nif = getattr(empresa, 'nif', 'sem_nif')
        response['Content-Disposition'] = f'attachment; filename="DECLARACAO_AGT_{nif}.pdf"'

        p = canvas.Canvas(response, pagesize=A4)
        width, height = A4
        y = height - 50

        p.setFont("Helvetica-Bold", 14)
        p.drawString(40, y, "DECLARAÇÃO OFICIAL PARA AGT — ASSINATURA DIGITAL")
        y -= 50

        p.setFont("Helvetica", 11)
        for linha in [
            f"Nome da Empresa: {empresa.nome}",
            f"NIF: {empresa.nif}",
            f"Regime: {_regime_label(getattr(empresa,'regime',''))}",
            f"Endereço: {getattr(empresa,'endereco','')} — {getattr(empresa,'cidade','')}",
        ]:
            p.drawString(40, y, linha)
            y -= 20
        y -= 20

        nif_contrib = getattr(assinatura, 'nif_contribuinte', '') or '—'
        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y, f"NIF do Contribuinte (chave AGT): {nif_contrib}")
        y -= 30

        chave_pub = getattr(assinatura, 'chave_contribuinte_publica', '') or ''
        if chave_pub:
            p.setFont("Helvetica-Bold", 11)
            p.drawString(40, y, "Chave Pública do Contribuinte (RSA — emitida pela AGT):")
            y -= 20
            p.setFont("Courier", 7)
            for linha in chave_pub.strip().split('\n'):
                p.drawString(40, y, linha)
                y -= 10
                if y < 80:
                    p.showPage()
                    y = height - 50

        y -= 25
        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y, "Último Hash (Cadeia de Integridade):")
        y -= 20
        p.setFont("Helvetica", 9)
        p.drawString(40, y, assinatura.ultimo_hash or "Ainda não gerado")

        p.setFont("Helvetica", 9)
        p.drawString(40, 70, "Declaro que os documentos emitidos obedecem ao regime de integridade fiscal digital.")
        p.drawString(40, 50, f"Luanda, {timezone.now().strftime('%d/%m/%Y %H:%M')}")
        p.showPage()
        p.save()
        return response


# ─────────────────────────────────────────────────────────────────────────────
# PDFDocumentoService — Fatura / Recibo / NC / ND / DT / FP para cliente
# ─────────────────────────────────────────────────────────────────────────────

class PDFDocumentoService:
    """
    Gera o PDF fiscal do documento para entrega ao cliente.
    Suporta A4 e 80mm (térmico). Detecta automaticamente se o documento está
    anulado e aplica marca d'água.

    Aceita:
        - documento_fiscal: instância de DocumentoFiscal (preferência)
        - venda_obj: instância de Venda ou FaturaCredito (compatibilidade)
    """

    # Etiquetas de tipo de documento para o cabeçalho do PDF
    TIPO_LABELS = {
        'FT': 'FACTURA',            'FR': 'FACTURA/RECIBO',
        'GF': 'FACTURA GENÉRICA',   'FG': 'FACTURA GLOBAL',
        'FA': 'FACTURA ADIANTAMENTO','AC': 'AVISO DE COBRANÇA',
        'AR': 'AVISO COBRANÇA/RECIBO','TV': 'TALÃO DE VENDA',
        'NC': 'NOTA DE CRÉDITO',    'ND': 'NOTA DE DÉBITO',
        'RE': 'ESTORNO',            'AF': 'AUTOFACTURAÇÃO',
        'RC': 'RECIBO',             'RG': 'RECIBO GERAL',
        'DT': 'GUIA DE REMESSA',    'FP': 'FACTURA PRÓ-FORMA',
        'RP': 'PRÉMIO/RECIBO',      'CS': 'CO-SEGURADORA',
        'LD': 'CO-SEGURADORA LÍDER','RA': 'RESSEGURO ACEITE',
    }

    # Watermarks por tipo
    WATERMARKS = {
        'FP': ('PRÓ-FORMA',   colors.Color(0, 0.4, 0.9, alpha=0.12)),
        'A':  ('ANULADO',     colors.Color(1, 0,   0,   alpha=0.18)),
    }

    def __init__(self, documento_fiscal=None, venda_obj=None, tamanho: str = 'a4'):
        # Aceitar DocumentoFiscal directamente (preferência) ou venda (fallback)
        self.doc_fiscal = documento_fiscal
        self.venda      = venda_obj or documento_fiscal  # fallback para venda

        # Empresa: do doc_fiscal, ou venda.empresa, ou connection.tenant
        self.empresa = (
            getattr(documento_fiscal, 'empresa', None)
            or getattr(venda_obj, 'empresa', None)
            or connection.tenant
        )

        self.tamanho = tamanho
        self.buffer  = io.BytesIO()

        # Tipo e status vêm do DocumentoFiscal quando disponível
        self._tipo   = getattr(documento_fiscal, 'tipo_documento', 'FR')
        self._status = getattr(documento_fiscal, 'status', getattr(venda_obj, 'status', ''))
        self._anulado = self._status in ('cancelled', 'cancelado', 'cancelada', 'A')

        if tamanho == '80mm':
            self.width  = 80 * mm
            self.height = 400 * mm
            self.p = canvas.Canvas(self.buffer, pagesize=(self.width, self.height))
            self.marg = 4 * mm
        else:
            self.p = canvas.Canvas(self.buffer, pagesize=A4)
            self.width, self.height = A4
            self.ml = 1.5 * cm   # margem esquerda
            self.mr = self.width - 1.5 * cm  # margem direita

    # ── Helpers internos ────────────────────────────────────────────────────

    def _hash(self) -> str:
        if self.doc_fiscal:
            return getattr(self.doc_fiscal, 'hash_documento', '') or ''
        return getattr(self.venda, 'hash_documento', '') or ''

    def _numero(self) -> str:
        if self.doc_fiscal:
            return getattr(self.doc_fiscal, 'numero_documento', '') or ''
        return (
            getattr(self.venda, 'numero_documento', None)
            or getattr(self.venda, 'numero_recibo', None)
            or getattr(self.venda, 'numero_nota', None) or ''
        )

    def _data(self):
        if self.doc_fiscal:
            return getattr(self.doc_fiscal, 'data_emissao', None) or timezone.now().date()
        return (
            getattr(self.venda, 'data_venda', None)
            or getattr(self.venda, 'data_fatura', None)
            or getattr(self.venda, 'data_recibo', None)
            or timezone.now()
        )

    def _periodo(self) -> str:
        """Campo obrigatório AGT: mês/ano da emissão."""
        try:
            d = self._data()
            return d.strftime('%m/%Y')
        except Exception:
            return ''

    def _regime_empresa(self) -> str:
        """Regime fiscal AGT da empresa — para PDFs e SAF-T."""
        return _regime_label(getattr(self.empresa, 'regime_fiscal', '') or '')

    def _tipo_label(self) -> str:
        return self.TIPO_LABELS.get(self._tipo, 'DOCUMENTO FISCAL')

    def _url_qr(self) -> str:
        return _url_qr(self.empresa.nif, self._numero())

    def _logo_empresa(self):
        foto = getattr(self.empresa, 'foto', None)
        if foto:
            try:
                r = requests.get(foto.url, timeout=5)
                return io.BytesIO(r.content)
            except Exception as e:
                logger.warning("Logo empresa indisponível: %s", e)
        return None

    def _linhas_doc(self):
        """Obtém as linhas do documento (DocumentoFiscalLinha ou ItemVenda)."""
        if self.doc_fiscal and hasattr(self.doc_fiscal, 'linhas'):
            linhas = list(self.doc_fiscal.linhas.all().order_by('numero_linha'))
            if linhas:
                return [self._linha_de_doc_fiscal(l) for l in linhas]
        # Fallback para ItemVenda / ItemFatura
        obj = self.venda
        if obj and hasattr(obj, 'itens'):
            return [self._linha_de_item(i) for i in obj.itens.all()]
        return []

    def _linha_de_doc_fiscal(self, linha) -> dict:
        taxa = getattr(linha, 'taxa_iva', None)
        return {
            'cod':        getattr(linha, 'codigo_produto', '') or '',
            'desc':       getattr(linha, 'descricao', '') or '',
            'op_type':    getattr(linha, 'operation_type', 'TB') or 'TB',
            'qtd':        str(linha.quantidade),
            'preco':      _fmt_unit(linha.valor_unitario),
            'desc_val':   _fmt_kz(getattr(linha, 'desconto_linha', Decimal('0'))),
            'taxa_iva':   f"{taxa.tax_percentage}%" if taxa else '0%',
            'isencao':    getattr(taxa, 'exemption_reason', '') if taxa else '',
            'total':      _fmt_kz(getattr(linha, 'valor_sem_iva', linha.valor_unitario)),
        }

    def _linha_de_item(self, item) -> dict:
        taxa = getattr(item, 'taxa_iva', None)
        return {
            'cod':      item.produto.codigo_interno if getattr(item, 'produto', None) else f"SRV-{getattr(item,'servico_id','?')}",
            'desc':     getattr(item, 'nome_produto', None) or getattr(item, 'nome_item', None) or getattr(item, 'nome_servico', None) or '',
            'op_type':  getattr(item, 'operation_type', 'TB') or 'TB',
            'qtd':      str(getattr(item, 'quantidade', 1)),
            'preco':    _fmt_unit(getattr(item, 'preco_unitario', 0)),
            'desc_val': _fmt_kz(getattr(item, 'desconto_item', Decimal('0'))),
            'taxa_iva': f"{taxa.tax_percentage}%" if taxa else '0%',
            'isencao':  getattr(taxa, 'exemption_reason', '') if taxa else '',
            'total':    _fmt_kz(getattr(item, 'subtotal_sem_iva', getattr(item, 'total', 0))),
        }

    def _totais(self) -> dict:
        obj = self.doc_fiscal or self.venda
        return {
            'base':     _fmt_kz(getattr(obj, 'valor_base', getattr(obj, 'subtotal', 0))),
            'iva':      _fmt_kz(getattr(obj, 'valor_iva', getattr(obj, 'iva_valor', 0))),
            'desconto': _fmt_kz(getattr(obj, 'valor_desconto', getattr(obj, 'desconto_valor', 0))),
            'total':    _fmt_kz(getattr(obj, 'valor_total', getattr(obj, 'total', 0))),
            'moeda':    getattr(obj, 'moeda', 'AOA'),
        }

    def _comentarios(self) -> str:
        """Campo operacional 'comentarios' do DocumentoFiscal."""
        if self.doc_fiscal:
            return getattr(self.doc_fiscal, 'comentarios', '') or ''
        return getattr(self.venda, 'observacoes', '') or ''

    # ── Ponto de entrada ────────────────────────────────────────────────────

    def gerar(self) -> io.BytesIO:
        if self.tamanho == '80mm':
            return self._gerar_termico()
        return self._gerar_a4()

    # ── Layout A4 ────────────────────────────────────────────────────────────

    def _gerar_a4(self) -> io.BytesIO:
        p = self.p
        w, h = self.width, self.height
        ml, mr = self.ml, self.mr

        # ── CABEÇALHO ──────────────────────────────────────────────────────
        y = h - 1.5 * cm
        logo_w = 0
        logo_io = self._logo_empresa()
        if logo_io:
            try:
                p.drawInlineImage(logo_io, ml, h - 3.5 * cm, width=4 * cm, preserveAspectRatio=True)
                logo_w = 4.5 * cm
            except Exception:
                pass

        # Dados da empresa
        x_emp = ml + logo_w
        p.setFont("Helvetica-Bold", 12)
        p.drawString(x_emp, h - 1.5 * cm, self.empresa.nome.upper()[:60])
        p.setFont("Helvetica", 8)
        p.drawString(x_emp, h - 2.0 * cm, f"NIF: {self.empresa.nif}  |  {_regime_label(getattr(self.empresa,'regime',''))}")
        p.drawString(x_emp, h - 2.4 * cm, f"{getattr(self.empresa,'endereco','')} — {getattr(self.empresa,'cidade','')}")
        p.drawString(x_emp, h - 2.8 * cm, f"Tel: {getattr(self.empresa,'telefone','')}")

        # Tipo + número do documento (caixa colorida à direita)
        tipo_label = self._tipo_label()
        numero = self._numero()
        p.setFillColor(COR_PRIMARIA)
        p.roundRect(mr - 8 * cm, h - 3.2 * cm, 8 * cm - 0.3 * cm, 2 * cm, 5, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 13)
        p.drawCentredString(mr - 4 * cm, h - 1.8 * cm, tipo_label)
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(mr - 4 * cm, h - 2.5 * cm, numero)
        p.setFillColor(colors.black)

        # Watermarks especiais
        if self._tipo == 'FP':
            self._watermark_texto(p, w, h, "PRÓ-FORMA", colors.Color(0, 0.4, 0.9, alpha=0.10))

        # Linha divisória
        y = h - 4 * cm
        p.setStrokeColor(COR_BORDA)
        p.line(ml, y, mr, y)
        y -= 0.3 * cm

        # ── DADOS DO ADQUIRENTE ────────────────────────────────────────────
        y -= 0.2 * cm
        # Bloco lado esquerdo
        p.setStrokeColor(COR_BORDA)
        p.roundRect(ml, y - 2.4 * cm, 10 * cm, 2.4 * cm, 4, fill=0, stroke=1)
        p.setFont("Helvetica-Bold", 8)
        p.drawString(ml + 0.3 * cm, y - 0.5 * cm, "EXCELENTÍSSIMO(A):")
        p.setFont("Helvetica", 8)
        cliente = getattr(self.doc_fiscal or self.venda, 'cliente', None)
        nome_cli = getattr(self.doc_fiscal, 'cliente_nome', None) if self.doc_fiscal else None
        nome_cli = nome_cli or (getattr(cliente, 'nome_completo', None) if cliente else 'Consumidor Final') or 'Consumidor Final'
        nif_cli  = getattr(self.doc_fiscal, 'cliente_nif', '') if self.doc_fiscal else (getattr(cliente, 'nif', '') if cliente else '')
        p.drawString(ml + 0.3 * cm, y - 1.0 * cm, nome_cli[:50])
        if nif_cli and nif_cli != '999999999':
            p.drawString(ml + 0.3 * cm, y - 1.5 * cm, f"NIF: {nif_cli}")
        else:
            p.drawString(ml + 0.3 * cm, y - 1.5 * cm, "Consumidor Final")
        p.drawString(ml + 0.3 * cm, y - 2.0 * cm, f"Período: {self._periodo()}")

        # Bloco lado direito
        data_d = self._data()
        data_str = data_d.strftime('%d/%m/%Y') if hasattr(data_d, 'strftime') else str(data_d)
        p.setFont("Helvetica", 8)
        p.drawRightString(mr, y - 0.5 * cm, f"Data: {data_str}")
        p.drawRightString(mr, y - 1.0 * cm, f"Regime: {self._regime_empresa()}")

        y -= 2.8 * cm

        # ── NOTA ESPECIAL POR TIPO ─────────────────────────────────────────
        if self._tipo == 'AF':
            p.setFont("Helvetica-Oblique", 7)
            p.setFillColor(colors.gray)
            p.drawString(ml, y, "Autofacturação — emitida pelo comprador em nome do fornecedor")
            p.setFillColor(colors.black)
            y -= 0.4 * cm

        doc_orig = getattr(self.doc_fiscal, 'documento_original', None) if self.doc_fiscal else None
        if doc_orig and self._tipo in ('NC', 'ND', 'RE'):
            p.setFont("Helvetica-Bold", 8)
            p.drawString(ml, y, f"Documento de Origem: {doc_orig.numero_documento}")
            y -= 0.5 * cm

        # ── TABELA DE ARTIGOS ──────────────────────────────────────────────
        y -= 0.2 * cm
        linhas = self._linhas_doc()
        col_widths = [1.2*cm, 4.5*cm, 2.8*cm, 1.2*cm, 2.0*cm, 1.5*cm, 1.5*cm, 2.0*cm]
        headers = ['Cód.', 'Descrição', 'Tipo Op.', 'Qtd', 'P.Unit.', 'Desc.', 'IVA', 'Total']
        table_data = [headers]

        for idx, l in enumerate(linhas):
            op_label = _operation_type_label(l['op_type'])
            taxa_display = l['isencao'] if l['taxa_iva'] == '0%' and l['isencao'] else l['taxa_iva']
            table_data.append([
                l['cod'][:12], l['desc'][:40], op_label[:22],
                l['qtd'], l['preco'], l['desc_val'], taxa_display, l['total'],
            ])

        if not linhas:
            table_data.append(['—', '(sem linhas)', '—', '—', '—', '—', '—', '—'])

        from reportlab.platypus import Table, TableStyle as TS
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TS([
            ('BACKGROUND',  (0,0), (-1,0), COR_CINZA_CABEC),
            ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0,0), (-1,-1), 7),
            ('GRID',        (0,0), (-1,-1), 0.3, COR_BORDA),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, COR_CINZA_LINHA]),
            ('ALIGN',       (3,0), (-1,-1), 'RIGHT'),
            ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',  (0,0), (-1,-1), 2),
            ('BOTTOMPADDING',(0,0),(-1,-1), 2),
        ]))
        t_w, t_h = tbl.wrapOn(p, mr - ml, h)
        y -= t_h
        if y < 5 * cm:
            if self._anulado:
                _marca_dagua_anulado(p, w, h)
            p.showPage()
            y = h - 2 * cm
        tbl.drawOn(p, ml, y)
        y -= 0.5 * cm

        # ── TOTAIS ─────────────────────────────────────────────────────────
        tot = self._totais()
        x_tot = mr - 7 * cm
        p.setFont("Helvetica", 8)
        for label, valor in [
            ("Base Tributável:", tot['base']),
            ("IVA:",             tot['iva']),
            ("Desconto:",        tot['desconto']),
        ]:
            p.drawString(x_tot, y, label)
            p.drawRightString(mr, y, valor)
            y -= 0.5 * cm

        p.setFont("Helvetica-Bold", 10)
        p.drawString(x_tot, y, "TOTAL A PAGAR:")
        p.drawRightString(mr, y, tot['total'])
        y -= 0.7 * cm

        # Moeda estrangeira
        moeda = tot['moeda']
        if moeda and moeda != 'AOA' and self.doc_fiscal:
            taxa_cambio = getattr(self.doc_fiscal, 'taxa_cambio', 1) or 1
            valor_total_raw = getattr(self.doc_fiscal, 'valor_total', 0) or 0
            valor_moeda = Decimal(str(valor_total_raw)) / Decimal(str(taxa_cambio))
            p.setFont("Helvetica", 7)
            p.drawRightString(mr, y, f"{moeda}: {_fmt_kz(valor_moeda)} (câmbio: {taxa_cambio})")
            y -= 0.5 * cm

        # ── COMENTÁRIOS ────────────────────────────────────────────────────
        comentarios = self._comentarios()
        if comentarios:
            y -= 0.3 * cm
            p.setStrokeColor(COR_BORDA)
            p.roundRect(ml, y - 1.5 * cm, mr - ml, 1.5 * cm, 4, fill=0, stroke=1)
            p.setFont("Helvetica-Bold", 7)
            p.drawString(ml + 0.3 * cm, y - 0.4 * cm, "Observações:")
            p.setFont("Helvetica", 7)
            p.drawString(ml + 0.3 * cm, y - 0.9 * cm, comentarios[:120])
            y -= 1.8 * cm

        # ── QR CODE + RODAPÉ LEGAL ─────────────────────────────────────────
        qr_y = 1.5 * cm
        qr_io = _gerar_qr_com_logo_agt(self._url_qr(), box_size=10)
        p.drawInlineImage(qr_io, ml, qr_y, width=3 * cm, height=3 * cm)

        # Rodapé — lado direito do QR
        p.setFont("Helvetica", 6)
        rx = ml + 3.5 * cm
        ry = qr_y + 1.8 * cm
        _rodape_legal(p, w, ry, self._hash())
        p.drawString(rx, ry - 0.4 * cm,
                     f"VistoGest Pro — SOTARQ Software  |  NIF: {getattr(settings,'AGT_PRODUCT_COMPANY_TAX_ID','5002764377')}")
        p.drawString(rx, ry - 0.8 * cm,
                     f"Regime: {self._regime_empresa()}")

        req_id = (getattr(self.doc_fiscal, 'metadados', {}) or {}).get('request_id_agt', '')
        if req_id:
            p.drawString(rx, ry - 1.2 * cm, f"RequestID AGT: {req_id}")

        # Marca de documento ANULADO — sobre todo o conteúdo
        if self._anulado:
            _marca_dagua_anulado(p, w, h)
            p.setFillColor(colors.red)
            p.setFont("Helvetica-Bold", 14)
            p.drawCentredString(w / 2, h - 0.8 * cm, "⚠ DOCUMENTO ANULADO ⚠")
            p.setFillColor(colors.black)

        p.showPage()
        p.save()
        self.buffer.seek(0)
        return self.buffer

    def _watermark_texto(self, p, width, height, texto, cor):
        p.saveState()
        p.setFillColor(cor)
        p.setFont("Helvetica-Bold", 60)
        p.translate(width / 2, height / 2)
        p.rotate(45)
        p.drawCentredString(0, 0, texto)
        p.restoreState()

    # ── Layout térmico 80mm ──────────────────────────────────────────────────

    def _gerar_termico(self) -> io.BytesIO:
        p = self.p
        w  = self.width
        mg = self.marg
        y  = self.height - 5 * mm

        # Logo empresa
        logo_io = self._logo_empresa()
        if logo_io:
            try:
                p.drawInlineImage(logo_io, (w/2)-15*mm, y-15*mm, width=30*mm, preserveAspectRatio=True)
                y -= 20 * mm
            except Exception:
                pass

        # Cabeçalho empresa
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(w/2, y, self.empresa.nome.upper()[:35])
        y -= 4*mm
        p.setFont("Helvetica", 7)
        p.drawCentredString(w/2, y, f"NIF: {self.empresa.nif}")
        y -= 3*mm
        p.drawCentredString(w/2, y, f"{_regime_label(getattr(self.empresa,'regime',''))}")
        y -= 3*mm
        p.drawCentredString(w/2, y, str(getattr(self.empresa,'endereco',''))[:40])
        y -= 7*mm

        # Tipo e número do documento
        tipo_label = self._tipo_label()
        numero = self._numero()
        data_str = self._data().strftime('%d/%m/%Y %H:%M') if hasattr(self._data(), 'strftime') else ''
        p.setFont("Helvetica-Bold", 9)
        p.drawString(mg, y, tipo_label)
        p.drawRightString(w-mg, y, f"Nº {numero}")
        y -= 5*mm
        p.setFont("Helvetica", 7)
        p.drawString(mg, y, f"Data: {data_str}")
        p.drawRightString(w-mg, y, f"Período: {self._periodo()}")
        y -= 3*mm
        p.line(mg, y, w-mg, y)
        y -= 4*mm

        # Linhas
        p.setFont("Helvetica-Bold", 7)
        p.drawString(mg, y, "DESCRIÇÃO")
        p.drawRightString(w-mg, y, "TOTAL")
        y -= 3*mm
        p.setFont("Helvetica", 7)
        for l in self._linhas_doc():
            desc = l['desc'][:28]
            op   = l['op_type']  # código curto por falta de espaço
            p.drawString(mg, y, f"{l['qtd']}x {desc} [{op}]")
            p.drawRightString(w-mg, y, l['total'])
            y -= 4*mm

        p.line(mg, y+1*mm, w-mg, y+1*mm)
        y -= 4*mm

        # Total
        tot = self._totais()
        p.setFont("Helvetica-Bold", 9)
        p.drawString(mg, y, "TOTAL:")
        p.drawRightString(w-mg, y, tot['total'])
        y -= 6*mm

        # Comentários (se existirem)
        comentarios = self._comentarios()
        if comentarios:
            p.setFont("Helvetica", 6)
            p.drawString(mg, y, f"Obs: {comentarios[:50]}")
            y -= 4*mm

        # QR Code
        y -= 30*mm
        qr_io = _gerar_qr_com_logo_agt(self._url_qr(), box_size=5)
        p.drawInlineImage(qr_io, (w/2)-15*mm, y, width=30*mm, height=30*mm)
        y -= 8*mm

        # Rodapé legal
        _rodape_legal(p, w, y, self._hash())
        y -= 3*mm
        p.setFont("Helvetica", 5)
        p.drawCentredString(w/2, y, f"Regime: {self._regime_empresa()}")

        if self._anulado:
            _marca_dagua_anulado(p, w, self.height)

        p.showPage()
        p.save()
        self.buffer.seek(0)
        return self.buffer

"""Geração de PDFs fiscais do VistoGest Pro / SOTARQ Software.

Inclui declaração de assinatura fiscal e documentos fiscais para cliente.
O layout de faturas usa Platypus para permitir texto extenso, quebra de página
correcta e repetição dos cabeçalhos das tabelas.

NOTA: a validade legal do conteúdo/QR e o estado da certificação AGT dependem
igualmente da configuração e do fluxo fiscal do sistema. A geração do PDF não
substitui essa validação.
"""
from __future__ import annotations

import io
import logging
import os
import math
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape as _esc

logger = logging.getLogger("fiscal.pdf")

# Paleta SOTARQ: azul sóbrio, fundos claros e linhas discretas.
COR_PRIMARIA = colors.HexColor("#1E40AF")
COR_PRIMARIA_ESCURA = colors.HexColor("#1E3A8A")
COR_CINZA_CABEC = colors.HexColor("#EFF3F8")
COR_CINZA_LINHA = colors.HexColor("#F8FAFC")
COR_TEXTO = colors.HexColor("#1F2937")
COR_TEXTO_SEC = colors.HexColor("#64748B")
COR_BORDA = colors.HexColor("#D9E1EC")
COR_ANULADO = colors.Color(0.80, 0.04, 0.08, alpha=0.14)
COR_PROFORMA = colors.Color(0.08, 0.28, 0.78, alpha=0.10)

ZERO = Decimal("0.00")
CENTAVO = Decimal("0.01")


def _decimal(valor, default=ZERO) -> Decimal:
    """Converte um valor para Decimal sem propagar None/valores inválidos."""
    if valor is None or valor == "":
        return default
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _fmt_numero(valor, casas: int = 2) -> str:
    """Formata números com separadores usados em Angola: 1.234,56."""
    d = _decimal(valor).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    return f"{d:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_kz(valor, casas: int = 2) -> str:
    """Compatibilidade com chamadas antigas; arredonda ao cêntimo, sem excesso."""
    return f"{_fmt_numero(valor, casas)} Kz"


def _fmt_unit(valor) -> str:
    """Preço unitário apresentado com quatro casas decimais."""
    return _fmt_numero(valor, 4)


def _fmt_quantidade(valor) -> str:
    """Apresenta até três casas decimais, removendo zeros não significativos."""
    texto = _fmt_numero(_decimal(valor), 3)
    return texto.rstrip("0").rstrip(",") if "," in texto else texto


def _fmt_moeda(valor, moeda: str = "AOA") -> str:
    codigo = (moeda or "AOA").upper()
    sufixo = "Kz" if codigo == "AOA" else codigo
    return f"{_fmt_numero(valor, 2)} {sufixo}"


def _safe_text(value) -> str:
    """Limita texto à codificação suportada pelas fontes PDF base do ReportLab."""
    if value is None:
        return ""
    texto = str(value)
    # As fontes Helvetica/Courier incluídas no ReportLab usam WinAnsi.
    # Os caracteres portugueses são preservados; emojis não suportados viram '?'.
    return texto.encode("cp1252", errors="replace").decode("cp1252")


def _p_text(value) -> str:
    """Escapa texto externo antes de o inserir num Paragraph/markup ReportLab."""
    return _esc(_safe_text(value)).replace("\n", "<br/>")


def _get_validation_number() -> str:
    val = getattr(settings, "AGT_SOFTWARE_VALIDATION_NUMBER", "") or ""
    return str(val).strip() or "0"


def _get_4_char_hash(hash_documento: str) -> str:
    """Extrai as posições 0, 10, 20 e 30 do hash SHA-256, quando disponíveis."""
    h = str(hash_documento or "")
    if len(h) >= 31:
        return f"{h[0]}{h[10]}{h[20]}{h[30]}".upper()
    return "0000"


def _rodape_legal(p, width: float, y: float, hash_documento: str) -> None:
    """Linha curta de identificação do software e do hash para o rodapé."""
    msg = f"{_get_4_char_hash(hash_documento)} - Processado por programa válido n{_get_validation_number()}"
    p.saveState()
    p.setFillColor(COR_TEXTO_SEC)
    p.setFont("Helvetica", 6)
    p.drawCentredString(width / 2, y, _safe_text(msg))
    p.restoreState()


def _marca_dagua_anulado(p, width: float, height: float) -> None:
    p.saveState()
    p.setFillColor(COR_ANULADO)
    p.setFont("Helvetica-Bold", 64 if width > 300 else 24)
    p.translate(width / 2, height / 2)
    p.rotate(38)
    p.drawCentredString(0, 0, "ANULADO")
    p.restoreState()


def _marca_dagua_texto(p, width: float, height: float, texto: str, cor) -> None:
    p.saveState()
    p.setFillColor(cor)
    p.setFont("Helvetica-Bold", 54 if width > 300 else 20)
    p.translate(width / 2, height / 2)
    p.rotate(38)
    p.drawCentredString(0, 0, _safe_text(texto))
    p.restoreState()


def _static_logo_agt_path():
    """Localiza o logótipo de consulta AGT sem depender apenas de STATIC_ROOT."""
    try:
        from django.contrib.staticfiles import finders
        encontrado = finders.find("img/fiscal/logo_agt_qr.png")
        if encontrado and os.path.isfile(encontrado):
            return encontrado
    except Exception:
        pass

    raiz = getattr(settings, "STATIC_ROOT", "") or ""
    candidato = os.path.join(raiz, "img", "fiscal", "logo_agt_qr.png")
    return candidato if os.path.isfile(candidato) else None


def _gerar_qr_com_logo_agt(url: str, box_size: int = 8) -> io.BytesIO:
    """Gera QR legível; o logótipo central, se existir, ocupa uma área pequena."""
    qr = qrcode.QRCode(
        version=4,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=3,
    )
    qr.add_data(url)
    # O QR pode subir automaticamente de versão se o URL for maior que a capacidade
    # da versão 4; é preferível manter um código funcional a truncar a consulta.
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    logo_path = _static_logo_agt_path()
    if logo_path:
        try:
            with Image.open(logo_path) as original:
                logo = original.convert("RGBA")
            qr_w, qr_h = qr_img.size
            logo_size = max(1, int(min(qr_w, qr_h) * 0.18))
            resampling = getattr(Image, "Resampling", Image)
            lanczos = getattr(resampling, "LANCZOS", 1)
            logo.thumbnail((logo_size, logo_size), lanczos)
            pos = ((qr_w - logo.width) // 2, (qr_h - logo.height) // 2)
            # Placa branca para manter o contraste e a leitura do QR.
            padding = max(2, int(logo_size * 0.10))
            placa = Image.new("RGB", (logo.width + 2 * padding, logo.height + 2 * padding), "white")
            px = max(0, (qr_w - placa.width) // 2)
            py = max(0, (qr_h - placa.height) // 2)
            qr_img.paste(placa, (px, py))
            qr_img.paste(logo, (px + padding, py + padding), logo)
        except Exception as exc:
            logger.warning("Não foi possível aplicar o logótipo AGT ao QR: %s", exc)

    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _url_qr(nif_empresa: str, numero_documento: str) -> str:
    """Monta o URL de consulta preservando parâmetros que já estejam na base."""
    base = getattr(
        settings,
        "AGT_QR_CODE_BASE_URL",
        #"https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe",
    )
    base = str(base or "").strip()
    if not base:
        return ""
    partes = urlsplit(base)
    parametros = dict(parse_qsl(partes.query, keep_blank_values=True))
    parametros.update({"emissor": str(nif_empresa or ""), "document": str(numero_documento or "")})
    return urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(parametros), partes.fragment))


def _regime_label(regime: str) -> str:
    """Converte códigos de regime fiscal para rótulos legíveis."""
    if not regime:
        return ""
    codigo = str(regime).strip().upper()
    labels = {
        "GERAL": "Regime Geral",
        "SIMPLIFICADO": "Regime Simplificado",
        "EXCLUSAO": "Regime de Exclusão",
        "ESPECIAL": "Regime Especial",
        "OUTROS": "Regime Especial / Outro",
    }
    return labels.get(codigo, _safe_text(regime))


def _operation_type_label(code: str) -> str:
    labels = {
        "SE": "Serviços em território nacional",
        "SS": "Serviços no estrangeiro",
        "STP": "Telecomunicações / via electrónica",
        "SR": "Serviços relativos a imóveis",
        "SIF": "Intermediação financeira",
        "SHS": "Hotelaria e similares",
        "ST": "Transporte",
        "SG": "Serviços em geral",
        "TB": "Transmissão de bens",
        "AS": "Aquisição de serviços",
        "QT": "Outras operações tributáveis",
        "RD": "Regularizações e devoluções",
    }
    code = str(code or "").strip().upper()
    return labels.get(code, code or "Não indicado")


class PDFDeclaracaoService:
    """Gera PDF de declaração para o processo de certificação junto da AGT."""

    @staticmethod
    def gerar_pdf_declaracao(empresa, assinatura):
        response = HttpResponse(content_type="application/pdf")
        nif = getattr(empresa, "nif", "sem_nif") or "sem_nif"
        response["Content-Disposition"] = f'attachment; filename="DECLARACAO_AGT_{nif}.pdf"'

        p = canvas.Canvas(response, pagesize=A4)
        width, height = A4
        y = height - 50
        p.setFont("Helvetica-Bold", 14)
        p.drawString(40, y, _safe_text("DECLARAÇÃO PARA AGT — ASSINATURA DIGITAL"))
        y -= 50

        p.setFont("Helvetica", 11)
        nome = getattr(empresa, "nome", None) or getattr(empresa, "razao_social", "")
        linhas = [
            f"Nome da Empresa: {nome}",
            f"NIF: {getattr(empresa, 'nif', '')}",
            f"Regime: {_regime_label(getattr(empresa, 'regime_fiscal', '') or getattr(empresa, 'regime', ''))}",
            f"Endereço: {getattr(empresa, 'endereco', '')} — {getattr(empresa, 'cidade', '')}",
        ]
        for linha in linhas:
            p.drawString(40, y, _safe_text(linha)[:110])
            y -= 20
        y -= 20

        nif_contrib = getattr(assinatura, "nif_contribuinte", "") or "—"
        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y, _safe_text(f"NIF do Contribuinte (chave AGT): {nif_contrib}")[:110])
        y -= 30

        chave_pub = getattr(assinatura, "chave_contribuinte_publica", "") or ""
        if chave_pub:
            p.setFont("Helvetica-Bold", 11)
            p.drawString(40, y, "Chave Pública do Contribuinte (RSA — emitida pela AGT):")
            y -= 20
            p.setFont("Courier", 6.5)
            for linha in chave_pub.strip().splitlines():
                if y < 65:
                    p.showPage()
                    y = height - 50
                    p.setFont("Courier", 6.5)
                p.drawString(40, y, _safe_text(linha)[:115])
                y -= 9

        y = max(y - 20, 100)
        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y, "Último Hash (Cadeia de Integridade):")
        y -= 18
        p.setFont("Helvetica", 9)
        p.drawString(40, y, _safe_text(getattr(assinatura, "ultimo_hash", "") or "Ainda não gerado")[:110])
        p.setFont("Helvetica", 8)
        p.drawString(40, 50, _safe_text(f"Luanda, {timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')}"))
        p.showPage()
        p.save()
        return response



from datetime import date, datetime, time


class _PDFNumberedCanvas(canvas.Canvas):
    """Canvas ReportLab que imprime Página X de Y."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_paginas = len(self._saved_page_states)
        for estado in self._saved_page_states:
            self.__dict__.update(estado)
            if self._pageNumber == total_paginas:
                servico = getattr(self, "_pdf_document_service", None)
                if servico is not None:
                    servico._desenhar_rodape_final(self)
            self.saveState()
            self.setFont("Helvetica", 6)
            self.setFillColor(COR_TEXTO_SEC)
            largura, _ = self._pagesize
            self.drawRightString(
                largura - getattr(self, "_pdf_right_margin", 15 * mm),
                8 * mm,
                f"Página {self._pageNumber} de {total_paginas}",
            )
            self.restoreState()
            super().showPage()
        super().save()


class PDFDocumentoService:
    """Gera documentos comerciais/fiscais A4 ou térmicos sem recalcular impostos.

    Compatibilidade mantida:
        PDFDocumentoService(documento_fiscal=doc).gerar()
        PDFDocumentoService(venda_obj=venda, tamanho="80mm").gerar()

    A identidade do emitente é resolvida a partir da Empresa do tenant activo.
    Os valores fiscais persistidos têm prioridade; o PDF apenas os apresenta.
    """

    TIPO_LABELS = {
        "FT": "FACTURA",
        "FR": "FACTURA/RECIBO",
        "GF": "FACTURA GENÉRICA",
        "FG": "FACTURA GLOBAL",
        "FA": "FACTURA DE ADIANTAMENTO",
        "AC": "AVISO DE COBRANÇA",
        "AR": "AVISO DE COBRANÇA/RECIBO",
        "TV": "TALÃO DE VENDA",
        "NC": "NOTA DE CRÉDITO",
        "ND": "NOTA DE DÉBITO",
        "RE": "ESTORNO",
        "AF": "AUTOFACTURAÇÃO",
        "RC": "RECIBO",
        "RG": "RECIBO GERAL",
        "DT": "GUIA DE TRANSPORTE",
        "FP": "FACTURA PROFORMA",
        "RP": "PRÉMIO/RECIBO",
        "CS": "CO-SEGURADORA",
        "LD": "CO-SEGURADORA LÍDER",
        "RA": "RESSEGURO ACEITE",
    }

    STATUS_ANULADO = {
        "a", "anulado", "anulada", "cancelado", "cancelada",
        "cancelled", "canceled", "void", "voided",
    }
    STATUS_RASCUNHO = {
        "draft", "rascunho", "pendente", "pending", "calculado",
        "não emitido", "nao emitido", "new", "novo",
    }

    # Paleta neutra da factura: a cor da marca fica no logótipo da empresa.
    DOC_CINZA_TOPO = colors.HexColor("#E5E7EB")
    DOC_CINZA_CABEC = colors.HexColor("#D9DDE3")
    DOC_CINZA_LINHA = colors.HexColor("#F3F4F6")
    DOC_TEXTO = colors.HexColor("#171717")
    DOC_TEXTO_SEC = colors.HexColor("#52525B")
    DOC_BORDA = colors.HexColor("#C7CBD1")

    def __init__(
        self,
        documento_fiscal=None,
        venda_obj=None,
        tamanho: str = "a4",
        configuracao_fiscal=None,
    ):
        self.doc_fiscal = documento_fiscal
        self.venda = venda_obj or documento_fiscal
        self._empresa_documento = (
            getattr(documento_fiscal, "empresa", None)
            or getattr(venda_obj, "empresa", None)
        )
        self.empresa = self._resolver_empresa_oficial()
        self.tamanho = (
            "80mm"
            if str(tamanho or "a4").strip().lower()
            in {"80mm", "80", "termico", "térmico"}
            else "a4"
        )
        self.buffer = io.BytesIO()
        self.config_fiscal = configuracao_fiscal or self._obter_configuracao_fiscal()
        self._logo_cache = None
        self._linhas_cache = None
        self._totais_cache = None
        self._qr_footer_data = None

        self._tipo = str(
            self._campo(self.doc_fiscal, "tipo_documento", default="")
            or self._campo(self.venda, "tipo_documento", default="FR")
            or "FR"
        ).strip().upper()
        self._status = str(
            self._campo(self.doc_fiscal, "status", "estado", default="")
            or self._campo(self.venda, "status", "estado", default="")
            or ""
        ).strip().lower()
        self._anulado = self._status in self.STATUS_ANULADO
        self._proforma = self._tipo == "FP"
        self._numero_guardado = self._numero()
        self._rascunho = self._status in self.STATUS_RASCUNHO or not self._numero_guardado

        self.width, self.height = (
            (80 * mm, 300 * mm) if self.tamanho == "80mm" else A4
        )

    # ------------------------------------------------------------------
    # Resolução de dados e tenant
    # ------------------------------------------------------------------
    @staticmethod
    def _campo(obj, *nomes, default=""):
        for nome in nomes:
            try:
                valor = getattr(obj, nome, None) if obj is not None else None
            except Exception:
                valor = None
            if callable(valor):
                continue
            if valor is not None and str(valor).strip() != "":
                return valor
        return default

    @classmethod
    def _decimal_opcional(cls, obj, *nomes):
        valor = cls._campo(obj, *nomes, default=None)
        if valor is None or valor == "":
            return None
        try:
            return Decimal(str(valor))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _resolver_empresa_oficial(self):
        """Resolve Empresa do tenant activo; não confia em identidade duplicada."""
        schema = getattr(connection, "schema_name", None)
        try:
            from django_tenants.utils import get_public_schema_name
            schema_publico = get_public_schema_name()
        except Exception:
            schema_publico = "public"

        if not schema or schema == schema_publico:
            logger.warning(
                "PDF fiscal solicitado sem tenant activo válido; schema=%s", schema
            )
            return None

        try:
            from apps.empresas.services import obter_empresa_do_schema
            empresa = obter_empresa_do_schema()
            schema_empresa = getattr(empresa, "schema_name", None)
            if schema_empresa and schema_empresa != schema:
                raise ValueError("A empresa resolvida não corresponde ao schema activo.")
            return empresa
        except Exception as exc:
            logger.warning(
                "Não foi possível resolver Empresa pelo serviço oficial: %s", exc
            )

        # Fallback apenas para um tenant que corresponda ao schema corrente.
        tenant = getattr(connection, "tenant", None)
        schema_tenant = getattr(tenant, "schema_name", None)
        if tenant is not None and schema_tenant == schema:
            return tenant

        # Compatibilidade com modelos antigos: aceitar a FK apenas quando traz
        # um schema explícito e coincidente. Não usar identidade de outra empresa.
        schema_empresa = getattr(self._empresa_documento, "schema_name", None)
        if self._empresa_documento is not None and schema_empresa == schema:
            return self._empresa_documento

        return None

    def _obter_configuracao_fiscal(self):
        """Obtém apenas configurações auxiliares do schema activo."""
        try:
            from apps.configuracoes.models import ConfiguracaoFiscal
            return ConfiguracaoFiscal.objects.first()
        except Exception as exc:
            logger.debug("Configuração fiscal auxiliar indisponível: %s", exc)
            return None

    def _obter_personalizacao_interface(self):
        try:
            from apps.configuracoes.models import PersonalizacaoInterface
            return PersonalizacaoInterface.objects.first()
        except Exception as exc:
            logger.debug("Personalização de interface indisponível: %s", exc)
            return None

    def _dados_emissor(self) -> dict:
        """Identidade fiscal: Empresa oficial primeiro, sem sobreposição de cfg."""
        empresa = self.empresa
        if empresa is None:
            logger.error(
                "PDF sem Empresa oficial; schema=%s", getattr(connection, "schema_name", None)
            )

        nome = self._campo(
            empresa, "nome_fantasia", "nome", "razao_social", default=""
        ) or "Empresa emissora"
        razao_social = self._campo(empresa, "razao_social", "nome", default="")
        
        
        nif_empresa = str(
            self._campo(
                empresa,
                "nif",
                "numero_identificacao_fiscal",
                default="",
            ) or ""
        ).strip()

        nif_configuracao = str(
            self._campo(
                self.config_fiscal,
                "nif",
                default="",
            ) or ""
        ).strip()

        if (
            nif_empresa
            and nif_configuracao
            and nif_empresa.replace(" ", "") != nif_configuracao.replace(" ", "")
        ):
            logger.error(
                "O NIF de Empresa diverge do NIF de ConfiguracaoFiscal "
                "no schema %s. Será utilizado o NIF da Empresa.",
                getattr(connection, "schema_name", None),
            )

        nif = nif_empresa or nif_configuracao



        regime = self._campo(
            empresa, "regime_fiscal", "regime_tributario", "regime", default=""
        )
        endereco = self._campo(empresa, "endereco", "morada", "endereco_completo", default="")
        cidade = self._campo(empresa, "cidade", "municipio", default="")
        provincia = self._campo(empresa, "provincia", default="")
        postal = self._campo(empresa, "postal", "codigo_postal", default="")
        localidade = ", ".join(
            str(v).strip() for v in (cidade, provincia, postal) if str(v or "").strip()
        )
        morada_completa = " — ".join(
            str(v).strip() for v in (endereco, localidade) if str(v or "").strip()
        )

        return {
            "nome": _safe_text(nome),
            "razao_social": _safe_text(razao_social),
            "nif": _safe_text(nif),
            "email": _safe_text(self._campo(empresa, "email", default="")),
            "site": _safe_text(self._campo(self.config_fiscal, "site", default="") or self._campo(empresa, "site", "website", default="")),
            "telefone": _safe_text(
                self._campo(empresa, "telefone", "telemovel", "contacto", default="")
            ),
            "endereco": _safe_text(morada_completa),
            "regime": _regime_label(regime),
        }

    # ------------------------------------------------------------------
    # Logótipo: primeiro Empresa; depois personalização do tenant
    # ------------------------------------------------------------------
    def _ler_logo_field(self, field) -> io.BytesIO | None:
        if not field:
            return None
        if isinstance(field, (bytes, bytearray)):
            return io.BytesIO(bytes(field))

        if isinstance(field, (str, os.PathLike)):
            caminho = os.fspath(field).strip()
            if caminho and os.path.isfile(caminho):
                try:
                    with open(caminho, "rb") as ficheiro:
                        return io.BytesIO(ficheiro.read())
                except OSError:
                    return None

        if hasattr(field, "open") and hasattr(field, "read"):
            try:
                try:
                    field.open("rb")
                except TypeError:
                    field.open()
                conteudo = field.read()
                try:
                    field.close()
                except Exception:
                    pass
                if conteudo:
                    return io.BytesIO(conteudo)
            except Exception:
                try:
                    field.close()
                except Exception:
                    pass

        # Compatibilidade para URL de storage. Limita tamanho e timeout.
        url = getattr(field, "url", None)
        if isinstance(field, str) and field.strip().startswith(("https://", "http://")):
            url = field.strip()
        if url:
            resposta = None
            try:
                partes = urlsplit(str(url))
                if partes.scheme not in {"https", "http"} or not partes.netloc:
                    return None
                resposta = requests.get(str(url), timeout=(2, 5), stream=True)
                resposta.raise_for_status()
                tamanho = int(resposta.headers.get("Content-Length", "0") or 0)
                if tamanho > 5 * 1024 * 1024:
                    return None
                blocos, total = [], 0
                for bloco in resposta.iter_content(chunk_size=64 * 1024):
                    if not bloco:
                        continue
                    total += len(bloco)
                    if total > 5 * 1024 * 1024:
                        return None
                    blocos.append(bloco)
                if blocos:
                    return io.BytesIO(b"".join(blocos))
            except Exception as exc:
                logger.warning("Não foi possível carregar logótipo: %s", exc)
            finally:
                if resposta is not None:
                    resposta.close()
        return None

    
    def _logo_empresa(self) -> io.BytesIO | None:
        """Carrega o logótipo e regista a fonte utilizada no PDF."""
        if self._logo_cache is not None:
            self._logo_cache.seek(0)
            return self._logo_cache

        fontes = []

        if self.empresa is not None:
            fontes.append((
                "VistoGEST PRO",
                self.empresa,
                ("logo", "logotipo", "logo_empresa", "foto", "imagem_logo"),
            ))

        # Compatibilidade: o modelo ConfiguracaoFiscal fornecido não tem
        # campo de logótipo, mas verificamos aliases caso o modelo evolua.
        if self.config_fiscal is not None:
            fontes.append((
                "ConfiguracaoFiscal",
                self.config_fiscal,
                ("logo", "logotipo", "logo_empresa", "imagem_logo", "logo_principal"),
            ))

        personalizacao = self._obter_personalizacao_interface()

        if personalizacao is not None:
            fontes.append((
                "PersonalizacaoInterface",
                personalizacao,
                ("logo_principal",),
            ))

        for origem, obj, nomes_campos in fontes:
            for nome_campo in nomes_campos:
                try:
                    campo = getattr(obj, nome_campo, None)
                except Exception:
                    logger.exception(
                        "Erro ao consultar %s.%s.",
                        origem,
                        nome_campo,
                    )
                    continue

                if not campo:
                    continue

                try:
                    imagem = self._ler_logo_field(campo)
                except Exception:
                    logger.exception(
                        "Erro ao carregar o logótipo de %s.%s.",
                        origem,
                        nome_campo,
                    )
                    continue

                if imagem:
                    imagem.seek(0)
                    self._logo_cache = imagem

                    logger.info(
                        "Logótipo do PDF carregado de %s.%s; schema=%s.",
                        origem,
                        nome_campo,
                        getattr(connection, "schema_name", None),
                    )

                    return self._logo_cache

                logger.warning(
                    "O campo %s.%s contém uma referência a imagem, "
                    "mas não foi possível carregar o ficheiro.",
                    origem,
                    nome_campo,
                )

        logger.error(
            "Nenhum logótipo foi carregado para o PDF. "
            "schema=%s; Empresa resolvida=%s; ConfiguracaoFiscal=%s; "
            "PersonalizacaoInterface=%s.",
            getattr(connection, "schema_name", None),
            self.empresa is not None,
            self.config_fiscal is not None,
            personalizacao is not None,
        )

        return None


    # ------------------------------------------------------------------
    # Identificação e datas
    # ------------------------------------------------------------------
    def _obj_documento(self):
        return self.doc_fiscal or self.venda

    def _numero(self) -> str:
        obj = self.doc_fiscal or self.venda
        return str(
            self._campo(
                obj,
                "numero_documento", "numero_fiscal", "numero_recibo", "numero_nota", "numero",
                default="",
            ) or ""
        ).strip()

    def _data(self):
        obj = self.doc_fiscal or self.venda
        return self._campo(
            obj,
            "data_emissao", "data_venda", "data_fatura", "data_recibo", "data_criacao", "created_at",
            default=None,
        )

    def _data_hora_formatada(self) -> str:
        """Formata data e hora reais do documento, respeitando o fuso horário."""

        obj = self._obj_documento()
        valor = self._data()

        if isinstance(valor, datetime):
            data_hora = valor

        elif isinstance(valor, date):
            hora = self._campo(
                obj,
                "hora_emissao",
                "hora_criacao",
                default=None,
            )

            if isinstance(hora, time):
                # DocumentoFiscal.data_emissao é DateField;
                # hora_emissao é um TimeField separado.
                data_hora = datetime.combine(valor, hora)

            else:
                # Fallback para a data/hora original da venda ou fatura,
                # se o documento estiver associado a um desses objectos.
                origem = self.venda

                if origem is obj:
                    try:
                        origem = getattr(obj, "venda", None) or obj
                    except Exception:
                        origem = obj

                data_legada = self._campo(
                    origem,
                    "data_venda",
                    "data_fatura",
                    "data_recibo",
                    "data_criacao",
                    "created_at",
                    default=None,
                )

                if isinstance(data_legada, datetime):
                    data_hora = data_legada
                else:
                    return f"{valor:%d/%m/%Y} - hora não registada"

        else:
            return "Data de emissão não registada"

        try:
            if timezone.is_naive(data_hora):
                data_hora = timezone.make_aware(
                    data_hora,
                    timezone.get_default_timezone(),
                )

            data_hora = timezone.localtime(data_hora)

        except (ValueError, OverflowError):
            logger.exception(
                "Não foi possível normalizar a data/hora do documento %s",
                self._numero(),
            )

        return data_hora.strftime("%d/%m/%Y - %Hh%M")


    def _periodo(self) -> str:
        valor = self._data()
        try:
            return valor.strftime("%m/%Y") if valor else ""
        except Exception:
            return ""

    def _data_formatada(self, *nomes) -> str:
        valor = self._campo(self._obj_documento(), *nomes, default=None)
        return valor.strftime("%d/%m/%Y") if valor and hasattr(valor, "strftime") else ""

    def _hash(self) -> str:
        return str(
            self._campo(self.doc_fiscal, "hash_documento", "hash_integridade", default="")
            or self._campo(self.venda, "hash_documento", "hash_integridade", default="")
            or ""
        ).strip()

    @staticmethod
    def _hash4(hash_documento: str) -> str:
        """Devolve os 4 caracteres derivados do hash; nunca inventa '0000'."""
        h = str(hash_documento or "").strip()
        return f"{h[0]}{h[10]}{h[20]}{h[30]}".upper() if len(h) >= 31 else ""

    def _atcud(self) -> str:
        return str(self._campo(self.doc_fiscal, "atcud", default="") or "").strip()

    def _tipo_label(self) -> str:
        return self.TIPO_LABELS.get(self._tipo, "DOCUMENTO FISCAL")

    def _cliente_dados(self) -> dict:
        obj = self._obj_documento()
        cliente = getattr(obj, "cliente", None) if obj else None
        nome = self._campo(obj, "cliente_nome", default="") or self._campo(
            cliente, "nome_completo", "razao_social", "nome", default=""
        ) or "Consumidor Final"
        nif = self._campo(obj, "cliente_nif", default="") or self._campo(
            cliente, "nif", "numero_identificacao_fiscal", default=""
        )
        endereco = self._campo(obj, "cliente_endereco", default="") or self._campo(
            cliente, "endereco", "morada", "endereco_completo", default=""
        )
        email = self._campo(obj, "cliente_email", default="") or self._campo(cliente, "email", default="")
        telefone = self._campo(obj, "cliente_telefone", default="") or self._campo(
            cliente, "telefone", "telemovel", default=""
        )
        nif = str(nif or "").strip()
        consumidor_final = (not nif) or nif in {"999999999", "000000000", "999999990"}
        return {
            "nome": _safe_text(nome),
            "nif": "" if consumidor_final else _safe_text(nif),
            "endereco": _safe_text(endereco),
            "email": _safe_text(email),
            "telefone": _safe_text(telefone),
            "consumidor_final": consumidor_final,
        }

    # ------------------------------------------------------------------
    # Linhas: apresenta valores persistidos; não calcula IVA/IEC/IS
    # ------------------------------------------------------------------
    def _obter_taxa(self, linha, tipo=""):
        aliases = {
            "IEC": ("taxa_iec", "taxa_imposto_iec"),
            "IVA": ("taxa_iva", "taxa_imposto"),
            "IS": ("taxa_selo", "taxa_is", "taxa_imposto_selo"),
        }
        for nome in aliases.get(tipo, ()):
            taxa = getattr(linha, nome, None)
            if taxa is not None:
                return taxa
        return self._campo(linha, "taxa_iva", "taxa_imposto", "taxa", default=None)

    def _linha_base(self, linha, legado=False) -> dict:
        produto = getattr(linha, "produto", None)
        quantidade = _decimal(self._campo(linha, "quantidade", "qtd", default=1), Decimal("1"))
        preco = _decimal(self._campo(linha, "preco_unitario", "preco", "valor_unitario", default=0))
        desconto = _decimal(
            self._campo(linha, "valor_desconto_linha", "desconto_item", "valor_desconto", "desconto", default=0)
        )
        bruto_guardado = self._decimal_opcional(
            linha, "valor_bruto_linha", "valor_bruto", "subtotal_bruto", "valor_sem_desconto"
        )
        bruto = bruto_guardado if bruto_guardado is not None else quantidade * preco
        liquido_guardado = self._decimal_opcional(
            linha, "valor_liquido", "subtotal_sem_iva", "base_tributavel", "valor_sem_imposto"
        )
        liquido = liquido_guardado if liquido_guardado is not None else bruto - desconto

        taxa = self._obter_taxa(linha)
        taxa_tipo = str(
            self._campo(taxa, "tax_type", "tipo_imposto", "tipo", default="")
            or self._campo(linha, "tax_type", "tipo_imposto", default="")
            or ""
        ).strip().upper()
        taxa_codigo = str(
            self._campo(taxa, "tax_code", "codigo_imposto", "codigo", default="")
            or self._campo(linha, "tax_code", "codigo_imposto", default="")
            or ""
        ).strip().upper()
        taxa_pct = self._decimal_opcional(taxa, "tax_percentage", "percentagem", "taxa")
        isencao_codigo = str(
            self._campo(
                taxa, "exemption_reason", "codigo_isencao", "motivo_isencao_codigo", default=""
            )
            or self._campo(linha, "codigo_isencao", "motivo_isencao_codigo", default="")
            or ""
        ).strip()
        isencao_motivo = str(
            self._campo(
                taxa, "descricao_isencao", "motivo_isencao_texto", "exemption_description", default=""
            )
            or self._campo(linha, "motivo_isencao", "descricao_isencao", default="")
            or ""
        ).strip()

        iva = self._decimal_opcional(linha, "valor_iva_linha", "valor_iva", "iva_valor", "imposto_iva")
        iec = self._decimal_opcional(linha, "valor_iec_linha", "valor_iec", "iec_valor", "imposto_iec")
        selo = self._decimal_opcional(
            linha, "valor_selo_linha", "valor_imposto_selo", "valor_selo", "valor_is", "imposto_selo", "valor_is_linha"
        )
        imposto_generico = self._decimal_opcional(
            linha, "valor_imposto_linha", "valor_imposto", "valor_taxa", "imposto"
        )

        # Se existir apenas o campo genérico de imposto, associa-o pelo tipo fiscal.
        if imposto_generico is not None:
            if taxa_tipo == "IVA" and iva is None:
                iva = imposto_generico
            elif taxa_tipo == "IEC" and iec is None:
                iec = imposto_generico
            elif taxa_tipo in {"IS", "ISELO", "SELO"} and selo is None:
                selo = imposto_generico

        if taxa_tipo == "NS" and taxa_codigo in {"NS", "NA"}:
            # Categoria de não sujeição: não atribuir valor a IEC ou Selo.
            if iva is None:
                iva = ZERO

        # Alguns modelos guardam zero por omissão em todas as colunas de imposto.
        # Nesse caso, só mostrar zero como valor fiscal quando o tipo corresponde
        # ao imposto da linha; os restantes campos ficam vazios (—). Valores
        # positivos de impostos adicionais são sempre preservados.
        if iec == ZERO and taxa_tipo != "IEC":
            iec = None
        if selo == ZERO and taxa_tipo not in {"IS", "ISELO", "SELO"}:
            selo = None
        if iva == ZERO and taxa_tipo not in {"IVA", "NS", "NA"} and taxa_codigo not in {"NS", "NA"}:
            iva = None

        impostos_conhecidos = [v for v in (iva, iec, selo) if v is not None]
        total_guardado = self._decimal_opcional(
            linha, "valor_total_linha", "valor_total", "total_linha", "total"
        )
        total = total_guardado
        if total is None:
            taxa_positiva_sem_valor = bool(
                taxa_pct is not None and taxa_pct > 0
                and ((taxa_tipo == "IVA" and iva is None)
                     or (taxa_tipo == "IEC" and iec is None)
                     or (taxa_tipo in {"IS", "ISELO", "SELO"} and selo is None))
            )
            if taxa_positiva_sem_valor:
                logger.warning(
                    "Linha sem valor de imposto persistido; o PDF não recalculou imposto. linha=%s",
                    getattr(linha, "pk", None),
                )
            else:
                total = liquido + sum(impostos_conhecidos, ZERO)

        codigo_produto = self._campo(linha, "codigo_produto", "codigo", "referencia", default="")
        if not codigo_produto and produto is not None:
            codigo_produto = self._campo(produto, "codigo_interno", "codigo", "referencia", default="")
        if not codigo_produto and getattr(linha, "servico_id", None):
            codigo_produto = f"SRV-{linha.servico_id}"

        descricao = self._campo(
            linha, "descricao", "nome_produto", "nome_item", "nome_servico", default="Item sem descrição"
        )
        operacao = str(
            self._campo(linha, "operation_type", "tipo_operacao", default="") or ""
        ).strip().upper()
        tipo_linha = str(
            self._campo(linha, "tipo_item", "tipo_linha", "tipo", default="") or operacao or "—"
        ).strip().upper()
        referencia_origem = self._campo(
            linha, "documento_original_numero", "documento_origem_numero", "referencia_documento_original", default=""
        )
        if not referencia_origem:
            origem = self._campo(linha, "documento_original", "documento_origem", default=None)
            referencia_origem = self._campo(origem, "numero_documento", "numero", default="")

        return {
            "tipo": _safe_text(tipo_linha or "—"),
            "cod": _safe_text(codigo_produto or "—"),
            "desc": _safe_text(descricao),
            "unidade": _safe_text(self._campo(linha, "unidade", default="UN") or "UN"),
            "op_type": operacao,
            "qtd_raw": quantidade,
            "qtd": _fmt_quantidade(quantidade),
            "preco_raw": preco,
            "preco": _fmt_unit(preco),
            "bruto_raw": bruto,
            "desconto_raw": desconto,
            "desc_val": _fmt_numero(desconto, 2),
            "liquido_raw": liquido,
            "iva_raw": iva,
            "iec_raw": iec,
            "selo_raw": selo,
            "total_raw": total,
            "taxa_tipo": taxa_tipo,
            "taxa_codigo": taxa_codigo,
            "taxa_pct": taxa_pct,
            "isencao_codigo": isencao_codigo,
            "isencao_motivo": isencao_motivo,
            "referencia_origem": str(referencia_origem or ""),
        }

    def _linhas_doc(self) -> list[dict]:
        if self._linhas_cache is not None:
            return self._linhas_cache

        linhas_obj = []
        obj_fiscal = self.doc_fiscal
        if obj_fiscal is not None:
            relacao = getattr(obj_fiscal, "linhas", None)
            if relacao is not None:
                try:
                    qs = relacao.all()
                    try:
                        qs = qs.order_by("numero_linha")
                    except Exception:
                        qs = qs.order_by("pk")
                    linhas_obj = list(qs)
                except Exception:
                    logger.exception("Falha ao obter linhas do documento fiscal %s", self._numero())

        if not linhas_obj:
            obj = self.venda
            relacao = getattr(obj, "itens", None) if obj is not None else None
            if relacao is not None:
                try:
                    qs = relacao.all()
                    try:
                        qs = qs.order_by("ordem", "pk")
                    except Exception:
                        pass
                    linhas_obj = list(qs)
                except Exception:
                    logger.exception("Falha ao obter itens do documento legado %s", self._numero())

        legado = self.doc_fiscal is None
        self._linhas_cache = [self._linha_base(linha, legado=legado) for linha in linhas_obj]
        return self._linhas_cache

    # ------------------------------------------------------------------
    # Totais persistidos e agrupamento de impostos
    # ------------------------------------------------------------------
    @staticmethod
    def _soma_linhas(linhas, campo):
        valores = [linha.get(campo) for linha in linhas]
        valores = [v for v in valores if v is not None]
        return sum(valores, ZERO) if valores else ZERO

    def _totais_raw(self) -> dict:
        if self._totais_cache is not None:
            return self._totais_cache

        obj = self._obj_documento()
        linhas = self._linhas_doc()
        base_guardada = self._decimal_opcional(
            obj, "valor_base", "subtotal", "valor_sem_imposto", "total_sem_imposto", "net_total"
        )
        base = base_guardada if base_guardada is not None else self._soma_linhas(linhas, "bruto_raw")

        desconto_guardado = self._decimal_opcional(
            obj, "valor_desconto", "desconto_valor", "total_descontos", "valor_total_descontos"
        )
        desconto = desconto_guardado if desconto_guardado is not None else self._soma_linhas(linhas, "desconto_raw")

        iva_guardado = self._decimal_opcional(obj, "valor_iva", "iva_valor", "total_iva", "valor_total_iva")
        iec_guardado = self._decimal_opcional(obj, "valor_iec", "iec_valor", "total_iec", "valor_total_iec")
        selo_guardado = self._decimal_opcional(
            obj, "valor_selo", "valor_imposto_selo", "valor_is", "total_selo", "valor_total_is"
        )
        iva = iva_guardado if iva_guardado is not None else self._soma_linhas(linhas, "iva_raw")
        iec = iec_guardado if iec_guardado is not None else self._soma_linhas(linhas, "iec_raw")
        selo = selo_guardado if selo_guardado is not None else self._soma_linhas(linhas, "selo_raw")
        retencao = self._decimal_opcional(
            obj, "valor_retencao", "valor_retido", "total_retencao", "valor_retencao_fonte"
        ) or ZERO

        total_guardado = self._decimal_opcional(
            obj, "valor_total", "total", "valor_total_documento", "valor_a_pagar", "total_a_pagar"
        )
        total_linhas = [linha.get("total_raw") for linha in linhas]
        if total_guardado is not None:
            total = total_guardado
            formula = base + iva + iec + selo - desconto
            if abs(total - formula) > CENTAVO:
                logger.warning(
                    "Totais do PDF diferem dos valores agregados: documento=%s; guardado=%s; agregado=%s",
                    self._numero(), total, formula,
                )
        elif total_linhas and all(v is not None for v in total_linhas):
            total = sum(total_linhas, ZERO)
        else:
            # Fallback apenas com os valores fiscais disponíveis; nenhuma taxa é recalculada.
            total = base + iva + iec + selo - desconto
            logger.warning(
                "Documento sem total persistido; foi usada a soma dos montantes disponíveis. documento=%s",
                self._numero(),
            )

        moeda = str(self._campo(obj, "moeda", "codigo_moeda", default="AOA") or "AOA").upper()
        cambio = self._decimal_opcional(obj, "taxa_cambio", "taxa_de_cambio", "cambio")
        cambio = cambio if cambio is not None else Decimal("1")
        total_aoa = self._decimal_opcional(
            obj, "valor_total_aoa", "total_aoa", "valor_total_kz", "total_kz", "valor_total_kwanzas"
        )
        self._totais_cache = {
            "base": base,
            "desconto": desconto,
            "base_tributavel": base - desconto,
            "iva": iva,
            "iec": iec,
            "selo": selo,
            "impostos": iva + iec + selo,
            "retencao": retencao,
            "total": total,
            "moeda": moeda,
            "taxa_cambio": cambio,
            "total_aoa": total_aoa,
        }
        return self._totais_cache

    def _resumo_impostos(self) -> list[dict]:
        grupos = {}
        for linha in self._linhas_doc():
            tipo_taxa = linha.get("taxa_tipo", "")
            codigo = linha.get("taxa_codigo", "")
            taxa_pct = linha.get("taxa_pct")
            codigo_isencao = linha.get("isencao_codigo", "")
            motivo = linha.get("isencao_motivo", "")

            tipos = []
            if linha.get("iec_raw") is not None or tipo_taxa == "IEC":
                tipos.append(("IEC", linha.get("iec_raw")))
            if linha.get("selo_raw") is not None or tipo_taxa in {"IS", "ISELO", "SELO"}:
                tipos.append(("Selo", linha.get("selo_raw")))
            if (
                linha.get("iva_raw") is not None
                or tipo_taxa in {"IVA", "NS", "NA"}
                or codigo in {"NOR", "INT", "RED", "ISE", "OUT", "NS", "NA"}
                or codigo_isencao
            ):
                tipos.append(("IVA", linha.get("iva_raw")))

            for rotulo, valor in tipos:
                taxa_label = (
                    f"{_fmt_numero(taxa_pct, 2)}%" if taxa_pct is not None and rotulo == "IVA"
                    else codigo or tipo_taxa or "Não indicada"
                )
                detalhes = " — ".join(v for v in (codigo_isencao, motivo) if v)
                chave = (rotulo, taxa_label, detalhes)
                if chave not in grupos:
                    grupos[chave] = {"base": ZERO, "valor": ZERO, "valor_conhecido": True}
                grupos[chave]["base"] += linha.get("liquido_raw") or ZERO
                if valor is None:
                    grupos[chave]["valor_conhecido"] = False
                else:
                    grupos[chave]["valor"] += valor

        resultado = []
        for (tipo, taxa, detalhes), montantes in sorted(grupos.items()):
            resultado.append({
                "tipo": tipo,
                "taxa": taxa,
                "detalhes": detalhes,
                "base": montantes["base"],
                "valor": montantes["valor"] if montantes["valor_conhecido"] else None,
            })
        return resultado

    def _motivos_isencao(self) -> list[str]:
        motivos = []
        vistos = set()
        for linha in self._linhas_doc():
            codigo = str(linha.get("isencao_codigo") or "").strip()
            motivo = str(linha.get("isencao_motivo") or "").strip()
            if not codigo and not motivo:
                continue
            texto = " — ".join(v for v in (codigo, motivo) if v)
            if texto not in vistos:
                vistos.add(texto)
                motivos.append(texto)
        return motivos

    # ------------------------------------------------------------------
    # Estilos neutros e cabeçalho
    # ------------------------------------------------------------------
    def _estilos(self, compacto=False) -> dict:
        base = getSampleStyleSheet()["Normal"]
        mult = 0.92 if compacto else 1.0
        return {
            "normal": ParagraphStyle("pdfdoc_normal", parent=base, fontName="Helvetica", fontSize=7.2 * mult, leading=9 * mult, textColor=self.DOC_TEXTO, spaceAfter=0, splitLongWords=1),
            "small": ParagraphStyle("pdfdoc_small", parent=base, fontName="Helvetica", fontSize=6.1 * mult, leading=7.5 * mult, textColor=self.DOC_TEXTO_SEC, spaceAfter=0, splitLongWords=1),
            "tiny": ParagraphStyle("pdfdoc_tiny", parent=base, fontName="Helvetica", fontSize=5.3 * mult, leading=6.4 * mult, textColor=self.DOC_TEXTO_SEC, spaceAfter=0, splitLongWords=1),
            "right": ParagraphStyle("pdfdoc_right", parent=base, fontName="Helvetica", fontSize=6.7 * mult, leading=8 * mult, alignment=TA_RIGHT, textColor=self.DOC_TEXTO, spaceAfter=0, splitLongWords=1),
            "issuer": ParagraphStyle("pdfdoc_issuer", parent=base, fontName="Helvetica-Bold", fontSize=10 * mult, leading=12 * mult, textColor=self.DOC_TEXTO, spaceAfter=2),
            "issuer_sub": ParagraphStyle("pdfdoc_issuer_sub", parent=base, fontName="Helvetica", fontSize=6.1 * mult, leading=7.5 * mult, textColor=self.DOC_TEXTO_SEC, spaceAfter=1),
            "title": ParagraphStyle("pdfdoc_title", parent=base, fontName="Helvetica-Bold", fontSize=17 * mult, leading=19 * mult, alignment=TA_CENTER, textColor=self.DOC_TEXTO, spaceAfter=2),
            "number": ParagraphStyle("pdfdoc_number", parent=base, fontName="Helvetica-Bold", fontSize=8 * mult, leading=10 * mult, alignment=TA_CENTER, textColor=self.DOC_TEXTO, spaceAfter=1),
            "section": ParagraphStyle("pdfdoc_section", parent=base, fontName="Helvetica-Bold", fontSize=7.3 * mult, leading=8.8 * mult, textColor=self.DOC_TEXTO, spaceAfter=2),
            "table_header": ParagraphStyle("pdfdoc_table_header", parent=base, fontName="Helvetica-Bold", fontSize=5.4 * mult, leading=6.2 * mult, textColor=self.DOC_TEXTO, alignment=TA_CENTER, spaceAfter=0, splitLongWords=1),
            "line": ParagraphStyle("pdfdoc_line", parent=base, fontName="Helvetica", fontSize=5.7 * mult, leading=6.8 * mult, textColor=self.DOC_TEXTO, spaceAfter=0, splitLongWords=1),
            "line_right": ParagraphStyle("pdfdoc_line_right", parent=base, fontName="Helvetica", fontSize=5.5 * mult, leading=6.5 * mult, alignment=TA_RIGHT, textColor=self.DOC_TEXTO, spaceAfter=0, splitLongWords=1),
            "total_label": ParagraphStyle("pdfdoc_total_label", parent=base, fontName="Helvetica", fontSize=7 * mult, leading=8.2 * mult, textColor=self.DOC_TEXTO, spaceAfter=0),
            "total_value": ParagraphStyle("pdfdoc_total_value", parent=base, fontName="Helvetica", fontSize=7 * mult, leading=8.2 * mult, alignment=TA_RIGHT, textColor=self.DOC_TEXTO, spaceAfter=0),
            "grand_label": ParagraphStyle("pdfdoc_grand_label", parent=base, fontName="Helvetica-Bold", fontSize=8.3 * mult, leading=9.8 * mult, textColor=self.DOC_TEXTO, spaceAfter=0),
            "grand_value": ParagraphStyle("pdfdoc_grand_value", parent=base, fontName="Helvetica-Bold", fontSize=8.3 * mult, leading=9.8 * mult, alignment=TA_RIGHT, textColor=self.DOC_TEXTO, spaceAfter=0),
            "logo_fallback": ParagraphStyle("pdfdoc_logo_fallback", parent=base, fontName="Helvetica-Bold", fontSize=7 * mult, leading=8 * mult, alignment=TA_CENTER, textColor=self.DOC_TEXTO, spaceAfter=0),
        }

    def _logo_flowable(self, largura: float, altura: float, styles: dict):
        logo_io = self._logo_empresa()
        if not logo_io:
            return Paragraph("EMPRESA", styles["logo_fallback"])
        try:
            logo_io.seek(0)
            with Image.open(logo_io) as img:
                img_w, img_h = img.size
            if not img_w or not img_h:
                return Paragraph("EMPRESA", styles["logo_fallback"])
            escala = min(largura / img_w, altura / img_h)
            logo_io.seek(0)
            return RLImage(logo_io, width=img_w * escala, height=img_h * escala, hAlign="CENTER")
        except Exception as exc:
            logger.warning("Logótipo não suportado no PDF: %s", exc)
            return Paragraph("EMPRESA", styles["logo_fallback"])

    def _caixa_documento(self, styles: dict, largura: float, compact=False):
        titulo = self._tipo_label()
        numero = self._numero() or "NÃO EMITIDO"
        linhas = [
            [Paragraph(_p_text(titulo), styles["title"])],
            [Paragraph(_p_text(numero), styles["number"])],
        ]
        via = self._campo(self._obj_documento(), "via", "tipo_via", "via_documento", default="")
        if via:
            linhas.append([Paragraph(_p_text(str(via)), styles["small"])])
        if self._proforma:
            linhas.append([Paragraph("DOCUMENTO NÃO FISCAL", styles["section"])])
        tabela = Table(linhas, colWidths=[largura])
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self.DOC_CINZA_TOPO),
            ("BOX", (0, 0), (-1, -1), 0.6, self.DOC_BORDA),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
            ("TOPPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return tabela

    def _cabecalho(self, styles: dict, compact=False):
        emissor = self._dados_emissor()
        if compact:
            logo = self._logo_flowable(20 * mm, 16 * mm, styles)
            linhas_info = [Paragraph(_p_text(emissor["nome"]), styles["issuer"])]
            linhas_info.append(Paragraph(_p_text(f"NIF: {emissor['nif'] or 'Não configurado'}"), styles["normal"]))
            if emissor["endereco"]:
                linhas_info.append(Paragraph(_p_text(emissor["endereco"]), styles["small"]))
            contactos = " | ".join(v for v in (emissor["telefone"], emissor["email"],emissor["site"],) if v)
            if contactos:
                linhas_info.append(Paragraph(_p_text(contactos), styles["small"]))
            info = Table([[x] for x in linhas_info], colWidths=[72 * mm])
            info.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            titulo = self._caixa_documento(styles, 50 * mm, compact=True)
            topo = Table([[logo, titulo]], colWidths=[21 * mm, 51 * mm])
            topo.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, self.DOC_BORDA),
            ]))
            return [topo, Spacer(1, 2 * mm), info, Spacer(1, 2 * mm)]

        logo = self._logo_flowable(25 * mm, 22 * mm, styles)
        info_linhas = [Paragraph(_p_text(emissor["nome"]), styles["issuer"])]
        if emissor["razao_social"] and emissor["razao_social"] != emissor["nome"]:
            info_linhas.append(Paragraph(_p_text(f"Razão social: {emissor['razao_social']}"), styles["issuer_sub"]))
        info_linhas.append(Paragraph(_p_text(f"NIF: {emissor['nif'] or 'Não configurado'}"), styles["normal"]))
        if emissor["endereco"]:
            info_linhas.append(Paragraph(_p_text(emissor["endereco"]), styles["small"]))
        contactos = " | ".join(v for v in (emissor["telefone"], emissor["email"], emissor["site"]) if v)
        if contactos:
            info_linhas.append(Paragraph(_p_text(contactos), styles["small"]))
        if emissor["regime"]:
            info_linhas.append(Paragraph(_p_text(emissor["regime"]), styles["small"]))

        info = Table([[x] for x in info_linhas], colWidths=[91 * mm])
        info.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        caixa = self._caixa_documento(styles, 57 * mm)
        topo = Table([[logo, info, caixa]], colWidths=[27 * mm, 96 * mm, 57 * mm])
        topo.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -1), 1, self.DOC_BORDA),
        ]))
        return [topo, Spacer(1, 3 * mm)]

    # ------------------------------------------------------------------
    # Intervenientes e metadados específicos
    # ------------------------------------------------------------------
    def _bloco_cliente_metadados(self, styles: dict, compact=False):
        cliente = self._cliente_dados()
        emissor = self._dados_emissor()
        linhas_cliente = [
            Paragraph("ADQUIRENTE / CLIENTE", styles["section"]),
            Paragraph(f"<b>{_p_text(cliente['nome'])}</b>", styles["normal"]),
            Paragraph(_p_text(f"NIF: {cliente['nif']}" if cliente["nif"] else "NIF não informado"), styles["normal"]),
        ]
        if cliente["endereco"]:
            linhas_cliente.append(Paragraph(_p_text(cliente["endereco"]), styles["small"]))
        contactos = " | ".join(v for v in (cliente["telefone"], cliente["email"]) if v)
        if contactos:
            linhas_cliente.append(Paragraph(_p_text(contactos), styles["small"]))

        obj = self._obj_documento()
        linhas_doc = [
            Paragraph("DADOS DO DOCUMENTO", styles["section"]),
            Paragraph(_p_text(f"Emissão: {self._data_hora_formatada()}"), styles["normal"]),
        ]
        periodo = self._periodo()
        if periodo:
            linhas_doc.append(Paragraph(_p_text(f"Período contabilístico: {periodo}"), styles["small"]))
        for campo, rotulo in (
            (("data_vencimento", "vencimento"), "Data de vencimento"),
            (("data_operacao",), "Data da operação"),
            (("condicoes_pagamento", "condicao_pagamento"), "Condições de pagamento"),
            (("referencia_externa", "referencia"), "Referência"),
        ):
            valor = self._campo(obj, *campo, default="")
            if valor:
                if hasattr(valor, "strftime"):
                    valor = valor.strftime("%d/%m/%Y")
                linhas_doc.append(Paragraph(_p_text(f"{rotulo}: {valor}"), styles["small"]))
        if self._atcud() and not self._proforma and not self._rascunho:
            linhas_doc.append(Paragraph(_p_text(f"ATCUD: {self._atcud()}"), styles["small"]))

        # Informações de transporte quando aplicáveis ao tipo documental.
        if self._tipo == "DT":
            for aliases, rotulo in (
                (("local_carga", "local_carregamento"), "Local de carga"),
                (("local_descarga", "local_descarregamento"), "Local de descarga"),
                (("data_carga", "data_carregamento"), "Data de carga"),
                (("data_descarga", "data_descarregamento"), "Data de descarga"),
                (("matricula_viatura", "matricula", "matrícula"), "Matrícula"),
            ):
                valor = self._campo(obj, *aliases, default="")
                if valor:
                    if hasattr(valor, "strftime"):
                        valor = valor.strftime("%d/%m/%Y %H:%M")
                    linhas_doc.append(Paragraph(_p_text(f"{rotulo}: {valor}"), styles["small"]))

        largura_interna = 72 * mm if compact else 85 * mm
        cliente_tbl = Table([[x] for x in linhas_cliente], colWidths=[largura_interna])
        doc_tbl = Table([[x] for x in linhas_doc], colWidths=[largura_interna])
        for tabela in (cliente_tbl, doc_tbl):
            tabela.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.45, self.DOC_BORDA),
                ("BACKGROUND", (0, 0), (-1, 0), self.DOC_CINZA_CABEC),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3 if not compact else 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 if not compact else 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
        if compact:
            return [cliente_tbl, Spacer(1, 2 * mm), doc_tbl, Spacer(1, 3 * mm)]
        ambos = Table([[cliente_tbl, doc_tbl]], colWidths=[90 * mm, 90 * mm])
        ambos.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return [ambos, Spacer(1, 3 * mm)]

    def _bloco_pagamento(self, styles: dict, compact=False):
        if self._tipo != "FR":
            return []
        obj = self._obj_documento()
        meio = self._campo(obj, "meio_pagamento", "forma_pagamento", "metodo_pagamento", default="")
        recebido = self._decimal_opcional(obj, "valor_recebido", "valor_pago", "montante_pago")
        total_pago = self._decimal_opcional(obj, "total_pago", "valor_total_pago", "valor_liquidado")
        troco = self._decimal_opcional(obj, "valor_troco", "troco")
        referencia = self._campo(obj, "referencia_pagamento", "referencia_transacao", default="")
        totais_doc = self._totais_raw()
        moeda = totais_doc["moeda"]
        # FR representa factura com recibo: quando não existe campo próprio de
        # liquidação, o montante liquidado é o total persistido do documento.
        if total_pago is None:
            total_pago = totais_doc["total"]
        dados = [[Paragraph("PAGAMENTO", styles["section"]), Paragraph(_p_text(meio or "—"), styles["normal"])]]
        dados.append([Paragraph("Total pago", styles["small"]), Paragraph(_p_text(_fmt_moeda(total_pago, moeda)), styles["normal"])])
        if recebido is not None:
            dados.append([Paragraph("Valor recebido", styles["small"]), Paragraph(_p_text(_fmt_moeda(recebido, moeda)), styles["normal"])])
        if troco is not None:
            dados.append([Paragraph("Troco", styles["small"]), Paragraph(_p_text(_fmt_moeda(troco, moeda)), styles["normal"])])
        if referencia:
            dados.append([Paragraph("Referência", styles["small"]), Paragraph(_p_text(referencia), styles["normal"])])
        tabela = Table(dados, colWidths=[27 * mm, 45 * mm] if compact else [38 * mm, 135 * mm])
        tabela.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.45, self.DOC_BORDA),
            ("BACKGROUND", (0, 0), (-1, 0), self.DOC_CINZA_CABEC),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return [tabela, Spacer(1, 2 * mm)]

    # ------------------------------------------------------------------
    # Tabela fiscal com onze colunas fixas
    # ------------------------------------------------------------------
    def _tabela_linhas(self, styles: dict, compact=False):
        linhas = self._linhas_doc()
        moeda = self._totais_raw()["moeda"]

        if compact:
            dados = [[
                Paragraph("DESCRIÇÃO / TIPO", styles["table_header"]),
                Paragraph("TOTAL", styles["table_header"]),
            ]]
            for linha in linhas:
                descricao = f"<b>{_p_text(linha['desc'])}</b><br/>"
                descricao += _p_text(
                    f"{linha['tipo']} · {linha['cod']} · {linha['qtd']} {linha['unidade']} × {linha['preco']}"
                )
                impostos = []
                for nome, valor in (("IEC", linha["iec_raw"]), ("IVA", linha["iva_raw"]), ("Selo", linha["selo_raw"])):
                    if valor is not None:
                        impostos.append(f"{nome}: {_fmt_numero(valor, 2)}")
                if impostos:
                    descricao += "<br/><font size='5'>" + _p_text(" | ".join(impostos)) + "</font>"
                if linha["isencao_codigo"] or linha["isencao_motivo"]:
                    descricao += "<br/><font size='5'>Isenção: " + _p_text(
                        " — ".join(v for v in (linha["isencao_codigo"], linha["isencao_motivo"]) if v)
                    ) + "</font>"
                total_txt = _fmt_moeda(linha["total_raw"], moeda) if linha["total_raw"] is not None else "—"
                dados.append([Paragraph(descricao, styles["line"]), Paragraph(_p_text(total_txt), styles["line_right"])])
            if not linhas:
                dados.append([Paragraph("Não existem linhas neste documento.", styles["line"]), Paragraph("—", styles["line_right"])])
            tabela = Table(dados, colWidths=[49 * mm, 23 * mm], repeatRows=1, hAlign="LEFT")
        else:
            titulos = ["Tipo", "Código", "Descrição", "Qt", "Preço Unit.", "Desconto", "Valor", "IEC", "IVA", "Selo", "Total"]
            dados = [[Paragraph(_p_text(t), styles["table_header"]) for t in titulos]]
            for linha in linhas:
                descricao = f"<b>{_p_text(linha['desc'])}</b>"
                metadados = []
                if linha["op_type"]:
                    metadados.append(f"Operação: {linha['op_type']}")
                if linha["taxa_codigo"]:
                    metadados.append(f"Código fiscal: {linha['taxa_codigo']}")
                if linha["taxa_pct"] is not None:
                    metadados.append(f"Taxa: {_fmt_numero(linha['taxa_pct'], 2)}%")
                if linha["isencao_codigo"] or linha["isencao_motivo"]:
                    metadados.append(
                        "Isenção: " + " — ".join(
                            v for v in (linha["isencao_codigo"], linha["isencao_motivo"]) if v
                        )
                    )
                if linha["referencia_origem"]:
                    metadados.append(f"Documento de origem: {linha['referencia_origem']}")
                if metadados:
                    descricao += "<br/><font size='5' color='#52525B'>" + _p_text(" · ".join(metadados)) + "</font>"

                def valor_celula(valor):
                    return "—" if valor is None else _fmt_numero(valor, 2)

                total_txt = _fmt_numero(linha["total_raw"], 2) if linha["total_raw"] is not None else "—"
                dados.append([
                    Paragraph(_p_text(linha["tipo"]), styles["line"]),
                    Paragraph(_p_text(linha["cod"]), styles["line"]),
                    Paragraph(descricao, styles["line"]),
                    Paragraph(_p_text(linha["qtd"]), styles["line_right"]),
                    Paragraph(_p_text(linha["preco"]), styles["line_right"]),
                    Paragraph(_p_text(valor_celula(linha["desconto_raw"])), styles["line_right"]),
                    Paragraph(_p_text(valor_celula(linha["bruto_raw"])), styles["line_right"]),
                    Paragraph(_p_text(valor_celula(linha["iec_raw"])), styles["line_right"]),
                    Paragraph(_p_text(valor_celula(linha["iva_raw"])), styles["line_right"]),
                    Paragraph(_p_text(valor_celula(linha["selo_raw"])), styles["line_right"]),
                    Paragraph(_p_text(total_txt), styles["line_right"]),
                ])
            if not linhas:
                dados.append([Paragraph("—", styles["line"]), Paragraph("—", styles["line"]),
                              Paragraph("Não existem linhas neste documento.", styles["line"]),
                              *[Paragraph("—", styles["line_right"]) for _ in range(8)]])

            # Soma = 180 mm, correspondente à área útil A4 (210 - 15 - 15).
            larguras = [9, 13, 48, 10, 17, 14, 17, 11, 11, 11, 19]
            tabela = Table(
                dados,
                colWidths=[v * mm for v in larguras],
                repeatRows=1,
                hAlign="LEFT",
                splitByRow=1,
            )

        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.DOC_CINZA_CABEC),
            ("TEXTCOLOR", (0, 0), (-1, 0), self.DOC_TEXTO),
            ("GRID", (0, 0), (-1, -1), 0.3, self.DOC_BORDA),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self.DOC_CINZA_LINHA]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, 0), 4),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT") if not compact else ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ]))
        return [Paragraph("ARTIGOS / SERVIÇOS", styles["section"]), tabela, Spacer(1, 3 * mm)]

    # ------------------------------------------------------------------
    # Impostos agrupados, retenções informativas e resumo final
    # ------------------------------------------------------------------
    def _tabela_impostos(self, styles: dict, compact=False):
        grupos = self._resumo_impostos()
        if compact:
            dados = [[Paragraph("IMPOSTO", styles["table_header"]), Paragraph("VALOR", styles["table_header"])]]
            for grupo in grupos:
                texto = grupo["tipo"] + " · " + grupo["taxa"]
                if grupo["detalhes"]:
                    texto += " · " + grupo["detalhes"]
                valor = _fmt_numero(grupo["valor"], 2) if grupo["valor"] is not None else "—"
                dados.append([Paragraph(_p_text(texto), styles["line"]), Paragraph(_p_text(valor), styles["line_right"])])
            if not grupos:
                dados.append([Paragraph("Sem discriminação registada", styles["line"]), Paragraph("—", styles["line_right"])])
            widths = [49 * mm, 23 * mm]
        else:
            dados = [[
                Paragraph("Imposto", styles["table_header"]),
                Paragraph("Taxa / código / isenção", styles["table_header"]),
                Paragraph("Base", styles["table_header"]),
                Paragraph("Valor", styles["table_header"]),
            ]]
            for grupo in grupos:
                dados.append([
                    Paragraph(_p_text(grupo["tipo"]), styles["line"]),
                    Paragraph(_p_text(" · ".join(v for v in (grupo["taxa"], grupo["detalhes"]) if v)), styles["line"]),
                    Paragraph(_p_text(_fmt_numero(grupo["base"], 2)), styles["line_right"]),
                    Paragraph(_p_text(_fmt_numero(grupo["valor"], 2) if grupo["valor"] is not None else "—"), styles["line_right"]),
                ])
            if not grupos:
                dados.append([Paragraph("—", styles["line"]), Paragraph("Sem discriminação registada", styles["line"]), Paragraph("—", styles["line_right"]), Paragraph("—", styles["line_right"])])
            widths = [15 * mm, 36 * mm, 21 * mm, 17 * mm]

        tabela = Table(dados, colWidths=widths, repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.DOC_CINZA_CABEC),
            ("GRID", (0, 0), (-1, -1), 0.3, self.DOC_BORDA),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self.DOC_CINZA_LINHA]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return tabela

    def _tabela_retencoes(self, styles: dict, compact=False):
        retencao = self._totais_raw()["retencao"]
        if retencao <= ZERO:
            return None
        moeda = self._totais_raw()["moeda"]
        dados = [
            [Paragraph("RETENÇÕES NA FONTE", styles["section"])],
            [Paragraph("Valores informativos; não deduzidos do total do documento.", styles["small"])],
            [Paragraph(_p_text(f"Total de retenções: {_fmt_moeda(retencao, moeda)}"), styles["normal"])],
        ]
        tabela = Table(dados, colWidths=[49 * mm if compact else 89 * mm])
        tabela.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.4, self.DOC_BORDA),
            ("BACKGROUND", (0, 0), (-1, 0), self.DOC_CINZA_CABEC),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return tabela

    def _tabela_totais(self, styles: dict, compact=False):
        totais = self._totais_raw()
        moeda = totais["moeda"]
        dados = [
            [Paragraph("Totais sem impostos", styles["total_label"]), Paragraph(_p_text(_fmt_moeda(totais["base"], moeda)), styles["total_value"])],
            [Paragraph("Valor de impostos", styles["total_label"]), Paragraph(_p_text(_fmt_moeda(totais["impostos"], moeda)), styles["total_value"])],
            [Paragraph("Valor de descontos", styles["total_label"]), Paragraph(_p_text(_fmt_moeda(totais["desconto"], moeda)), styles["total_value"])],
            [Paragraph("VALOR TOTAL A PAGAR", styles["grand_label"]), Paragraph(_p_text(_fmt_moeda(totais["total"], moeda)), styles["grand_value"])],
        ]
        largura_label, largura_valor = ((48 * mm, 24 * mm) if compact else (53 * mm, 36 * mm))
        tabela = Table(dados, colWidths=[largura_label, largura_valor], hAlign="RIGHT")
        tabela.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -2), 0.3, self.DOC_BORDA),
            ("BACKGROUND", (0, 0), (-1, -2), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), self.DOC_CINZA_TOPO),
            ("BOX", (0, -1), (-1, -1), 0.8, self.DOC_TEXTO),
            ("LINEABOVE", (0, -1), (-1, -1), 1.2, self.DOC_TEXTO),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return tabela

    def _bloco_totais_fiscais(self, styles: dict, compact=False):
        imposto = self._tabela_impostos(styles, compact=compact)
        retencao = self._tabela_retencoes(styles, compact=compact)
        tabela_direita = self._tabela_totais(styles, compact=compact)

        if compact:
            elementos_compactos = [Paragraph("TOTAIS POR IMPOSTO", styles["section"]), imposto]
            if retencao is not None:
                elementos_compactos.extend([Spacer(1, 2 * mm), retencao])
            elementos_compactos.extend([Spacer(1, 3 * mm), Paragraph("RESUMO DO DOCUMENTO", styles["section"]), tabela_direita])
            totais = self._totais_raw()
            if totais["moeda"] != "AOA":
                elementos_compactos.append(Paragraph(_p_text(f"Moeda: {totais['moeda']} · Câmbio: {_fmt_numero(totais['taxa_cambio'], 4)}"), styles["small"]))
                elementos_compactos.append(Paragraph(_p_text(_fmt_moeda(totais["total_aoa"], "AOA") if totais["total_aoa"] is not None else "Equivalente em Kz não registado"), styles["small"]))
            else:
                elementos_compactos.append(Paragraph("Valores em Kwanzas (Kz).", styles["small"]))
            elementos_compactos.append(Spacer(1, 3 * mm))
            return elementos_compactos

        esquerdo = [Paragraph("TOTAIS POR IMPOSTO", styles["section"]), imposto]
        if retencao is not None:
            esquerdo.extend([Spacer(1, 2 * mm), retencao])
        tabela_esquerda = Table([[item] for item in esquerdo], colWidths=[89 * mm])
        tabela_esquerda.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        conjunto = Table([[tabela_esquerda, tabela_direita]], colWidths=[90 * mm, 90 * mm])
        conjunto.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        totais = self._totais_raw()
        moeda = totais["moeda"]
        elementos = [conjunto]
        if moeda != "AOA":
            cambio_texto = _fmt_numero(totais["taxa_cambio"], 4)
            equivalente = (
                _fmt_moeda(totais["total_aoa"], "AOA")
                if totais["total_aoa"] is not None
                else "Equivalente em Kz não registado"
            )
            elementos.append(Spacer(1, 1 * mm))
            elementos.append(Paragraph(
                _p_text(f"Moeda original: {moeda} · Taxa de câmbio registada: {cambio_texto} · Valor em Kwanzas: {equivalente}"),
                styles["small"],
            ))
        else:
            elementos.append(Paragraph("Valores em Kwanzas (Kz).", styles["small"]))
        elementos.append(Spacer(1, 3 * mm))
        return elementos

    # ------------------------------------------------------------------
    # Observações, cancelamento e referências
    # ------------------------------------------------------------------
    def _comentarios(self) -> str:
        obj = self._obj_documento()
        return _safe_text(self._campo(obj, "comentarios", "observacoes", "observacao", default=""))

    def _bloco_observacoes(self, styles: dict, compact=False):
        obj = self._obj_documento()
        notas = []
        if self._proforma:
            notas.append("DOCUMENTO NÃO FISCAL — ESTE DOCUMENTO NÃO SERVE DE FACTURA.")
        elif self._rascunho:
            notas.append("RASCUNHO — ESTE DOCUMENTO NÃO SERVE DE FACTURA.")
        if self._anulado:
            codigo = self._campo(obj, "motivo_codigo", "codigo_motivo_anulacao", "motivo_cancelamento_codigo", default="")
            motivo = self._campo(obj, "motivo_texto", "motivo_cancelamento", "motivo_anulacao", "motivo", default="")
            sufixo = " — ".join(str(v) for v in (codigo, motivo) if v)
            notas.append("DOCUMENTO ANULADO" + (f": {sufixo}" if sufixo else ". Motivo não registado."))
        documento_original = self._campo(obj, "documento_original", "documento_origem", default=None)
        if self._tipo in {"NC", "ND", "RE"}:
            numero_origem = self._campo(
                obj, "numero_documento_original", "documento_origem_numero", default=""
            ) or self._campo(documento_original, "numero_documento", "numero", default="")
            motivo = self._campo(obj, "motivo_rectificacao", "motivo", "motivo_texto", default="")
            if numero_origem:
                notas.append(f"Documento de origem: {numero_origem}")
            elif self._tipo == "NC":
                notas.append("Referência ao documento original não disponível no PDF.")
            if motivo:
                notas.append(f"Motivo: {motivo}")
        if self._tipo == "AF":
            notas.append("Autofacturação: documento emitido pelo adquirente em nome do fornecedor.")
        comentarios = self._comentarios()
        itens = []
        if notas:
            texto = "<br/>".join(_p_text(nota) for nota in notas)
            tabela_notas = Table([[Paragraph(texto, styles["normal"])]], colWidths=[72 * mm if compact else 180 * mm])
            tabela_notas.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.45, self.DOC_BORDA),
                ("BACKGROUND", (0, 0), (-1, -1), self.DOC_CINZA_LINHA),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            itens.extend([tabela_notas, Spacer(1, 2 * mm)])
        if comentarios:
            tabela_obs = Table([
                [Paragraph("OBSERVAÇÕES", styles["section"])],
                [Paragraph(_p_text(comentarios), styles["normal"])],
            ], colWidths=[72 * mm if compact else 180 * mm])
            tabela_obs.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.45, self.DOC_BORDA),
                ("BACKGROUND", (0, 0), (-1, 0), self.DOC_CINZA_CABEC),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            itens.extend([tabela_obs, Spacer(1, 2 * mm)])
        return itens

    # ------------------------------------------------------------------
    # QR e rodapé legal: nenhum QR em pró-forma/rascunho
    # ------------------------------------------------------------------
    def _url_qr_documento(self) -> str:
        """Prepara o URL de consulta do QR para documentos emitidos."""

        if self._proforma or self._rascunho:
            logger.debug(
                "QR omitido para documento não emitido: %s",
                self._numero(),
            )
            return ""

        emissor = self._dados_emissor()
        nif = str(emissor.get("nif") or "").strip()
        numero = self._numero()

        if not nif or not numero:
            logger.warning(
                "QR não gerado: falta NIF do emitente ou número do documento. "
                "NIF presente=%s; número presente=%s; documento=%s",
                bool(nif),
                bool(numero),
                numero or "(sem número)",
            )
            return ""

        base = str(
            getattr(settings, "AGT_QR_CODE_BASE_URL", "") or ""
        ).strip()

        if not base:
            logger.error(
                "QR não gerado para %s: AGT_QR_CODE_BASE_URL não está "
                "configurado nas definições Django.",
                numero,
            )
            return ""

        try:
            partes = urlsplit(base)

            if partes.scheme.lower() not in {"https", "http"} or not partes.netloc:
                logger.error(
                    "QR não gerado para %s: URL base inválido: %s",
                    numero,
                    base,
                )
                return ""

            url = _url_qr(nif, numero)

            if not url:
                logger.warning(
                    "O construtor do URL QR devolveu um valor vazio: %s",
                    numero,
                )
                return ""

            return url

        except Exception:
            logger.exception(
                "Não foi possível preparar o URL do QR do documento %s",
                numero,
            )
            return ""
        

    def _bloco_qr(self, styles: dict, compact=False):
        """Prepara QR e informação legal para o rodapé da última página.

        A renderização é feita pelo Canvas depois de conhecer o total de páginas,
        para o QR ficar ancorado no canto inferior direito e nunca ser repetido.
        """
        url = self._url_qr_documento()
        png = None
        if url:
            try:
                qr_io = _gerar_qr_com_logo_agt(url, box_size=4 if compact else 6,)
                png = qr_io.getvalue()
            except Exception:
                logger.exception("Não foi possível gerar o QR do documento %s", self._numero())

        software = str(getattr(settings, "AGT_SOFTWARE_NAME", "VistoGest Pro") or "VistoGest Pro").strip()
        versao = str(getattr(settings, "AGT_SOFTWARE_VERSION", "") or "").strip()
        certificacao = str(getattr(settings, "AGT_SOFTWARE_VALIDATION_NUMBER", "") or "").strip()
        hash4 = self._hash4(self._hash())
        linhas_texto = [f"Processado por software validado nº: {certificacao}" if certificacao else "Software validado nº: não configurado"]
        
        if hash4:
            linhas_texto.append(f"Hash (4 caracteres): {hash4}")
        elif not self._proforma and not self._rascunho:
            linhas_texto.append("Hash do documento não disponível")
        if self._atcud() and not self._proforma and not self._rascunho:
            linhas_texto.append(f"ATCUD: {self._atcud()}")
        motivos = self._motivos_isencao()
        if motivos:
            linhas_texto.append("Isenções: " + "; ".join(motivos))
        if self._proforma or self._rascunho:
            linhas_texto.append("Este documento não serve de factura.")
        if self._anulado:
            linhas_texto.append("DOCUMENTO ANULADO")

        self._qr_footer_data = {"png": png, "linhas": linhas_texto}
        return []

    def _desenhar_rodape_final(self, pdf_canvas):
        """Desenha QR e menções legais na última página, acima do rodapé paginado."""
        dados = self._qr_footer_data or {}
        linhas = dados.get("linhas") or []
        png = dados.get("png")
        if not linhas and not png:
            return

        pdf_canvas.saveState()
        largura, _ = pdf_canvas._pagesize
        margem_esquerda = getattr(pdf_canvas, "_pdf_left_margin", 15 * mm)
        margem_direita = getattr(pdf_canvas, "_pdf_right_margin", 15 * mm)
        lado_qr = 18 * mm if self.tamanho == "80mm" else 24 * mm
        x_qr = largura - margem_direita - lado_qr
        y_qr = 16 * mm

        if png:
            try:
                imagem = ImageReader(io.BytesIO(png))
                pdf_canvas.drawImage(
                    imagem, x_qr, y_qr, width=lado_qr, height=lado_qr,
                    preserveAspectRatio=True, anchor="c", mask="auto",
                )
            except Exception:
                logger.exception("Não foi possível desenhar o QR no rodapé do documento %s", self._numero())

        largura_texto = max(20 * mm, x_qr - margem_esquerda - 3 * mm) if png else largura - margem_esquerda - margem_direita
        if linhas:
            estilo = ParagraphStyle(
                "pdfdoc_footer_legal",
                parent=getSampleStyleSheet()["Normal"],
                fontName="Helvetica",
                fontSize=5.2 if self.tamanho != "80mm" else 4.3,
                leading=6.2 if self.tamanho != "80mm" else 5.1,
                textColor=self.DOC_TEXTO_SEC,
                spaceAfter=0,
                splitLongWords=1,
            )
            texto = Paragraph("<br/>".join(_p_text(linha) for linha in linhas), estilo)
            altura_maxima = lado_qr if png else (24 * mm if self.tamanho != "80mm" else 18 * mm)
            _, altura_texto = texto.wrap(largura_texto, altura_maxima)
            if altura_texto > altura_maxima:
                # Reduz ligeiramente o corpo, em vez de sobrepor o rodapé da página.
                estilo.fontSize = 4.5 if self.tamanho != "80mm" else 3.8
                estilo.leading = 5.2 if self.tamanho != "80mm" else 4.4
                texto = Paragraph("<br/>".join(_p_text(linha) for linha in linhas), estilo)
                _, altura_texto = texto.wrap(largura_texto, altura_maxima)
            y_texto = y_qr + lado_qr - min(altura_texto, altura_maxima) if png else 16 * mm
            texto.drawOn(pdf_canvas, margem_esquerda, y_texto)

        pdf_canvas.restoreState()

    # ------------------------------------------------------------------
    # Composição e paginação
    # ------------------------------------------------------------------
    def _story(self, compact=False):
        styles = self._estilos(compacto=compact)
        story = []
        story.extend(self._cabecalho(styles, compact=compact))
        story.extend(self._bloco_cliente_metadados(styles, compact=compact))
        story.extend(self._bloco_pagamento(styles, compact=compact))
        story.extend(self._tabela_linhas(styles, compact=compact))

        # Os totais, observações e QR são colocados depois de todas as linhas.
        # Em documentos comuns, o bloco final tenta manter-se unido na última página.
        totais = self._bloco_totais_fiscais(styles, compact=compact)
        if totais:
            # Mantém o resumo fiscal unido quando cabe; a tabela de linhas já
            # terminou, portanto nenhum total aparece antes das linhas restantes.
            story.append(KeepTogether(totais))
        story.extend(self._bloco_observacoes(styles, compact=compact))
        story.extend(self._bloco_qr(styles, compact=compact))
        return story

    def _decorar_pagina(self, pdf_canvas, doc):
        pdf_canvas.saveState()
        largura, altura = doc.pagesize
        if self._anulado:
            _marca_dagua_anulado(pdf_canvas, largura, altura)
        elif self._proforma:
            _marca_dagua_texto(pdf_canvas, largura, altura, "PRÓ-FORMA — NÃO SERVE DE FACTURA", COR_PROFORMA)
        elif self._rascunho:
            _marca_dagua_texto(pdf_canvas, largura, altura, "RASCUNHO — RASCUNHO", COR_PROFORMA)

        pdf_canvas.setStrokeColor(self.DOC_BORDA)
        pdf_canvas.setLineWidth(0.45)
        pdf_canvas.line(doc.leftMargin, 13 * mm, largura - doc.rightMargin, 13 * mm)
        pdf_canvas.setFillColor(self.DOC_TEXTO_SEC)
        pdf_canvas.setFont("Helvetica", 6)
        #pdf_canvas.drawString(
         #   doc.leftMargin,
          #  8 * mm,
           # _safe_text("VistoGest Pro — SOTARQ Software (SU), Lda")[:130],
        #)
        pdf_canvas.restoreState()

    def gerar(self) -> io.BytesIO:
        if self.tamanho == "80mm":
            return self._gerar_termico()
        return self._gerar_a4()

    def _construir_pdf(self, pagesize, margens, compacto=False):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            leftMargin=margens[0],
            rightMargin=margens[1],
            topMargin=margens[2],
            bottomMargin=margens[3],
            title=_safe_text(f"{self._tipo_label()} {self._numero() or 'NÃO EMITIDO'}"),
            author=_safe_text(self._dados_emissor()["nome"]),
            subject="Documento fiscal",
        )
        # O canvas personalizado consegue indicar o total de páginas.
        def canvasmaker(*args, **kwargs):
            pdf_canvas = _PDFNumberedCanvas(*args, **kwargs)
            pdf_canvas._pdf_right_margin = margens[1]
            pdf_canvas._pdf_left_margin = margens[0]
            pdf_canvas._pdf_document_service = self
            return pdf_canvas

        doc.build(
            self._story(compact=compacto),
            onFirstPage=self._decorar_pagina,
            onLaterPages=self._decorar_pagina,
            canvasmaker=canvasmaker,
        )
        buffer.seek(0)
        return buffer

    def _gerar_a4(self) -> io.BytesIO:
        return self._construir_pdf(
            pagesize=A4,
            margens=(15 * mm, 15 * mm, 12 * mm, 45 * mm),
            compacto=False,
        )

    def _gerar_termico(self) -> io.BytesIO:
        linhas = self._linhas_doc()
        comentarios = self._comentarios()
        estimativa_mm = 210 + sum(
            12 + min(26, math.ceil(len(linha.get("desc", "")) / 28) * 2.8)
            for linha in linhas
        )
        estimativa_mm += min(70, math.ceil(len(comentarios) / 40) * 3)
        if self._logo_empresa():
            estimativa_mm += 16
        altura = max(250 * mm, estimativa_mm * mm)
        return self._construir_pdf(
            pagesize=(80 * mm, altura),
            margens=(4 * mm, 4 * mm, 4 * mm, 28 * mm),
            compacto=True,
        )


########
# Recibos de vencimento/Salário — PDF para entrega ao colaborador/funcionário
########
# ─────────────────────────────────────────────────────────────────────────────
# PDFReciboVencimentoService — Recibo de Vencimento (documento laboral, não fiscal AGT)
# ─────────────────────────────────────────────────────────────────────────────
from xml.sax.saxutils import escape as _esc

from reportlab.platypus import (
    HRFlowable, Image as RLImage, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
    Table as RLTable, TableStyle as RLTableStyle,
)


def _fmt_valor(v, casas: int = 2) -> str:
    """Formato 1.234.567,89 com arredondamento meio-para-cima (igual ao motor salarial)."""
    d = Decimal(str(v or 0)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    return f"{d:,.{casas}f}".replace(',', 'X').replace('.', ',').replace('X', '.')


class PDFReciboVencimentoService:
    """Gera o PDF do recibo (A4). Adapta-se ao nº de rubricas (quebra de página automática)."""
    ESTADO_MARCA = {'ANULADO': 'ANULADO', 'RETIFICADO': 'RETIFICADO', 'RASCUNHO': 'RASCUNHO', 'CALCULADO': 'NÃO EMITIDO'}

    def __init__(self, recibo, mostrar_iban_completo: bool = False, configuracao=None):
        self.r = recibo
        self.cfg = configuracao
        self.iban = recibo.func_iban if mostrar_iban_completo else recibo.func_iban_mascarado
        base = getSampleStyleSheet()['Normal']
        self.s = ParagraphStyle('rv', parent=base, fontName='Helvetica', fontSize=7.5, leading=9.5)
        self.sb = ParagraphStyle('rvb', parent=self.s, fontName='Helvetica-Bold')
        self.sr = ParagraphStyle('rvr', parent=self.s, alignment=TA_RIGHT)
        self.sh = ParagraphStyle('rvh', parent=self.sb, textColor=colors.white, fontSize=7)
        self.shr = ParagraphStyle('rvhr', parent=self.sh, alignment=TA_RIGHT)

    # ── helpers ─────────────────────────────────────────────────────────────
    def _p(self, txt, estilo=None):
        return Paragraph(_esc(str(txt if txt not in (None, '') else '—')), estilo or self.s)

    def _logo(self):
        foto = getattr(connection.tenant, 'foto', None)
        if not foto:
            return None
        try:
            r = requests.get(foto.url, timeout=5)
            img = RLImage(io.BytesIO(r.content))
            img._restrictSize(3.2 * cm, 2.2 * cm)
            return img
        except Exception as exc:
            logger.warning("Logo da empresa indisponível no recibo: %s", exc)
            return None

    def _estilo_tabela(self, n_cols_dir):
        return RLTableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_PRIMARIA), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.3, COR_BORDA), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COR_CINZA_LINHA]),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ])

    # ── blocos ──────────────────────────────────────────────────────────────
    def _cabecalho(self):
        r = self.r
        emp = [self._p(r.empresa_nome, ParagraphStyle('e', parent=self.sb, fontSize=11, leading=13)),
               self._p(f"NIF: {r.empresa_nif}" + (f"  |  INSS n.º {r.empresa_inss}" if r.empresa_inss else '')),
               self._p(r.empresa_endereco), self._p(r.empresa_contactos)]
        esq = [[self._logo() or '', emp]]
        t_esq = RLTable(esq, colWidths=[3.4 * cm, 7.1 * cm])
        t_esq.setStyle(RLTableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        tit = ParagraphStyle('t', parent=self.sb, fontSize=13, leading=15, textColor=colors.white, alignment=TA_CENTER)
        sub = ParagraphStyle('t2', parent=self.s, textColor=colors.white, alignment=TA_CENTER, fontSize=8)
        dir_ = RLTable([[Paragraph("RECIBO DE VENCIMENTO", tit)], [Paragraph(_esc(r.numero), ParagraphStyle('n', parent=sub, fontName='Helvetica-Bold', fontSize=9))],
                        [Paragraph(f"Período: {r.periodo}", sub)]], colWidths=[7.3 * cm])
        dir_.setStyle(RLTableStyle([('BACKGROUND', (0, 0), (-1, -1), COR_PRIMARIA), ('TOPPADDING', (0, 0), (-1, -1), 3),
                                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        topo = RLTable([[t_esq, dir_]], colWidths=[10.7 * cm, 7.3 * cm])
        topo.setStyle(RLTableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        emissao = r.data_emissao.strftime('%d/%m/%Y') if r.data_emissao else '—'
        pag = r.data_pagamento.strftime('%d/%m/%Y') if r.data_pagamento else '—'
        proc = r.processamento.get_estado_display() if getattr(r, 'processamento_id', None) else '—'
        meta = RLTable([[self._p(f"Data de emissão: {emissao}"), self._p(f"Data de pagamento: {pag}"),
                         self._p(f"Moeda: {r.moeda}"), self._p(f"Estado: {r.get_estado_display()}  |  Processamento: {proc}")]],
                       colWidths=[3.8 * cm, 4 * cm, 2.4 * cm, 7.8 * cm])
        meta.setStyle(RLTableStyle([('BOX', (0, 0), (-1, -1), 0.3, COR_BORDA), ('BACKGROUND', (0, 0), (-1, -1), COR_CINZA_CABEC)]))
        return [topo, Spacer(1, 0.25 * cm), meta, Spacer(1, 0.3 * cm)]

    def _funcionario(self):
        r = self.r
        adm = r.func_data_admissao.strftime('%d/%m/%Y') if r.func_data_admissao else '—'
        def par(rotulo, valor):
            return [self._p(rotulo, self.sb), self._p(valor)]
        linhas = [
            par("Nome", r.func_nome) + par("N.º interno", r.func_matricula),
            par("NIF", r.func_nif) + par("N.º INSS", r.func_inss),
            par("Cargo / função", r.func_cargo) + par("Categoria", r.func_categoria),
            par("Departamento", r.func_departamento) + par("Unidade", r.func_unidade),
            par("Tipo de contrato", r.func_tipo_contrato) + par("Admissão", adm),
            par("IBAN / conta", self.iban) + par("Período salarial", r.periodo),
        ]
        t = RLTable(linhas, colWidths=[2.6 * cm, 6.4 * cm, 2.6 * cm, 6.4 * cm])
        t.setStyle(RLTableStyle([('BOX', (0, 0), (-1, -1), 0.3, COR_BORDA), ('INNERGRID', (0, 0), (-1, -1), 0.2, COR_BORDA),
                                 ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        return [Paragraph("Identificação do funcionário", ParagraphStyle('h', parent=self.sb, fontSize=8.5, spaceAfter=2)), t, Spacer(1, 0.3 * cm)]

    def _linhas(self, tipo):
        return [l for l in self.r.linhas.all().order_by('ordem', 'id') if l.tipo == tipo]

    def _tab_remuneracoes(self):
        cab = [Paragraph(x, self.sh) for x in ("Cód.", "Designação", "Qtd.")] + \
              [Paragraph(x, self.shr) for x in ("Base", "%", "V. calculado", "V. final")]
        dados = [cab]
        for l in self._linhas('REMUNERACAO'):
            dados.append([self._p(l.codigo), self._p(l.designacao), self._p(_fmt_valor(l.quantidade) if l.quantidade is not None else ''),
                          self._p(_fmt_valor(l.base_calculo) if l.base_calculo else '', self.sr),
                          self._p(_fmt_valor(l.taxa) if l.taxa is not None else '', self.sr),
                          self._p(_fmt_valor(l.valor_calculado), self.sr), self._p(_fmt_valor(l.valor_final), self.sb if False else self.sr)])
        t = RLTable(dados, colWidths=[1.6 * cm, 5.4 * cm, 1.6 * cm, 2.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm], repeatRows=1)
        t.setStyle(self._estilo_tabela(4))
        return [Paragraph("Remunerações e abonos", ParagraphStyle('h', parent=self.sb, fontSize=8.5, spaceAfter=2)), t, Spacer(1, 0.3 * cm)]

    def _tab_descontos(self):
        cab = [Paragraph(x, self.sh) for x in ("Cód.", "Designação")] + \
              [Paragraph(x, self.shr) for x in ("Base", "%", "V. calculado", "V. final")] + [Paragraph("Observação", self.sh)]
        dados = [cab]
        for l in self._linhas('DESCONTO'):
            dados.append([self._p(l.codigo), self._p(l.designacao), self._p(_fmt_valor(l.base_calculo) if l.base_calculo else '', self.sr),
                          self._p(_fmt_valor(l.taxa) if l.taxa is not None else '', self.sr),
                          self._p(_fmt_valor(l.valor_calculado), self.sr), self._p(_fmt_valor(l.valor_final), self.sr),
                          self._p(l.observacao, ParagraphStyle('o', parent=self.s, fontSize=6.5, leading=8))])
        if len(dados) == 1:
            dados.append([self._p('—')] * 7)
        t = RLTable(dados, colWidths=[1.6 * cm, 4.2 * cm, 2.3 * cm, 1.4 * cm, 2.3 * cm, 2.3 * cm, 3.9 * cm], repeatRows=1)
        t.setStyle(self._estilo_tabela(4))
        return [Paragraph("Descontos e deduções", ParagraphStyle('h', parent=self.sb, fontSize=8.5, spaceAfter=2)), t, Spacer(1, 0.3 * cm)]

    def _resumo(self):
        r = self.r
        linhas = [["Salário-base", _fmt_valor(r.salario_base)],
                  ["Total de remunerações adicionais", _fmt_valor(r.total_remuneracoes_adicionais)],
                  ["Salário ilíquido", _fmt_valor(r.salario_iliquido)],
                  ["Total de descontos", _fmt_valor(r.total_descontos)],
                  [f"SALÁRIO LÍQUIDO A RECEBER ({r.moeda})", _fmt_valor(r.salario_liquido)]]
        t = RLTable([[self._p(a, self.sb if i in (2, 4) else self.s), self._p(b, self.sr if i != 4 else ParagraphStyle('l', parent=self.sr, fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.white))]
                     for i, (a, b) in enumerate(linhas)], colWidths=[11 * cm, 5 * cm], hAlign='RIGHT')
        t.setStyle(RLTableStyle([('GRID', (0, 0), (-1, -1), 0.3, COR_BORDA), ('BACKGROUND', (0, 2), (-1, 2), COR_CINZA_CABEC),
                                 ('BACKGROUND', (0, 4), (-1, 4), COR_PRIMARIA), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        t.setStyle(RLTableStyle([('TEXTCOLOR', (0, 4), (0, 4), colors.white)]))
        out = [t]
        enc = self._linhas('ENCARGO')
        if enc:
            nota = " | ".join(f"{l.designacao}: {_fmt_valor(l.valor_final)}" for l in enc)
            out += [Spacer(1, 0.15 * cm), Paragraph(_esc(f"Encargos da entidade empregadora (não descontados ao trabalhador): {nota}"),
                                                      ParagraphStyle('enc', parent=self.s, fontSize=6.8, textColor=colors.grey, alignment=TA_RIGHT))]
        return out + [Spacer(1, 0.4 * cm)]

    def _assinaturas(self):
        r, cfg = self.r, self.cfg
        blocos = []
        if cfg is None or cfg.exigir_assinatura_trabalhador:
            blocos.append(("O trabalhador", r.func_nome))
        blocos.append(("O responsável pelo processamento", r.nome_responsavel))
        if cfg is not None and cfg.mostrar_assinatura_contabilista:
            nome = r.contabilista_nome or cfg.contabilista_nome
            ordem = r.contabilista_numero_ordem or cfg.contabilista_numero_ordem
            blocos.append(("O contabilista" + (f" (inscrição n.º {ordem})" if ordem else ''), nome))
        larg = 18 * cm / len(blocos)
        linha1 = [Spacer(1, 1.3 * cm)] * len(blocos)
        linha2 = [Paragraph(_esc(t), ParagraphStyle('a', parent=self.s, alignment=TA_CENTER, fontSize=7)) for t, _ in blocos]
        linha3 = [Paragraph(_esc(n or ''), ParagraphStyle('a2', parent=self.s, alignment=TA_CENTER, fontSize=6.5, textColor=colors.grey)) for _, n in blocos]
        t = RLTable([linha1, linha2, linha3], colWidths=[larg] * len(blocos))
        t.setStyle(RLTableStyle([('LINEABOVE', (0, 1), (-1, 1), 0.5, colors.black), ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12)]))
        ref = [f"Referência do pagamento: {r.referencia_pagamento}"] if r.referencia_pagamento else []
        if r.data_assinatura:
            ref.append(f"Data da assinatura: {r.data_assinatura:%d/%m/%Y}")
        if r.observacoes:
            ref.append(f"Observações: {r.observacoes}")
        extra = [Paragraph(_esc("  |  ".join(ref[:2]) + ("<br/>" if False else '')), self.s)] if ref[:2] else []
        obs = [Paragraph(_esc(ref[2]), self.s)] if len(ref) > 2 else []
        return [KeepTogether([HRFlowable(width='100%', color=COR_BORDA), Spacer(1, 0.2 * cm), *extra, *obs, Spacer(1, 0.2 * cm), t])]

    def _decorar(self, c, doc):
        r = self.r
        c.saveState()
        c.setFont('Helvetica', 6.3)
        c.setFillColor(colors.grey)
        codigo = (r.hash_integridade or '—')[:16].upper()
        rodape = (self.cfg.texto_rodape if self.cfg and self.cfg.texto_rodape else "Documento processado por computador")
        c.drawString(1.5 * cm, 1.0 * cm, f"{rodape} • {r.numero} • Cód. verificação: {codigo}")
        c.drawRightString(A4[0] - 1.5 * cm, 1.0 * cm, f"Página {doc.page}")
        marca = self.ESTADO_MARCA.get(r.estado)
        if marca:
            c.translate(A4[0] / 2, A4[1] / 2)
            c.rotate(45)
            c.setFont('Helvetica-Bold', 70)
            c.setFillColor(colors.Color(1, 0, 0, alpha=0.12))
            c.drawCentredString(0, 0, marca)
        c.restoreState()

    # ── ponto de entrada ────────────────────────────────────────────────────
    def gerar(self) -> io.BytesIO:
        r = self.r
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.4 * cm,
                                bottomMargin=1.8 * cm, title=f"Recibo de Vencimento {r.numero}", author=r.empresa_nome)
        story = (self._cabecalho() + self._funcionario() + self._tab_remuneracoes() + self._tab_descontos()
                 + self._resumo() + self._assinaturas())
        doc.build(story, onFirstPage=self._decorar, onLaterPages=self._decorar)
        buf.seek(0)

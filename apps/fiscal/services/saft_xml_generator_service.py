# apps/fiscal/services/saft_xml_generator_service.py
"""
Gerador de SAF-T AO 1.01_01 conforme:
  - XSD: apps/fiscal/schemas/SAFTAO1.01_01.xsd
  - Decreto Executivo 683/25 (Anexos I/II/III)
  - Notificação AGT Ref: 0000497/01180000/AGT/2026

Correcções aplicadas (vs. versão anterior):
  5.1  SpecialRegimes obrigatório em cada Invoice/StockMovement/WorkDocument
  5.2  Period (mês 1-12) obrigatório em todos os documentos
  5.3  HashControl usa settings.AGT_SOFTWARE_VALIDATION_NUMBER
  5.4  InvoiceType dinâmico (não hardcoded "FR")
  5.5  Roteamento correcto por secção SAF-T
  5.6  OrderReferences em faturas com pró-forma de origem
  5.7  References em Notas de Crédito
  5.8  TaxExemptionReason/Code correcto (a partir do modelo, não hardcoded)
  5.9  _build_clientes com CustomerTaxID, SelfBillingIndicator, BillingAddress
  5.10 Header: ProductCompanyTaxID, SoftwareValidationNumber, ProductID de settings
  11   WithholdingTax exportado; SourceBilling correcto; TotalDebit/Credit correcto
"""
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.fiscal.models import (
    TaxaIVAAGT, AssinaturaDigital, DocumentoFiscal, RetencaoFonte,
)
from apps.vendas.models import (
    Venda, FaturaCredito, Recibo, FaturaProforma,
    NotaCredito, NotaDebito, DocumentoTransporte,
)
from apps.clientes.models import Cliente
from apps.produtos.models import Produto
from apps.servicos.models import Servico
from .saft_mapping import mapear_withholding_tax_saft


# ---------------------------------------------------------------------------
# Mapeamento tipo_documento → secção SAF-T
# ---------------------------------------------------------------------------
SALES_INVOICES_TYPES = {"FT", "FR", "GF", "FG", "AC", "AR", "AF", "TV", "ND", "NC", "FA", "RP", "RE", "CS", "LD", "RA"}
MOVEMENT_TYPES       = {"DT", "GT"}   # Guias de remessa / transporte
WORKING_DOC_TYPES    = {"FP", "OR"}   # Pró-formas / orçamentos
PAYMENT_TYPES        = {"RC", "RG"}   # Recibos


class SaftXmlGeneratorService:
    """
    Gera o ficheiro SAF-T AO 1.01_01 para o período solicitado.

    Isolamento físico: `empresa` é passada para construir o Header e filtrar
    os dados do tenant activo. Não usa filtros company_id dentro dos modelos
    de tenant (o schema já isola).
    """

    def __init__(self, empresa, data_inicio, data_fim):
        self.empresa = empresa
        self.data_inicio = data_inicio
        self.data_fim = data_fim
        self.ns = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"
        ET.register_namespace('', self.ns)

    # ------------------------------------------------------------------
    # Helpers de formatação
    # ------------------------------------------------------------------

    def _e(self, tag: str) -> str:
        """Namespace-qualified tag."""
        return f"{{{self.ns}}}{tag}"

    def _fmt(self, valor, casas: int = 2) -> str:
        """Arredondamento por excesso (ROUND_UP) — regra fiscal AGT."""
        if valor is None:
            return f"{'0.' + '0' * casas}"
        return str(Decimal(str(valor)).quantize(
            Decimal(f"1.{'0' * casas}"), rounding=ROUND_UP
        ))

    def _fmt_unit(self, valor) -> str:
        """UnitPrice com 4 casas decimais (arredondamento matemático)."""
        if valor is None:
            return "0.0000"
        return str(Decimal(str(valor)).quantize(
            Decimal("1.0000"), rounding=ROUND_HALF_UP
        ))

    def _sub(self, parent, tag: str, text: str = "") -> ET.Element:
        el = ET.SubElement(parent, self._e(tag))
        el.text = str(text) if text is not None else ""
        return el

    def _period(self, date_obj) -> str:
        """Período contabilístico = número do mês (1–12)."""
        return str(date_obj.month) if date_obj else ""

    def _source_billing(self) -> str:
        """P = produzido por software de facturação (standalone)."""
        return "P"

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def generate_xml(self) -> bytes:
        root = ET.Element(self._e("AuditFile"))

        self._build_header(root)

        master = ET.SubElement(root, self._e("MasterFiles"))
        self._build_clientes(master)
        self._build_fornecedores(master)
        self._build_products(master)
        self._build_tax_table(master)

        source = ET.SubElement(root, self._e("SourceDocuments"))
        self._build_sales_invoices(source)
        self._build_movement_of_goods(source)
        self._build_working_documents(source)
        self._build_payments(source)

        return ET.tostring(root, encoding="UTF-8", xml_declaration=True)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self, parent):
        h = ET.SubElement(parent, self._e("Header"))

        self._sub(h, "AuditFileVersion", "1.01_01")
        self._sub(h, "CompanyID", self.empresa.nif or "")
        self._sub(h, "TaxRegistrationNumber", self.empresa.nif or "")
        self._sub(h, "TaxAccountingBasis", "F")   # F = Facturação
        self._sub(h, "CompanyName", self.empresa.nome or "")

        # Endereço (AddressStructureAO: Country fixo "AO")
        addr = ET.SubElement(h, self._e("CompanyAddress"))
        self._sub(addr, "AddressDetail", getattr(self.empresa, 'endereco', '') or "Luanda")
        self._sub(addr, "City", getattr(self.empresa, 'cidade', '') or "Luanda")
        self._sub(addr, "Country", "AO")

        self._sub(h, "FiscalYear", str(self.data_inicio.year))
        self._sub(h, "StartDate", self.data_inicio.strftime("%Y-%m-%d"))
        self._sub(h, "EndDate", self.data_fim.strftime("%Y-%m-%d"))
        self._sub(h, "CurrencyCode", "AOA")
        self._sub(h, "DateCreated", timezone.now().strftime("%Y-%m-%d"))
        self._sub(h, "TaxEntity", "Global")

        # Dados do produtor de software (SOTARQ)
        self._sub(
            h, "ProductCompanyTaxID",
            getattr(settings, "AGT_PRODUCT_COMPANY_TAX_ID", "5002764377"),
        )
        self._sub(
            h, "SoftwareValidationNumber",
            getattr(settings, "AGT_SOFTWARE_VALIDATION_NUMBER", "0"),
        )
        self._sub(
            h, "ProductID",
            getattr(settings, "AGT_PRODUCT_ID", "VistoGest Pro/SOTARQ Software"),
        )
        self._sub(
            h, "ProductVersion",
            getattr(settings, "AGT_SOFTWARE_PRODUCT_VERSION", "1.0.0"),
        )

    # ------------------------------------------------------------------
    # MasterFiles — Clientes
    # ------------------------------------------------------------------

    def _build_clientes(self, parent):
        clientes = Cliente.objects.all()

        # Cliente genérico "Consumidor Final" sempre presente
        self._escrever_cliente(
            parent,
            customer_id="999999999",
            account_id="Desconhecido",
            tax_id="999999999",
            nome="Consumidor Final",
            address_detail="Luanda",
            city="Luanda",
            country="AO",
            self_billing=0,
        )

        for cli in clientes:
            nif = (cli.nif or "").strip() or "999999999"
            endereco = ""
            cidade = "Luanda"
            if hasattr(cli, 'enderecos'):
                principal = cli.enderecos.filter(endereco_principal=True).first()
                if principal:
                    endereco = getattr(principal, 'endereco_completo', '') or ""
                    cidade = getattr(principal, 'cidade', '') or cidade

            self._escrever_cliente(
                parent,
                customer_id=str(cli.id),
                account_id="Desconhecido",
                tax_id=nif,
                nome=cli.nome_completo if hasattr(cli, 'nome_completo') else str(cli),
                address_detail=endereco or "Luanda",
                city=cidade,
                country="AO",
                self_billing=0,
            )

    def _escrever_cliente(self, parent, customer_id, account_id, tax_id,
                          nome, address_detail, city, country, self_billing):
        c = ET.SubElement(parent, self._e("Customer"))
        self._sub(c, "CustomerID", customer_id)
        self._sub(c, "AccountID", account_id)
        self._sub(c, "CustomerTaxID", tax_id)
        self._sub(c, "CompanyName", nome[:200])
        addr = ET.SubElement(c, self._e("BillingAddress"))
        self._sub(addr, "AddressDetail", (address_detail or "Luanda")[:250])
        self._sub(addr, "City", (city or "Luanda")[:50])
        self._sub(addr, "Country", country[:2])
        self._sub(c, "SelfBillingIndicator", str(self_billing))

    # ------------------------------------------------------------------
    # MasterFiles — Fornecedores (stub mínimo)
    # ------------------------------------------------------------------

    def _build_fornecedores(self, parent):
        try:
            from apps.fornecedores.models import Fornecedor
            fornecedores = Fornecedor.objects.all()[:200]
            for forn in fornecedores:
                s = ET.SubElement(parent, self._e("Supplier"))
                self._sub(s, "SupplierID", str(forn.id))
                self._sub(s, "AccountID", "Desconhecido")
                self._sub(s, "SupplierTaxID", (forn.nif or "000000000")[:20])
                self._sub(s, "CompanyName", str(forn)[:200])
                addr = ET.SubElement(s, self._e("BillingAddress"))
                self._sub(addr, "AddressDetail", "Luanda")
                self._sub(addr, "City", "Luanda")
                self._sub(addr, "Country", "AO")
                self._sub(s, "SelfBillingIndicator", "0")
        except Exception:
            pass  # Fornecedores são opcionais no SAF-T de facturação

    # ------------------------------------------------------------------
    # MasterFiles — Produtos
    # ------------------------------------------------------------------

    def _build_products(self, parent):
        for prod in Produto.objects.filter(ativo=True):
            el = ET.SubElement(parent, self._e("Product"))
            self._sub(el, "ProductType", "P")
            self._sub(el, "ProductCode", (prod.codigo_interno or str(prod.id))[:60])
            self._sub(el, "ProductDescription", prod.nome_produto[:200])
            self._sub(
                el, "ProductNumberCode",
                (prod.codigo_barras or prod.codigo_interno or str(prod.id))[:60],
            )

        for serv in Servico.objects.filter(ativo=True):
            el = ET.SubElement(parent, self._e("Product"))
            self._sub(el, "ProductType", "S")
            code = f"SRV-{serv.id}"
            self._sub(el, "ProductCode", code[:60])
            self._sub(el, "ProductDescription", serv.nome[:200])
            self._sub(el, "ProductNumberCode", code[:60])

    # ------------------------------------------------------------------
    # MasterFiles — TaxTable
    # ------------------------------------------------------------------

    def _build_tax_table(self, parent):
        table = ET.SubElement(parent, self._e("TaxTable"))
        for taxa in TaxaIVAAGT.objects.filter(ativo=True):
            entry = ET.SubElement(table, self._e("TaxTableEntry"))
            # TaxType: IVA | IS | NS  (corrigir NSU → NS)
            tax_type = taxa.tax_type if taxa.tax_type in ("IVA", "IS", "NS") else "IVA"
            self._sub(entry, "TaxType", tax_type)
            self._sub(entry, "TaxCountryRegion", "AO")
            # TaxCode: NOR|INT|RED|ISE|OUT|NS|NA
            tax_code = taxa.tax_code
            if tax_code == "NSU":
                tax_code = "NS"
            self._sub(entry, "TaxCode", tax_code)
            self._sub(entry, "Description", taxa.nome[:255])
            self._sub(entry, "TaxPercentage", self._fmt(taxa.tax_percentage))

    # ------------------------------------------------------------------
    # SourceDocuments — SalesInvoices
    # ------------------------------------------------------------------

    def _build_sales_invoices(self, parent):
        # Recolhe todos os DocumentoFiscal do período cujo tipo vai nesta secção
        docs = DocumentoFiscal.objects.filter(
            data_emissao__range=(self.data_inicio, self.data_fim),
            tipo_documento__in=SALES_INVOICES_TYPES,
        ).order_by("tipo_documento", "serie", "numero")

        if not docs.exists():
            return

        sales = ET.SubElement(parent, self._e("SalesInvoices"))
        self._sub(sales, "NumberOfEntries", str(docs.count()))

        # TotalDebit = soma de DebitAmount (NC, ND) de documentos com status N
        total_debit = docs.filter(
            tipo_documento__in={"NC", "ND"}, status="confirmed"
        ).aggregate(s=Sum("valor_total"))["s"] or Decimal("0.00")
        total_credit = docs.filter(
            status="confirmed"
        ).exclude(
            tipo_documento__in={"NC", "ND"}
        ).aggregate(s=Sum("valor_total"))["s"] or Decimal("0.00")

        self._sub(sales, "TotalDebit", self._fmt(total_debit))
        self._sub(sales, "TotalCredit", self._fmt(total_credit))

        for doc in docs:
            self._build_invoice(sales, doc)

    def _build_invoice(self, parent, doc):
        inv = ET.SubElement(parent, self._e("Invoice"))
        self._sub(inv, "InvoiceNo", doc.numero_documento)

        # DocumentStatus
        ds = ET.SubElement(inv, self._e("DocumentStatus"))
        inv_status = "A" if doc.status == "cancelled" else "N"
        self._sub(ds, "InvoiceStatus", inv_status)
        self._sub(
            ds, "InvoiceStatusDate",
            (doc.data_confirmacao or doc.created_at).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._sub(ds, "SourceID", str(doc.usuario_criacao_id or "Sistema"))
        self._sub(ds, "SourceBilling", self._source_billing())

        # Hash e HashControl
        self._sub(inv, "Hash", doc.hash_documento or "0")
        self._sub(
            inv, "HashControl",
            getattr(settings, "AGT_SOFTWARE_VALIDATION_NUMBER", "0"),
        )

        # Period (mês 1-12) — exigido pela notificação AGT
        self._sub(inv, "Period", self._period(doc.data_emissao))

        self._sub(inv, "InvoiceDate", doc.data_emissao.strftime("%Y-%m-%d"))

        # InvoiceType dinâmico
        invoice_type = doc.tipo_documento
        self._sub(inv, "InvoiceType", invoice_type)

        # SpecialRegimes (obrigatório pelo XSD)
        sr = ET.SubElement(inv, self._e("SpecialRegimes"))
        self._sub(sr, "SelfBillingIndicator", "1" if invoice_type == "AF" else "0")
        self._sub(sr, "CashVATSchemeIndicator", "0")
        self._sub(sr, "ThirdPartiesBillingIndicator", "0")

        self._sub(
            inv, "SourceID",
            str(doc.usuario_criacao_id or "Sistema"),
        )
        self._sub(
            inv, "SystemEntryDate",
            doc.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # CustomerID — FK para o Customer em MasterFiles
        if doc.cliente_id:
            self._sub(inv, "CustomerID", str(doc.cliente_id))
        else:
            self._sub(inv, "CustomerID", "999999999")

        # Linhas
        self._build_invoice_lines(inv, doc)

        # DocumentTotals
        totals = ET.SubElement(inv, self._e("DocumentTotals"))
        self._sub(totals, "TaxPayable", self._fmt(doc.valor_iva))
        self._sub(totals, "NetTotal", self._fmt(doc.valor_base))
        self._sub(totals, "GrossTotal", self._fmt(doc.valor_total))

        # Currency (só quando moeda ≠ AOA)
        if doc.moeda and doc.moeda != "AOA":
            cur = ET.SubElement(totals, self._e("Currency"))
            self._sub(cur, "CurrencyCode", doc.moeda)
            taxa_cambio = doc.taxa_cambio or Decimal("1")
            valor_moeda = doc.valor_total / taxa_cambio if taxa_cambio else doc.valor_total
            self._sub(cur, "CurrencyAmount", self._fmt(valor_moeda))
            self._sub(cur, "ExchangeRate", str(taxa_cambio))

        # WithholdingTax
        self._build_withholding_tax(inv, doc)

    def _build_invoice_lines(self, parent, doc):
        linhas = doc.linhas.all().order_by("numero_linha") if hasattr(doc, "linhas") else []

        # Fallback via Venda ligada
        if not linhas:
            venda = getattr(doc, "venda", None)
            if venda:
                self._build_lines_from_venda(parent, venda, doc)
                return
            fatura = getattr(doc, "fatura_credito", None)
            if fatura:
                self._build_lines_from_fatura(parent, fatura, doc)
                return

        for idx, linha in enumerate(linhas, start=1):
            ln = ET.SubElement(parent, self._e("Line"))
            self._sub(ln, "LineNumber", str(idx))

            # OrderReferences (ponto 5.6 — fatura com pró-forma de origem)
            self._build_order_references(ln, doc)

            self._sub(ln, "ProductCode", (linha.codigo_produto or "")[:60])
            self._sub(ln, "ProductDescription", (linha.descricao or "")[:200])
            self._sub(ln, "Quantity", str(linha.quantidade))
            self._sub(ln, "UnitOfMeasure", getattr(linha, "unidade", "UN") or "UN")
            self._sub(ln, "UnitPrice", self._fmt_unit(linha.valor_unitario))
            self._sub(ln, "TaxPointDate", doc.data_emissao.strftime("%Y-%m-%d"))

            # References (ponto 5.7 — só em NC)
            if doc.tipo_documento == "NC":
                self._build_references_linha(ln, linha)

            self._sub(ln, "Description", (linha.descricao or "")[:200])

            # DebitAmount / CreditAmount
            if doc.tipo_documento in {"NC", "ND"}:
                self._sub(ln, "DebitAmount", self._fmt(linha.valor_sem_iva))
            else:
                self._sub(ln, "CreditAmount", self._fmt(linha.valor_sem_iva))

            # Tax
            self._build_tax_linha(ln, linha)

            # SettlementAmount (desconto de linha + proporção do global)
            self._sub(ln, "SettlementAmount", self._fmt_unit(
                self._settlement_linha(linha, doc)
            ))

    def _build_lines_from_venda(self, parent, venda, doc):
        desconto_global = float(venda.desconto_valor or 0)
        subtotal_doc = float(venda.subtotal or 1)

        for idx, item in enumerate(venda.itens.all().order_by("id"), start=1):
            ln = ET.SubElement(parent, self._e("Line"))
            self._sub(ln, "LineNumber", str(idx))

            self._build_order_references(ln, doc)

            p_code = item.produto.codigo_interno if item.produto else f"SRV-{item.servico.id if item.servico else idx}"
            p_desc = item.nome_produto or (item.produto.nome_produto if item.produto else
                     (item.servico.nome if item.servico else "Item"))

            self._sub(ln, "ProductCode", p_code[:60])
            self._sub(ln, "ProductDescription", p_desc[:200])
            self._sub(ln, "Quantity", str(item.quantidade))
            self._sub(ln, "UnitOfMeasure", "UN")

            # UnitPrice = preço sem desconto de linha e sem imposto, 4 casas
            self._sub(ln, "UnitPrice", self._fmt_unit(item.preco_unitario))
            self._sub(ln, "TaxPointDate", venda.data_venda.strftime("%Y-%m-%d"))

            if doc.tipo_documento == "NC":
                self._build_references_linha(ln, item)

            self._sub(ln, "Description", p_desc[:200])

            if doc.tipo_documento in {"NC", "ND"}:
                self._sub(ln, "DebitAmount", self._fmt(item.subtotal_sem_iva or item.total))
            else:
                self._sub(ln, "CreditAmount", self._fmt(item.subtotal_sem_iva or item.total))

            # Tax
            if item.taxa_iva:
                tax_el = ET.SubElement(ln, self._e("Tax"))
                tax_type = item.taxa_iva.tax_type if item.taxa_iva.tax_type in ("IVA", "IS", "NS") else "IVA"
                self._sub(tax_el, "TaxType", tax_type)
                self._sub(tax_el, "TaxCountryRegion", "AO")
                tax_code = item.taxa_iva.tax_code if item.taxa_iva.tax_code != "NSU" else "NS"
                self._sub(tax_el, "TaxCode", tax_code)
                self._sub(tax_el, "TaxPercentage", self._fmt(item.taxa_iva.tax_percentage))

                # TaxExemptionReason/Code (5.8)
                if float(item.taxa_iva.tax_percentage or 0) == 0:
                    code = item.taxa_iva.exemption_reason or "M02"
                    self._sub(ln, "TaxExemptionReason",
                               dict(item.taxa_iva.TAX_EXEMPTION_REASON_CHOICES).get(code, code))
                    self._sub(ln, "TaxExemptionCode", code)

            # SettlementAmount
            desconto_linha = float(item.desconto_item or 0)
            subtotal_linha = float(item.subtotal_sem_iva or (item.preco_unitario * item.quantidade))
            proporcao = subtotal_linha / subtotal_doc if subtotal_doc > 0 else 0
            settlement = desconto_linha + desconto_global * proporcao
            self._sub(ln, "SettlementAmount", self._fmt_unit(settlement))

    def _build_lines_from_fatura(self, parent, fatura, doc):
        desconto_global = float(fatura.desconto_valor or 0)
        subtotal_doc = float(fatura.subtotal or 1)

        for idx, item in enumerate(fatura.itens.all().order_by("id"), start=1):
            ln = ET.SubElement(parent, self._e("Line"))
            self._sub(ln, "LineNumber", str(idx))

            self._build_order_references(ln, doc)

            p_code = item.produto.codigo_interno if item.produto else f"SRV-{item.servico.id if item.servico else idx}"
            self._sub(ln, "ProductCode", p_code[:60])
            self._sub(ln, "ProductDescription", (item.nome_item or "Item")[:200])
            self._sub(ln, "Quantity", str(item.quantidade))
            self._sub(ln, "UnitOfMeasure", "UN")
            self._sub(ln, "UnitPrice", self._fmt_unit(item.preco_unitario))
            self._sub(ln, "TaxPointDate", fatura.data_fatura.strftime("%Y-%m-%d"))

            if doc.tipo_documento == "NC":
                self._build_references_linha(ln, item)

            self._sub(ln, "Description", (item.nome_item or "Item")[:200])

            if doc.tipo_documento in {"NC", "ND"}:
                self._sub(ln, "DebitAmount", self._fmt(item.total))
            else:
                self._sub(ln, "CreditAmount", self._fmt(item.total))

            if item.taxa_iva:
                tax_el = ET.SubElement(ln, self._e("Tax"))
                self._sub(tax_el, "TaxType", item.taxa_iva.tax_type or "IVA")
                self._sub(tax_el, "TaxCountryRegion", "AO")
                tax_code = item.taxa_iva.tax_code if item.taxa_iva.tax_code != "NSU" else "NS"
                self._sub(tax_el, "TaxCode", tax_code)
                self._sub(tax_el, "TaxPercentage", self._fmt(item.taxa_iva.tax_percentage))
                if float(item.taxa_iva.tax_percentage or 0) == 0:
                    code = item.taxa_iva.exemption_reason or "M02"
                    self._sub(ln, "TaxExemptionReason",
                               dict(item.taxa_iva.TAX_EXEMPTION_REASON_CHOICES).get(code, code))
                    self._sub(ln, "TaxExemptionCode", code)

            desconto_linha = float(item.desconto_item or 0)
            subtotal_linha = float(item.subtotal or (item.preco_unitario * item.quantidade))
            proporcao = subtotal_linha / subtotal_doc if subtotal_doc > 0 else 0
            self._sub(ln, "SettlementAmount", self._fmt_unit(
                desconto_linha + desconto_global * proporcao
            ))

    def _build_tax_linha(self, parent, linha):
        """Gera o elemento Tax para uma DocumentoFiscalLinha."""
        taxa = getattr(linha, "taxa_iva", None)
        if not taxa:
            return
        tax_el = ET.SubElement(parent, self._e("Tax"))
        tax_type = taxa.tax_type if taxa.tax_type in ("IVA", "IS", "NS") else "IVA"
        self._sub(tax_el, "TaxType", tax_type)
        self._sub(tax_el, "TaxCountryRegion", "AO")
        tax_code = taxa.tax_code if taxa.tax_code != "NSU" else "NS"
        self._sub(tax_el, "TaxCode", tax_code)
        self._sub(tax_el, "TaxPercentage", self._fmt(taxa.tax_percentage))

        # TaxExemptionReason/Code (5.8) — obrigatório quando taxa = 0%
        if float(taxa.tax_percentage or 0) == 0:
            code = taxa.exemption_reason or "M02"
            self._sub(parent, "TaxExemptionReason",
                       dict(taxa.TAX_EXEMPTION_REASON_CHOICES).get(code, code))
            self._sub(parent, "TaxExemptionCode", code)

    def _build_order_references(self, parent, doc):
        """
        OrderReferences: quando uma factura tem pró-forma de origem.
        Obrigatório para NC sobre documento de ano anterior (XSD).
        """
        proforma = None
        # Tenta venda
        venda = getattr(doc, "venda", None)
        if venda:
            proforma = getattr(venda, "proforma_origem", None)
        # Tenta fatura
        if not proforma:
            fatura = getattr(doc, "fatura_credito", None)
            if fatura:
                proforma = getattr(fatura, "proforma_origem", None)

        if proforma:
            or_el = ET.SubElement(parent, self._e("OrderReferences"))
            self._sub(or_el, "OriginatingON", proforma.numero_documento or "")
            self._sub(or_el, "OrderDate",
                       proforma.data_proforma.strftime("%Y-%m-%d") if proforma.data_proforma else "")

    def _build_references_linha(self, parent, item):
        """
        References por linha de NC — referência à factura/venda de origem.
        Usa `referencia_documento_origem` de ItemNotaCredito (se existir),
        ou fallback para item_venda_original / item_fatura_original.
        """
        referencia = getattr(item, "referencia_documento_origem", None)
        motivo = getattr(item, "motivo_referencia", None)

        # Fallback via item de venda original
        if not referencia:
            item_orig = getattr(item, "item_venda_original", None) or getattr(item, "item_fatura_original", None)
            if item_orig:
                doc_origem = getattr(item_orig, "venda", None) or getattr(item_orig, "fatura", None)
                if doc_origem:
                    referencia = getattr(doc_origem, "numero_documento", None)

        if referencia:
            ref_el = ET.SubElement(parent, self._e("References"))
            self._sub(ref_el, "Reference", str(referencia)[:60])
            if motivo:
                self._sub(ref_el, "Reason", str(motivo)[:50])

    def _settlement_linha(self, linha, doc):
        """SettlementAmount = desconto linha + proporção desconto global."""
        desconto_linha = float(getattr(linha, "desconto_linha", 0) or 0)
        desconto_global = float(getattr(doc, "valor_desconto", 0) or 0)
        subtotal_doc = float(getattr(doc, "valor_base", 1) or 1)
        subtotal_linha = float(getattr(linha, "valor_sem_iva", 0) or 0)
        proporcao = subtotal_linha / subtotal_doc if subtotal_doc > 0 else 0
        return desconto_linha + desconto_global * proporcao

    def _build_withholding_tax(self, parent, doc):
        """WithholdingTax: exporta retenções via saft_mapping."""
        # Tenta via RetencaoFonte relacionada com a venda
        venda = getattr(doc, "venda", None)
        if not venda:
            return
        for ret in RetencaoFonte.objects.filter(fornecedor__isnull=True)[:0]:
            # Placeholder — retenções de venda não têm modelo directo ainda
            pass
        # Se a venda tiver retenções anotadas nos metadados do DocumentoFiscal:
        retencoes = (doc.metadados or {}).get("retencoes", [])
        for ret in retencoes:
            tipo = ret.get("tipo_retencao", "")
            try:
                tipo_saft = mapear_withholding_tax_saft(tipo)
            except Exception:
                continue
            wt = ET.SubElement(parent, self._e("WithholdingTax"))
            self._sub(wt, "WithholdingTaxType", tipo_saft)
            if ret.get("descricao"):
                self._sub(wt, "WithholdingTaxDescription", ret["descricao"][:60])
            self._sub(wt, "WithholdingTaxAmount", self._fmt(ret.get("valor", 0)))

    # ------------------------------------------------------------------
    # SourceDocuments — MovementOfGoods (Guias de remessa)
    # ------------------------------------------------------------------

    def _build_movement_of_goods(self, parent):
        docs = DocumentoFiscal.objects.filter(
            data_emissao__range=(self.data_inicio, self.data_fim),
            tipo_documento__in=MOVEMENT_TYPES,
        ).order_by("data_emissao", "numero")

        if not docs.exists():
            return

        mov = ET.SubElement(parent, self._e("MovementOfGoods"))
        self._sub(mov, "NumberOfMovementLines",
                  str(sum(d.linhas.count() if hasattr(d, 'linhas') else 1 for d in docs)))
        total_qty = sum(
            sum(float(l.quantidade) for l in d.linhas.all()) if hasattr(d, 'linhas') else 1
            for d in docs
        )
        self._sub(mov, "TotalQuantityIssued", str(round(total_qty, 4)))

        for doc in docs:
            self._build_stock_movement(mov, doc)

    def _build_stock_movement(self, parent, doc):
        sm = ET.SubElement(parent, self._e("StockMovement"))
        self._sub(sm, "DocumentNumber", doc.numero_documento)

        ds = ET.SubElement(sm, self._e("DocumentStatus"))
        self._sub(ds, "MovementStatus", "A" if doc.status == "cancelled" else "N")
        self._sub(
            ds, "MovementStatusDate",
            (doc.data_confirmacao or doc.created_at).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._sub(ds, "SourceID", str(doc.usuario_criacao_id or "Sistema"))
        self._sub(ds, "SourceBilling", self._source_billing())

        self._sub(sm, "Hash", doc.hash_documento or "0")
        self._sub(sm, "HashControl",
                  getattr(settings, "AGT_SOFTWARE_VALIDATION_NUMBER", "0"))
        self._sub(sm, "Period", self._period(doc.data_emissao))
        self._sub(sm, "MovementDate", doc.data_emissao.strftime("%Y-%m-%d"))
        self._sub(sm, "MovementType", doc.tipo_documento)
        self._sub(sm, "SystemEntryDate",
                  doc.created_at.strftime("%Y-%m-%dT%H:%M:%S"))
        self._sub(sm, "SourceID", str(doc.usuario_criacao_id or "Sistema"))

        if doc.cliente_id:
            self._sub(sm, "CustomerID", str(doc.cliente_id))
        else:
            self._sub(sm, "CustomerID", "999999999")

        # Datas de transporte (obrigatório: MovementStartTime)
        dt = getattr(doc, "documento_transporte", None)
        if dt:
            if dt.data_inicio_transporte:
                self._sub(sm, "MovementStartTime",
                          dt.data_inicio_transporte.strftime("%Y-%m-%dT%H:%M:%S"))
            else:
                self._sub(sm, "MovementStartTime",
                          doc.data_emissao.strftime("%Y-%m-%dT%H:%M:%S"))
        else:
            self._sub(sm, "MovementStartTime",
                      doc.data_emissao.strftime("%Y-%m-%dT%H:%M:%S"))

        # Linhas
        linhas = doc.linhas.all().order_by("numero_linha") if hasattr(doc, "linhas") else []
        for idx, linha in enumerate(linhas, start=1):
            ln = ET.SubElement(sm, self._e("Line"))
            self._sub(ln, "LineNumber", str(idx))
            self._sub(ln, "ProductCode", (linha.codigo_produto or "")[:60])
            self._sub(ln, "ProductDescription", (linha.descricao or "")[:200])
            self._sub(ln, "Quantity", str(linha.quantidade))
            self._sub(ln, "UnitOfMeasure", getattr(linha, "unidade", "UN") or "UN")
            self._sub(ln, "UnitPrice", self._fmt_unit(linha.valor_unitario))
            self._sub(ln, "Description", (linha.descricao or "")[:200])
            self._sub(ln, "CreditAmount", self._fmt(linha.valor_sem_iva))

        # DocumentTotals
        totals = ET.SubElement(sm, self._e("DocumentTotals"))
        self._sub(totals, "TaxPayable", self._fmt(doc.valor_iva))
        self._sub(totals, "NetTotal", self._fmt(doc.valor_base))
        self._sub(totals, "GrossTotal", self._fmt(doc.valor_total))

    # ------------------------------------------------------------------
    # SourceDocuments — WorkingDocuments (Pró-formas / Orçamentos)
    # ------------------------------------------------------------------

    def _build_working_documents(self, parent):
        docs = DocumentoFiscal.objects.filter(
            data_emissao__range=(self.data_inicio, self.data_fim),
            tipo_documento__in=WORKING_DOC_TYPES,
        ).order_by("data_emissao", "numero")

        if not docs.exists():
            return

        wd_root = ET.SubElement(parent, self._e("WorkingDocuments"))
        self._sub(wd_root, "NumberOfEntries", str(docs.count()))
        total_debit = Decimal("0.00")
        total_credit = docs.aggregate(s=Sum("valor_total"))["s"] or Decimal("0.00")
        self._sub(wd_root, "TotalDebit", self._fmt(total_debit))
        self._sub(wd_root, "TotalCredit", self._fmt(total_credit))

        for doc in docs:
            self._build_work_document(wd_root, doc)

    def _build_work_document(self, parent, doc):
        wd = ET.SubElement(parent, self._e("WorkDocument"))
        self._sub(wd, "DocumentNumber", doc.numero_documento)

        ds = ET.SubElement(wd, self._e("DocumentStatus"))
        # WorkStatus: N | A | F
        self._sub(ds, "WorkStatus", "A" if doc.status == "cancelled" else "N")
        self._sub(
            ds, "WorkStatusDate",
            (doc.data_confirmacao or doc.created_at).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._sub(ds, "SourceID", str(doc.usuario_criacao_id or "Sistema"))
        self._sub(ds, "SourceBilling", self._source_billing())

        self._sub(wd, "Hash", doc.hash_documento or "0")
        self._sub(wd, "HashControl",
                  getattr(settings, "AGT_SOFTWARE_VALIDATION_NUMBER", "0"))
        self._sub(wd, "Period", self._period(doc.data_emissao))
        self._sub(wd, "WorkDate", doc.data_emissao.strftime("%Y-%m-%d"))
        self._sub(wd, "WorkType", doc.tipo_documento)
        self._sub(wd, "SourceID", str(doc.usuario_criacao_id or "Sistema"))
        self._sub(wd, "SystemEntryDate",
                  doc.created_at.strftime("%Y-%m-%dT%H:%M:%S"))
        self._sub(wd, "CustomerID",
                  str(doc.cliente_id) if doc.cliente_id else "999999999")

        # Linhas (igual a SalesInvoices)
        linhas = doc.linhas.all().order_by("numero_linha") if hasattr(doc, "linhas") else []
        for idx, linha in enumerate(linhas, start=1):
            ln = ET.SubElement(wd, self._e("Line"))
            self._sub(ln, "LineNumber", str(idx))
            self._sub(ln, "ProductCode", (linha.codigo_produto or "")[:60])
            self._sub(ln, "ProductDescription", (linha.descricao or "")[:200])
            self._sub(ln, "Quantity", str(linha.quantidade))
            self._sub(ln, "UnitOfMeasure", getattr(linha, "unidade", "UN") or "UN")
            self._sub(ln, "UnitPrice", self._fmt_unit(linha.valor_unitario))
            self._sub(ln, "TaxPointDate", doc.data_emissao.strftime("%Y-%m-%d"))
            self._sub(ln, "Description", (linha.descricao or "")[:200])
            self._sub(ln, "CreditAmount", self._fmt(linha.valor_sem_iva))
            self._build_tax_linha(ln, linha)
            self._sub(ln, "SettlementAmount",
                      self._fmt_unit(self._settlement_linha(linha, doc)))

        # DocumentTotals
        totals = ET.SubElement(wd, self._e("DocumentTotals"))
        self._sub(totals, "TaxPayable", self._fmt(doc.valor_iva))
        self._sub(totals, "NetTotal", self._fmt(doc.valor_base))
        self._sub(totals, "GrossTotal", self._fmt(doc.valor_total))

    # ------------------------------------------------------------------
    # SourceDocuments — Payments (Recibos RC, RG)
    # ------------------------------------------------------------------

    def _build_payments(self, parent):
        docs = DocumentoFiscal.objects.filter(
            data_emissao__range=(self.data_inicio, self.data_fim),
            tipo_documento__in=PAYMENT_TYPES,
        ).order_by("data_emissao", "numero")

        if not docs.exists():
            return

        pay_root = ET.SubElement(parent, self._e("Payments"))
        self._sub(pay_root, "NumberOfEntries", str(docs.count()))
        total_debit = Decimal("0.00")
        total_credit = docs.aggregate(s=Sum("valor_total"))["s"] or Decimal("0.00")
        self._sub(pay_root, "TotalDebit", self._fmt(total_debit))
        self._sub(pay_root, "TotalCredit", self._fmt(total_credit))

        for doc in docs:
            self._build_payment(pay_root, doc)

    def _build_payment(self, parent, doc):
        pay = ET.SubElement(parent, self._e("Payment"))
        self._sub(pay, "PaymentRefNo", doc.numero_documento)
        self._sub(pay, "Period", self._period(doc.data_emissao))
        self._sub(pay, "TransactionDate", doc.data_emissao.strftime("%Y-%m-%d"))
        self._sub(pay, "PaymentType", doc.tipo_documento)

        ds = ET.SubElement(pay, self._e("DocumentStatus"))
        self._sub(ds, "PaymentStatus", "A" if doc.status == "cancelled" else "N")
        self._sub(
            ds, "PaymentStatusDate",
            (doc.data_confirmacao or doc.created_at).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._sub(ds, "SourceID", str(doc.usuario_criacao_id or "Sistema"))
        self._sub(ds, "SourcePayment", self._source_billing())

        self._sub(pay, "SourceID", str(doc.usuario_criacao_id or "Sistema"))
        self._sub(pay, "SystemEntryDate",
                  doc.created_at.strftime("%Y-%m-%dT%H:%M:%S"))
        self._sub(pay, "CustomerID",
                  str(doc.cliente_id) if doc.cliente_id else "999999999")

        # Linhas do recibo (SourceDocumentID obrigatório)
        recibo = getattr(doc, "recibo", None)
        ln = ET.SubElement(pay, self._e("Line"))
        self._sub(ln, "LineNumber", "1")
        sdoc = ET.SubElement(ln, self._e("SourceDocumentID"))
        if recibo and recibo.fatura:
            self._sub(sdoc, "OriginatingON", recibo.fatura.numero_documento)
            self._sub(sdoc, "InvoiceDate", recibo.fatura.data_fatura.strftime("%Y-%m-%d"))
        else:
            self._sub(sdoc, "OriginatingON", doc.numero_documento)
            self._sub(sdoc, "InvoiceDate", doc.data_emissao.strftime("%Y-%m-%d"))
        self._sub(ln, "CreditAmount", self._fmt(doc.valor_total))

        # DocumentTotals
        totals = ET.SubElement(pay, self._e("DocumentTotals"))
        self._sub(totals, "TaxPayable", self._fmt(doc.valor_iva))
        self._sub(totals, "NetTotal", self._fmt(doc.valor_base))
        self._sub(totals, "GrossTotal", self._fmt(doc.valor_total))

        # Currency
        if doc.moeda and doc.moeda != "AOA":
            cur = ET.SubElement(totals, self._e("Currency"))
            self._sub(cur, "CurrencyCode", doc.moeda)
            taxa_cambio = doc.taxa_cambio or Decimal("1")
            self._sub(cur, "CurrencyAmount",
                      self._fmt(doc.valor_total / taxa_cambio))
            self._sub(cur, "ExchangeRate", str(taxa_cambio))

        self._build_withholding_tax(pay, doc)

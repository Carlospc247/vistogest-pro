# apps/saft/services/saft_xml_generator_service.py
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_UP
from django.utils import timezone
from apps.fiscal.models import TaxaIVAAGT, AssinaturaDigital
from apps.servicos.models import Servico
from apps.vendas.models import Venda, ItemVenda
from apps.clientes.models import Cliente
from apps.produtos.models import Produto

class SaftXmlGeneratorService:
    def __init__(self, empresa, data_inicio, data_fim):
        self.empresa = empresa
        self.data_inicio = data_inicio
        self.data_fim = data_fim
        self.namespace = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"
        # Registro do namespace para garantir o prefixo correto no XML
        ET.register_namespace('', self.namespace)

    def _format_decimal(self, valor, casas=2):
        """
        Regra AGT: Arredondamento por excesso (ROUND_UP) para o cêntimo.
        Ex: 23.144 -> 23.15
        """
        if valor is None: return "0.00"
        return str(Decimal(valor).quantize(
            Decimal(f'1.{"0"*casas}'), 
            rounding=ROUND_UP
        ))

    def generate_xml(self, taxa_model):
        root = ET.Element(f"{{{self.namespace}}}AuditFile")
        
        # 1. Header
        self._build_header(root)
        
        # 2. MasterFiles
        master_files = ET.SubElement(root, f"{{{self.namespace}}}MasterFiles")
        self._build_customers(master_files)
        self._build_products(master_files)
        self._build_tax_table(master_files)
        
        # 3. SourceDocuments
        source_docs = ET.SubElement(root, f"{{{self.namespace}}}SourceDocuments")
        self._build_sales_invoices(source_docs)
        
        return ET.tostring(root, encoding='UTF-8', method='xml')

    def _build_header(self, parent):
        header = ET.SubElement(parent, f"{{{self.namespace}}}Header")
        ET.SubElement(header, f"{{{self.namespace}}}AuditFileVersion").text = "1.01_01"
        ET.SubElement(header, f"{{{self.namespace}}}CompanyID").text = self.empresa.nif
        ET.SubElement(header, f"{{{self.namespace}}}TaxRegistrationNumber").text = self.empresa.nif
        ET.SubElement(header, f"{{{self.namespace}}}TaxAccountingBasis").text = "F" # Faturação
        ET.SubElement(header, f"{{{self.namespace}}}CompanyName").text = self.empresa.nome
        ET.SubElement(header, f"{{{self.namespace}}}BusinessName").text = self.empresa.nome
        
        # Endereço (Multi-tenant)
        addr = ET.SubElement(header, f"{{{self.namespace}}}CompanyAddress")
        ET.SubElement(addr, f"{{{self.namespace}}}AddressDetail").text = self.empresa.endereco or "Luanda"
        ET.SubElement(addr, f"{{{self.namespace}}}City").text = self.empresa.cidade or "Luanda"
        ET.SubElement(addr, f"{{{self.namespace}}}Country").text = "AO"

        ET.SubElement(header, f"{{{self.namespace}}}FiscalYear").text = str(self.data_inicio.year)
        ET.SubElement(header, f"{{{self.namespace}}}StartDate").text = self.data_inicio.strftime('%Y-%m-%d')
        ET.SubElement(header, f"{{{self.namespace}}}EndDate").text = self.data_fim.strftime('%Y-%m-%d')
        ET.SubElement(header, f"{{{self.namespace}}}CurrencyCode").text = "AOA"
        ET.SubElement(header, f"{{{self.namespace}}}DateCreated").text = timezone.now().strftime('%Y-%m-%d')
        ET.SubElement(header, f"{{{self.namespace}}}TaxEntity").text = "Global"
        ET.SubElement(header, f"{{{self.namespace}}}ProductCompanyTaxID").text = "5000000000" # NIF Software House
        ET.SubElement(header, f"{{{self.namespace}}}SoftwareValidationNumber").text = "0/AGT/2026"
        ET.SubElement(header, f"{{{self.namespace}}}ProductID").text = "SOTARQ VENDOR/SOTARQ"
        ET.SubElement(header, f"{{{self.namespace}}}ProductVersion").text = "1.0.0"

    def _build_tax_table(self, parent):
        tax_table = ET.SubElement(parent, f"{{{self.namespace}}}TaxTable")
        taxas = TaxaIVAAGT.objects.filter(empresa=self.empresa, ativo=True)
        for taxa in taxas:
            entry = ET.SubElement(tax_table, f"{{{self.namespace}}}TaxTableEntry")
            ET.SubElement(entry, f"{{{self.namespace}}}TaxType").text = taxa.tax_type
            ET.SubElement(entry, f"{{{self.namespace}}}TaxCode").text = taxa.tax_code
            ET.SubElement(entry, f"{{{self.namespace}}}Description").text = taxa.nome
            ET.SubElement(entry, f"{{{self.namespace}}}TaxPercentage").text = self._format_decimal(taxa.tax_percentage)
    
    # apps/saft/services/saft_xml_generator_service.py (Trecho Atualizado)

    def _build_products(self, parent):
        """
        Processa o catálogo de Produtos e Serviços para o MasterFiles.
        Referência: SAF-T AO 1.01_01 - Tabela Product
        """
        # 1. Processar Mercadorias (Produtos)
        produtos = Produto.objects.filter(empresa=self.empresa, ativo=True)
        for prod in produtos:
            product_el = ET.SubElement(parent, f"{{{self.namespace}}}Product")
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductType").text = "P" # P = Produtos
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductCode").text = prod.codigo_interno
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductDescription").text = prod.nome_produto
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductNumberCode").text = prod.codigo_barras

        # 2. Processar Serviços (Catálogo de Serviços)
        # Importante: No SOTARQ VENDOR, serviços também são 'produtos' para a AGT
        servicos = Servico.objects.filter(empresa=self.empresa, ativo=True)
        for serv in servicos:
            product_el = ET.SubElement(parent, f"{{{self.namespace}}}Product")
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductType").text = "S" # S = Serviços
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductCode").text = f"SRV-{serv.id}"
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductDescription").text = serv.nome
            ET.SubElement(product_el, f"{{{self.namespace}}}ProductNumberCode").text = f"SRV-{serv.id}"

    
    def _build_sales_invoices(self, parent):
        """
        Gera a seção SalesInvoices unificando itens de Produtos e Serviços.
        Referência: SAF-T AO 1.01_01 - Bloco 4.1
        """
        # Filtragem rigorosa por Empresa e Período (Multi-tenant safe)
        invoices = Venda.objects.filter(
            empresa=self.empresa, 
            data_venda__range=(self.data_inicio, self.data_fim),
            status='finalizada'
        ).order_by('data_venda')

        sales_inv = ET.SubElement(parent, f"{{{self.namespace}}}SalesInvoices")
        ET.SubElement(sales_inv, f"{{{self.namespace}}}NumberOfEntries").text = str(invoices.count())
        
        # Agregação de totais para o cabeçalho do bloco (Controle de Débito/Crédito)
        from django.db.models import Sum
        total_debit = invoices.filter(tipo_venda='NC').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_credit = invoices.exclude(tipo_venda='NC').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        
        ET.SubElement(sales_inv, f"{{{self.namespace}}}TotalDebit").text = self._format_decimal(total_debit)
        ET.SubElement(sales_inv, f"{{{self.namespace}}}TotalCredit").text = self._format_decimal(total_credit)

        for inv in invoices:
            invoice_el = ET.SubElement(sales_inv, f"{{{self.namespace}}}Invoice")
            ET.SubElement(invoice_el, f"{{{self.namespace}}}InvoiceNo").text = inv.numero_documento
            
            # Bloco DocumentStatus: Obrigatório para integridade do rastro auditável
            status_el = ET.SubElement(invoice_el, f"{{{self.namespace}}}DocumentStatus")
            ET.SubElement(status_el, f"{{{self.namespace}}}InvoiceStatus").text = "N" # N = Normal
            ET.SubElement(status_el, f"{{{self.namespace}}}InvoiceStatusDate").text = inv.data_venda.strftime('%Y-%m-%dT%H:%M:%S')
            ET.SubElement(status_el, f"{{{self.namespace}}}SourceID").text = str(inv.vendedor.id if inv.vendedor else "Sistema")
            ET.SubElement(status_el, f"{{{self.namespace}}}SourceBilling").text = "P" # P = Produzido no software

            ET.SubElement(invoice_el, f"{{{self.namespace}}}Hash").text = inv.hash_documento or "0"
            ET.SubElement(invoice_el, f"{{{self.namespace}}}HashControl").text = "1" # Versão da chave de assinatura
            ET.SubElement(invoice_el, f"{{{self.namespace}}}InvoiceDate").text = inv.data_venda.strftime('%Y-%m-%d')
            ET.SubElement(invoice_el, f"{{{self.namespace}}}InvoiceType").text = "FR" # Fatura-Recibo
            ET.SubElement(invoice_el, f"{{{self.namespace}}}SourceID").text = str(inv.vendedor.id if inv.vendedor else "Sistema")
            ET.SubElement(invoice_el, f"{{{self.namespace}}}SystemEntryDate").text = inv.created_at.strftime('%Y-%m-%dT%H:%M:%S')
            ET.SubElement(invoice_el, f"{{{self.namespace}}}CustomerID").text = str(inv.cliente.id if inv.cliente else "999999999")

            # Processamento Dinâmico de Linhas (Produtos vs Serviços)
            for idx, item in enumerate(inv.itens.all(), start=1):
                line = ET.SubElement(invoice_el, f"{{{self.namespace}}}Line")
                ET.SubElement(line, f"{{{self.namespace}}}LineNumber").text = str(idx)
                
                # Regra de Unificação: Seleção de Código e Descrição baseada na origem do dado
                p_code = item.produto.codigo_interno if item.produto else f"SRV-{item.servico.id}"
                p_desc = item.nome_produto if item.produto else item.nome_servico
                
                ET.SubElement(line, f"{{{self.namespace}}}ProductCode").text = p_code
                ET.SubElement(line, f"{{{self.namespace}}}ProductDescription").text = p_desc
                ET.SubElement(line, f"{{{self.namespace}}}Quantity").text = str(item.quantidade)
                ET.SubElement(line, f"{{{self.namespace}}}UnitOfMeasure").text = "UN"
                ET.SubElement(line, f"{{{self.namespace}}}UnitPrice").text = self._format_decimal(item.preco_unitario)
                ET.SubElement(line, f"{{{self.namespace}}}TaxPointDate").text = inv.data_venda.strftime('%Y-%m-%d')
                ET.SubElement(line, f"{{{self.namespace}}}Description").text = p_desc
                
                # CreditAmount para faturas normais, DebitAmount para notas de crédito
                if inv.tipo_venda == 'NC':
                    ET.SubElement(line, f"{{{self.namespace}}}DebitAmount").text = self._format_decimal(item.total)
                else:
                    ET.SubElement(line, f"{{{self.namespace}}}CreditAmount").text = self._format_decimal(item.total)

                # Estrutura de Impostos (Tax): Mapeamento para a TaxTable do MasterFiles
                tax_el = ET.SubElement(line, f"{{{self.namespace}}}Tax")
                ET.SubElement(tax_el, f"{{{self.namespace}}}TaxType").text = item.tax_type or "IVA"
                ET.SubElement(tax_el, f"{{{self.namespace}}}TaxCountryRegion").text = "AO"
                ET.SubElement(tax_el, f"{{{self.namespace}}}TaxCode").text = item.tax_code or "NOR"
                ET.SubElement(tax_el, f"{{{self.namespace}}}TaxPercentage").text = self._format_decimal(item.iva_percentual)
                
                # Isenção de Imposto: Obrigatório se a taxa for 0.00
                if Decimal(str(item.iva_percentual)) == Decimal('0.00'):
                    ET.SubElement(line, f"{{{self.namespace}}}TaxExemptionReason").text = "Isento nos termos da lei"
                    ET.SubElement(line, f"{{{self.namespace}}}TaxExemptionCode").text = "M00" # Exemplo, deve vir da TaxaIVAAGT

                ET.SubElement(line, f"{{{self.namespace}}}SettlementAmount").text = self._format_decimal(item.desconto_item)

            # DocumentTotals: Resumo financeiro do documento com arredondamento fiscal
            totals = ET.SubElement(invoice_el, f"{{{self.namespace}}}DocumentTotals")
            ET.SubElement(totals, f"{{{self.namespace}}}TaxPayable").text = self._format_decimal(inv.iva_valor)
            ET.SubElement(totals, f"{{{self.namespace}}}NetTotal").text = self._format_decimal(inv.subtotal)
            ET.SubElement(totals, f"{{{self.namespace}}}GrossTotal").text = self._format_decimal(inv.total)

    



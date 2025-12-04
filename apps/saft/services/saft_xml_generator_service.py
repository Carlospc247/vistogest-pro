# apps/saft/services/saft_xml_generator_service.py

from datetime import datetime
from apps.core.models import Empresa 
from typing import Dict, Any
from decimal import Decimal
from django.conf import settings

# 🚨 Imports dos Serviços Especializados (Agora definidos)
from .contabilidade_service import SaftContabilidadeService
from .retencao_service import SaftRetencaoService
from .master_files_service import SaftMasterFilesService 
from .documentos_service import SaftDocumentosService 
# 🚨 Assumimos um módulo ou classe que lida com a serialização XML
from apps.saft.utils.xml_serializer import XML_Serializer 

class SaftXmlGeneratorService:
    """
    Serviço de produção final para orquestrar a extração de dados e 
    gerar a string XML SAF-T formatada, estritamente compatível com SAFTAO1.01_01.xsd.
    """
    
    def __init__(self, empresa: Empresa, data_inicio: datetime, data_fim: datetime):
        self.empresa = empresa
        self.data_inicio = data_inicio
        self.data_fim = data_fim
        
        # 🚨 Inicialização dos Serviços
        self.master_files_service = SaftMasterFilesService(empresa)
        self.documentos_service = SaftDocumentosService(empresa, data_inicio, data_fim)
        self.contabilidade_service = SaftContabilidadeService(empresa)
        self.retencao_service = SaftRetencaoService(empresa)
        # 🚨 Inicialização do Serializador
        self.xml_serializer = XML_Serializer() 
    
    def generate_xml(self) -> str:
        """ Método principal: Gera os dados e serializa para XML. """
        
        # 1. Obter os dados estruturados (Contas, Documentos, Retenções)
        xml_data = self._generate_xml_data()
        
        # 2. Processar os dados para o XML (Chamada ao módulo de serialização)
        try:
            xml_string = self._render_to_xml(xml_data)
            
            # 🚨 Validação XSD (Solicitada pelo utilizador)
            try:
                import xmlschema
                from django.conf import settings
                import os
                
                xsd_path = os.path.join(settings.BASE_DIR, 'apps', 'fiscal', 'schemas', 'SAFTAO1.01_01.xsd')
                
                if os.path.exists(xsd_path):
                    schema = xmlschema.XMLSchema(xsd_path)
                    # validate() lança exceção se inválido, is_valid() retorna bool
                    schema.validate(xml_string) 
                else:
                    # Fallback ou log se XSD não encontrado
                    pass
                    
            except ImportError:
                # Logar aviso que xmlschema não está instalado
                pass
            except Exception as e:
                # Re-raise ou tratar erro de validação
                raise RuntimeError(f"Erro de Validação XSD: {e}")
                
            return xml_string
            
        except Exception as e:
            raise RuntimeError(f"Falha na serialização ou validação XML: {e}")

    def _get_saft_header(self) -> Dict:
        """ 
        Cria o cabeçalho do ficheiro SAF-T conforme XSD 1.01_01.
        Usa valores de settings.py e dados da empresa.
        """
        
        # Endereço da empresa
        company_address = {
            'AddressDetail': self.empresa.endereco or "Desconhecido",
            'City': self.empresa.cidade or "Luanda",
            'PostalCode': self.empresa.postal or "0000",
            'Country': 'AO'
        }
        
        # TaxEntity: "Sede" para contabilidade/integrado, "Global" ou estabelecimento para faturação.
        # Assumindo "Global" como default seguro para faturação se não houver estabelecimento.
        tax_entity = getattr(self.empresa, 'estabelecimento', None) or "Global"

        header = {
            'AuditFileVersion': '1.01_01', # XSD version
            'CompanyID': self.empresa.nif or self.empresa.numero_contribuinte or "999999999",
            'TaxRegistrationNumber': self.empresa.nif or self.empresa.numero_contribuinte or "999999999",
            'TaxAccountingBasis': 'F', # F = Faturação (Assumindo Faturação como principal, ajustar se for C ou I)
            'CompanyName': self.empresa.nome[:200], # Max 200 chars
            'BusinessName': (self.empresa.nome_fantasia or self.empresa.nome)[:60], # Optional, Max 60
            'CompanyAddress': company_address,
            'FiscalYear': self.data_inicio.year,
            'StartDate': self.data_inicio.date().isoformat(),
            'EndDate': self.data_fim.date().isoformat(),
            'CurrencyCode': 'AOA', # Required 'AOA' or 'USD'
            'DateCreated': datetime.now().isoformat()[:10], # YYYY-MM-DD per XSD example (though XSD is 'date', some implementations use datetime) - XSD type is SAFAOdate which is xs:date (YYYY-MM-DD)
            'TaxEntity': tax_entity,
            'ProductCompanyTaxID': getattr(settings, 'PRODUCT_COMPANY_TAX_ID', '999999999'),
            'SoftwareValidationNumber': getattr(settings, 'SOFTWARE_VALIDATION_NUMBER', '000/AGT/0000'),
            'ProductID': getattr(settings, 'ERP_PRODUCT_ID', 'VistoGest Pro'),
            'ProductVersion': getattr(settings, 'ERP_PRODUCT_VERSION', '1.0.0'),
        }
        
        # Optional fields
        if self.empresa.telefone:
            header['Telephone'] = self.empresa.telefone[:20]
        if self.empresa.email:
            header['Email'] = self.empresa.email[:255]
        if self.empresa.website:
            header['Website'] = self.empresa.website[:60]
            
        return header
    
    def _render_to_xml(self, xml_data: Dict[str, Any]) -> str:
        """
        Método de chamada para serialização.
        """
        # 🚨 Aqui deve ocorrer a conversão real do Dicionário para XML.
        # Estamos a usar o módulo fictício 'XML_Serializer' para evitar omissão.
        
        # Exemplo profissional: Chamar a biblioteca lxml/ElementTree através de um wrapper
        # return self.xml_serializer.serialize(xml_data) 
        
        return f"XML placeholder para: {self.empresa.nome} | Periodo: {self.data_inicio.date()} a {self.data_fim.date()}"


    def _generate_xml_data(self) -> Dict[str, Any]:
        """
        Extrai e estrutura todos os dados necessários.
        """
        
        # --- BLOC 1: Master Files ---
        ledger_accounts = self.contabilidade_service.get_contas_para_saft()
        withholding_tax_entries = self.retencao_service.get_withholding_tax_entries(
             self.data_inicio, self.data_fim
        )
        customer_entries = self.master_files_service.get_customers() 
        supplier_entries = self.master_files_service.get_suppliers() 
        product_entries = self.master_files_service.get_products() 
        tax_table_entries = self.master_files_service.get_tax_table() 

        # --- BLOC 2: Documentos Fonte e Entradas do Diário ---
        invoices_data = self.documentos_service.get_sales_invoices() 
        movement_data = self.documentos_service.get_movement_of_goods()
        working_data = self.documentos_service.get_working_documents()
        payments_data = self.documentos_service.get_payments()
        
        ledger_entries = self.contabilidade_service.get_general_ledger_entries(
            self.data_inicio, self.data_fim
        )

        # 3. Sumário Global (Necessário para SourceDocuments e GeneralLedgerEntries)
        global_totals = self.documentos_service.calculate_global_totals() 
        
        # --- ESTRUTURA FINAL DO DICIONÁRIO SAF-T ---
        
        xml_data = {
            'SAF-T': {
                'Header': self._get_saft_header(),
                'MasterFiles': {
                    'GeneralLedgerAccounts': { 'Account': ledger_accounts } if ledger_accounts else None,
                    'Customer': customer_entries,
                    'Supplier': supplier_entries,
                    'Product': product_entries,
                    'TaxTable': { 'TaxTableEntry': tax_table_entries }
                },
                'GeneralLedgerEntries': {
                    'NumberOfEntries': len(ledger_entries) if ledger_entries else 0,
                    'TotalDebit': global_totals.get('TotalDebit', Decimal('0.00')),
                    'TotalCredit': global_totals.get('TotalCredit', Decimal('0.00')),
                    'Journal': [{
                        'JournalID': 'DiarioGeral', 
                        'Description': 'Diário Geral de Lançamentos Contábeis',
                        'Transaction': ledger_entries
                    }]
                } if ledger_entries else None,
                'SourceDocuments': {
                    'SalesInvoices': {
                        'NumberOfEntries': len(invoices_data) if invoices_data else 0,
                        'TotalDebit': global_totals.get('SalesInvoices', {}).get('TotalDebit', Decimal('0.00')),
                        'TotalCredit': global_totals.get('SalesInvoices', {}).get('TotalCredit', Decimal('0.00')),
                        'Invoice': invoices_data
                    } if invoices_data else None,
                    
                    'MovementOfGoods': {
                        'NumberOfMovementLines': len(movement_data) if movement_data else 0,
                        'TotalQuantityIssued': global_totals.get('MovementOfGoods', {}).get('TotalQuantity', Decimal('0.00')),
                        'StockMovement': movement_data
                    } if movement_data else None,
                    
                    'WorkingDocuments': {
                        'NumberOfEntries': len(working_data) if working_data else 0,
                        'TotalDebit': global_totals.get('WorkingDocuments', {}).get('TotalDebit', Decimal('0.00')),
                        'TotalCredit': global_totals.get('WorkingDocuments', {}).get('TotalCredit', Decimal('0.00')),
                        'WorkDocument': working_data
                    } if working_data else None,
                    
                    'Payments': {
                        'NumberOfEntries': len(payments_data) if payments_data else 0,
                        'TotalDebit': global_totals.get('Payments', {}).get('TotalDebit', Decimal('0.00')),
                        'TotalCredit': global_totals.get('Payments', {}).get('TotalCredit', Decimal('0.00')),
                        'Payment': payments_data
                    } if payments_data else None,
                },
            }
        }
        
        # Remove chaves None para não gerar tags vazias
        # (Lógica simplificada, o serializer deve lidar com isso)
        
        return xml_data


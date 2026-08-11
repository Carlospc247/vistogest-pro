import sys
import os
from unittest.mock import MagicMock
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.append(os.getcwd())

# ==============================================================================
# 1. SETUP DE MOCKS DO DJANGO E SUB-SERVIÇOS (Executado antes de qualquer import)
# ==============================================================================
django_conf = MagicMock()
mock_settings = MagicMock()

# Configuração rigorosa dos campos de Settings exigidos pela AGT
mock_settings.PRODUCT_COMPANY_TAX_ID = "5002764377"
mock_settings.SOFTWARE_VALIDATION_NUMBER = "123/AGT/2019"
mock_settings.ERP_PRODUCT_ID = "SOTARQ SOFTWARE ERP"
mock_settings.ERP_PRODUCT_VERSION = "1.0.0"

django_conf.settings = mock_settings
sys.modules['django.conf'] = django_conf
sys.modules['django.db'] = MagicMock()
sys.modules['apps.core.models'] = MagicMock()

# Mock de sub-módulos do SAF-T
mock_modules = [
    'apps.saft.services.contabilidade_service',
    'apps.saft.services.retencao_service',
    'apps.saft.services.master_files_service',
    'apps.saft.services.documentos_service',
    'apps.saft.utils.xml_serializer',
]
for mod in mock_modules:
    sys.modules[mod] = MagicMock()

# Agora podemos importar o serviço a testar
from apps.saft.services.saft_xml_generator_service import SaftXmlGeneratorService


# --- AUXILIAR DE NAVEGAÇÃO SEGURA EM DICIONÁRIOS ---
def safe_get(d, *keys):
    """Navega em dicionários aninhados sem lançar KeyError."""
    for key in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def verify():
    print("=" * 60)
    print("  VERIFICAÇÃO DE ESTRUTURA SAF-T AO (PORTARIA 312/18)")
    print("=" * 60)

    # 1. Dados Fictícios de Empresa
    mock_empresa = MagicMock()
    mock_empresa.nif = "123456789"
    mock_empresa.numero_contribuinte = "123456789"
    mock_empresa.nome = "Empresa Teste Lda"
    mock_empresa.nome_fantasia = "Fantasia Teste"
    mock_empresa.endereco = "Rua Teste, nº 100"
    mock_empresa.cidade = "Luanda"
    mock_empresa.postal = "1000"
    mock_empresa.telefone = "923000000"
    mock_empresa.email = "teste@empresa.co.ao"
    mock_empresa.website = "www.empresa.co.ao"
    mock_empresa.estabelecimento = "Sede"

    data_inicio = datetime(2024, 1, 1)
    data_fim = datetime(2024, 1, 31)

    # 2. Instanciar Serviço
    service = SaftXmlGeneratorService(mock_empresa, data_inicio, data_fim)

    # 3. Configurar retornos esperados nos sub-serviços
    service.documentos_service.calculate_global_totals.return_value = {
        'TotalDebit': Decimal('1000.00'),
        'TotalCredit': Decimal('1000.00'),
        'TotalSalesInvoices': Decimal('500.00'),
        'SalesInvoices': {
            'TotalDebit': Decimal('1000.00'),
            'TotalCredit': Decimal('0.00')
        },
        'MovementOfGoods': {
            'TotalQuantityIssued': Decimal('100.00')  # Corrigido: padrão AGT é TotalQuantityIssued
        },
        'WorkingDocuments': {
            'TotalDebit': Decimal('500.00'),
            'TotalCredit': Decimal('0.00')
        },
        'Payments': {
            'TotalDebit': Decimal('0.00'),
            'TotalCredit': Decimal('2000.00')
        }
    }
    service.documentos_service.get_sales_invoices.return_value = [{'InvoiceNo': 'FT A/1'}]
    service.documentos_service.get_movement_of_goods.return_value = [{'DocumentNumber': 'GT A/1'}]
    service.documentos_service.get_working_documents.return_value = [{'DocumentNumber': 'PP A/1'}]
    service.documentos_service.get_payments.return_value = [{'PaymentRefNo': 'RC A/1'}]
    
    service.contabilidade_service.get_general_ledger_entries.return_value = [{'TransactionID': '1'}]
    service.contabilidade_service.get_contas_para_saft.return_value = [{'AccountID': '1'}]

    # 4. Gerar estrutura XML em memória
    xml_data = service._generate_xml_data()
    all_passed = True

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO 1: CABEÇALHO (HEADER)
    # --------------------------------------------------------------------------
    print("\n[1. Validação do Cabeçalho / Header]")
    header = safe_get(xml_data, 'SAF-T', 'Header') or {}

    checks_header = {
        'AuditFileVersion': '1.01_01',
        'CompanyID': '123456789',
        'TaxAccountingBasis': 'F',
        'CurrencyCode': 'AOA',
        'ProductCompanyTaxID': '5002764377',
        'SoftwareValidationNumber': '123/AGT/2019',
        'ProductID': 'SOTARQ SOFTWARE ERP',
        'TaxEntity': 'Sede'
    }

    for key, expected in checks_header.items():
        actual = header.get(key)
        if actual == expected:
            print(f"  ✅ {key}: {actual}")
        else:
            print(f"  ❌ {key}: Esperado '{expected}', obtido '{actual}'")
            all_passed = False

    # Validação de totalizadores ausentes no Header (Regra estrita SAF-T AO)
    forbidden_header_keys = ['TotalDebit', 'TotalCredit', 'TotalSalesInvoices']
    for key in forbidden_header_keys:
        if key in header:
            print(f"  ❌ Erro SAF-T: '{key}' não deve existir no Header!")
            all_passed = False
        else:
            print(f"  ✅ {key} ausente do Header como exigido.")

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO 2: CONTABILIDADE (GeneralLedgerEntries)
    # --------------------------------------------------------------------------
    print("\n[2. Validação dos Totalizadores de Contabilidade]")
    gl_debit = safe_get(xml_data, 'SAF-T', 'GeneralLedgerEntries', 'TotalDebit')
    if gl_debit == Decimal('1000.00'):
        print("  ✅ TotalDebit em GeneralLedgerEntries correto (1000.00)")
    else:
        print(f"  ❌ TotalDebit incorreto em GeneralLedgerEntries: {gl_debit}")
        all_passed = False

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO 3: DOCUMENTOS DE ORIGEM (SourceDocuments)
    # --------------------------------------------------------------------------
    print("\n[3. Validação dos Documentos de Origem / SourceDocuments]")
    
    # SalesInvoices
    si_debit = safe_get(xml_data, 'SAF-T', 'SourceDocuments', 'SalesInvoices', 'TotalDebit')
    if si_debit == Decimal('1000.00'):
        print("  ✅ SalesInvoices -> TotalDebit correto (1000.00)")
    else:
        print(f"  ❌ SalesInvoices -> TotalDebit incorreto ou ausente: {si_debit}")
        all_passed = False

    # MovementOfGoods
    mg_qty = safe_get(xml_data, 'SAF-T', 'SourceDocuments', 'MovementOfGoods', 'TotalQuantityIssued')
    if mg_qty == Decimal('100.00'):
        print("  ✅ MovementOfGoods -> TotalQuantityIssued correto (100.00)")
    else:
        print(f"  ❌ MovementOfGoods -> TotalQuantityIssued incorreto ou ausente: {mg_qty}")
        all_passed = False

    # WorkingDocuments
    wd_debit = safe_get(xml_data, 'SAF-T', 'SourceDocuments', 'WorkingDocuments', 'TotalDebit')
    if wd_debit == Decimal('500.00'):
        print("  ✅ WorkingDocuments -> TotalDebit correto (500.00)")
    else:
        print(f"  ❌ WorkingDocuments -> TotalDebit incorreto ou ausente: {wd_debit}")
        all_passed = False

    # Payments
    py_credit = safe_get(xml_data, 'SAF-T', 'SourceDocuments', 'Payments', 'TotalCredit')
    if py_credit == Decimal('2000.00'):
        print("  ✅ Payments -> TotalCredit correto (2000.00)")
    else:
        print(f"  ❌ Payments -> TotalCredit incorreto ou ausente: {py_credit}")
        all_passed = False

    # --------------------------------------------------------------------------
    # RESULTADO FINAL
    # --------------------------------------------------------------------------
    print("\n" + "=" * 60)
    if all_passed:
        print(" 🎉 TODOS OS TESTES PASSARAM! ESTRUTURA COMPATÍVEL COM AGT.")
        print("=" * 60 + "\n")
    else:
        print(" ⚠️ OCORRERAM FALHAS DE VALIDAÇÃO NA ESTRUTURA SAF-T.")
        print("=" * 60 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    verify()
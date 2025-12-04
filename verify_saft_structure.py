
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.append(os.getcwd())

# Mock Django settings
sys.modules['django.conf'] = MagicMock()
from django.conf import settings
settings.PRODUCT_COMPANY_TAX_ID = "5002764377"
settings.SOFTWARE_VALIDATION_NUMBER = "123/AGT/2019"
settings.ERP_PRODUCT_ID = "SOTARQ SOFTWARE ERP"
settings.ERP_PRODUCT_VERSION = "1.0.0"

# Mock Django models
sys.modules['django.db'] = MagicMock()
sys.modules['apps.core.models'] = MagicMock()

# Mock other services
sys.modules['apps.saft.services.contabilidade_service'] = MagicMock()
sys.modules['apps.saft.services.retencao_service'] = MagicMock()
sys.modules['apps.saft.services.master_files_service'] = MagicMock()
sys.modules['apps.saft.services.documentos_service'] = MagicMock()
sys.modules['apps.saft.utils.xml_serializer'] = MagicMock()

# Import the service to test
from apps.saft.services.saft_xml_generator_service import SaftXmlGeneratorService

def verify():
    print("Verifying SAFT XML Generator Structure...")

    # Mock Data
    mock_empresa = MagicMock()
    mock_empresa.nif = "123456789"
    mock_empresa.numero_contribuinte = "123456789"
    mock_empresa.nome = "Empresa Teste"
    mock_empresa.nome_fantasia = "Fantasia Teste"
    mock_empresa.endereco = "Rua Teste"
    mock_empresa.cidade = "Luanda"
    mock_empresa.postal = "1000"
    mock_empresa.telefone = "999999999"
    mock_empresa.email = "teste@empresa.com"
    mock_empresa.website = "www.empresa.com"
    mock_empresa.estabelecimento = "Sede"

    data_inicio = datetime(2024, 1, 1)
    data_fim = datetime(2024, 1, 31)

    # Instantiate Service
    service = SaftXmlGeneratorService(mock_empresa, data_inicio, data_fim)

    # Mock return values for internal services
    service.documentos_service.calculate_global_totals.return_value = {
        'TotalDebit': Decimal('1000.00'),
        'TotalCredit': Decimal('1000.00'),
        'TotalSalesInvoices': Decimal('500.00'),
        'SalesInvoices': {
            'TotalDebit': Decimal('1000.00'),
            'TotalCredit': Decimal('0.00')
        },
        'MovementOfGoods': {
            'TotalQuantity': Decimal('100.00')
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
    service.documentos_service.get_sales_invoices.return_value = [{'InvoiceNo': 'FT 2024/1'}]
    service.documentos_service.get_movement_of_goods.return_value = [{'DocumentNumber': 'GT 2024/1'}]
    service.documentos_service.get_working_documents.return_value = [{'DocumentNumber': 'PP 2024/1'}]
    service.documentos_service.get_payments.return_value = [{'PaymentRefNo': 'RC 2024/1'}]
    
    service.contabilidade_service.get_general_ledger_entries.return_value = [{'TransactionID': '1'}]
    service.contabilidade_service.get_contas_para_saft.return_value = [{'AccountID': '1'}]

    # Generate Data
    xml_data = service._generate_xml_data()
    
    # Verify Header
    header = xml_data['SAF-T']['Header']
    print("\n[Header Verification]")
    
    checks = {
        'AuditFileVersion': '1.01_01',
        'CompanyID': '123456789',
        'TaxAccountingBasis': 'F',
        'CurrencyCode': 'AOA',
        'ProductCompanyTaxID': '5002764377', # From settings
        'SoftwareValidationNumber': '123/AGT/2019', # From settings
        'ProductID': 'SOTARQ SOFTWARE ERP', # From settings
        'TaxEntity': 'Sede'
    }

    all_passed = True
    for key, expected in checks.items():
        actual = header.get(key)
        if actual == expected:
            print(f"✅ {key}: {actual}")
        else:
            print(f"❌ {key}: Expected '{expected}', got '{actual}'")
            all_passed = False

    # Verify Totals are NOT in Header
    forbidden_header_keys = ['TotalDebit', 'TotalCredit', 'TotalSalesInvoices']
    for key in forbidden_header_keys:
        if key in header:
            print(f"❌ {key} found in Header (Should be removed)")
            all_passed = False
        else:
            print(f"✅ {key} correctly absent from Header")

    # Verify Totals in GeneralLedgerEntries
    print("\n[GeneralLedgerEntries Verification]")
    gl_entries = xml_data['SAF-T']['GeneralLedgerEntries']
    if gl_entries['TotalDebit'] == Decimal('1000.00'):
        print("✅ TotalDebit present in GeneralLedgerEntries")
    else:
        print(f"❌ TotalDebit missing or wrong in GeneralLedgerEntries: {gl_entries.get('TotalDebit')}")
        all_passed = False

    # Verify Totals in SourceDocuments
    print("\n[SourceDocuments Verification]")
    source_docs = xml_data['SAF-T']['SourceDocuments']
    
    # SalesInvoices
    if 'SalesInvoices' in source_docs and source_docs['SalesInvoices']['TotalDebit'] == Decimal('1000.00'):
        print("✅ TotalDebit present in SalesInvoices")
    else:
        print(f"❌ TotalDebit missing or wrong in SalesInvoices")
        all_passed = False

    # MovementOfGoods
    if 'MovementOfGoods' in source_docs and source_docs['MovementOfGoods']['TotalQuantityIssued'] == Decimal('100.00'):
        print("✅ TotalQuantityIssued present in MovementOfGoods")
    else:
        print(f"❌ TotalQuantityIssued missing or wrong in MovementOfGoods")
        all_passed = False

    # WorkingDocuments
    if 'WorkingDocuments' in source_docs and source_docs['WorkingDocuments']['TotalDebit'] == Decimal('500.00'):
        print("✅ TotalDebit present in WorkingDocuments")
    else:
        print(f"❌ TotalDebit missing or wrong in WorkingDocuments")
        all_passed = False

    # Payments
    if 'Payments' in source_docs and source_docs['Payments']['TotalCredit'] == Decimal('2000.00'):
        print("✅ TotalCredit present in Payments")
    else:
        print(f"❌ TotalCredit missing or wrong in Payments")
        all_passed = False

    if all_passed:
        print("\n🎉 ALL CHECKS PASSED!")
    else:
        print("\n⚠️ SOME CHECKS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    verify()

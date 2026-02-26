# apps/fiscal/services/utils.py
import logging
import hashlib
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from lxml import etree

# Imports do Projeto
from apps.empresas.models import Empresa
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import logging
from django.utils import timezone
from decimal import Decimal
import hashlib
from django.utils.encoding import force_bytes

from apps.fiscal.models import AssinaturaDigital, ContadorDocumento, DocumentoFiscal, DocumentoFiscalLinha, RetencaoFonte, TaxaIVAAGT

logger = logging.getLogger(__name__)


class FiscalServiceError(Exception):
    pass


def validar_documentos_fiscais(empresa):
    """
    Executa validações em todos os documentos fiscais emitidos pela empresa.

    Retorna um dicionário com contagem de erros e avisos.
    """
    erros = []
    avisos = []

    documentos = DocumentoFiscal.objects.filter(empresa=empresa).order_by('-data_emissao')

    if not documentos.exists():
        avisos.append("Nenhum documento fiscal encontrado para validação.")
        logger.warning(f"Nenhum documento fiscal encontrado para {empresa.nome}")
        return {
            "status": "ok",
            "mensagem": "Nenhum documento encontrado.",
            "erros": len(erros),
            "avisos": len(avisos),
            "detalhes": {"erros": erros, "avisos": avisos},
        }

    for doc in documentos:
        # 🔹 1. Validação de NIF
        if not doc.nif_cliente or len(str(doc.nif_cliente)) < 5:
            erros.append(f"Documento {doc.numero} - NIF inválido ou ausente.")

        # 🔹 2. Validação de valores
        if doc.total < Decimal("0.00"):
            erros.append(f"Documento {doc.numero} - Valor total negativo ({doc.total}).")

        # 🔹 3. Verificação de data futura
        if doc.data_emissao > timezone.now().date():
            avisos.append(f"Documento {doc.numero} - Data de emissão está no futuro ({doc.data_emissao}).")

        # 🔹 4. Verificação de assinatura digital
        if not doc.hash_assinatura:
            avisos.append(f"Documento {doc.numero} - Assinatura digital ausente.")

        # 🔹 5. Verificação de estado
        if not doc.estado or doc.estado not in ["emitido", "cancelado", "pago"]:
            avisos.append(f"Documento {doc.numero} - Estado desconhecido: {doc.estado}.")

    logger.info(f"Validação concluída para {empresa.nome}: {len(erros)} erros, {len(avisos)} avisos.")

    return {
        "status": "ok",
        "empresa": empresa.nome,
        "total_documentos": documentos.count(),
        "erros": len(erros),
        "avisos": len(avisos),
        "detalhes": {
            "erros": erros,
            "avisos": avisos,
        },
        "timestamp": timezone.now().isoformat(),
    }











logger = logging.getLogger('fiscal')

def gerar_rsa_local():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem






def gerar_numero_documento(empresa, tipo_documento, serie='A'):
    """
    Gera o número oficial conforme o modelo DocumentoFiscal.
    Formato exigido: TIPO SERIE/NUMERO
    Exemplo: FR A/1, FT A/2, REC A/1
    """
    ano_atual = timezone.now().year

    with transaction.atomic():
        # select_for_update() bloqueia a linha para evitar duplicidade no PDV
        contador, created = ContadorDocumento.objects.select_for_update().get_or_create(
            empresa=empresa,
            tipo_documento=tipo_documento,
            ano=ano_atual,
            serie=serie,
            defaults={'ultimo_numero': 0}
        )

        contador.ultimo_numero += 1
        contador.save()

        # Montagem rigorosa conforme o campo 'numero_documento' do seu modelo fiscal
        # Formato: TIPO SERIE/NUMERO (Ex: FR A/1)
        numero_final = f"{tipo_documento} {contador.serie}/{contador.ultimo_numero}"

        # Retornamos um dicionário para que o model fiscal preencha os campos 'numero' e 'numero_documento'
        return {
            'sequencial': contador.ultimo_numero,
            'formatado': numero_final
        }



class DocumentoFiscalService:
    """
    Serviço para criação e gestão de Documentos Fiscais.
    """
    @staticmethod
    @transaction.atomic
    def criar_documento(empresa, tipo_documento, cliente, linhas, usuario, dados_extra=None):
        dados_extra = dados_extra or {}

        # Criar documento
        documento = DocumentoFiscal.objects.create(
            empresa=empresa,
            tipo_documento=tipo_documento,
            cliente=cliente,
            usuario_criacao=usuario,
            **dados_extra
        )

        # Criar linhas
        for idx, linha in enumerate(linhas, start=1):
            if linha.get('produto'):
                # É um produto
                taxa_iva_obj = linha['produto'].taxa_iva
                codigo = linha['produto'].codigo_interno
                descricao = linha['produto'].nome_produto
            elif linha.get('servico'):
                # É um serviço
                taxa_iva_obj = linha['servico'].taxa_iva
                codigo = f"S-{linha['servico'].id}"  # identificador único do serviço
                descricao = linha['servico'].nome
            else:
                raise ValueError("Linha deve ter 'produto' ou 'servico'.")

            DocumentoFiscalLinha.objects.create(
                documento=documento,
                numero_linha=idx,
                produto=linha.get('produto'),   # None se for serviço
                codigo_produto=codigo,
                descricao=descricao,
                unidade=linha.get('unidade', 'UN'),
                quantidade=linha.get('quantidade', Decimal('1.0')),
                preco_unitario=linha.get('preco_unitario', Decimal('0.00')),
                valor_desconto_linha=linha.get('desconto', Decimal('0.00')),
                taxa_iva=taxa_iva_obj,
                observacoes_linha=linha.get('observacoes', '')
            )

        # Recalcular totais do documento
        DocumentoFiscalService.recalcular_totais(documento)

        # ====== GERAÇÃO DE HASH E ATCUD ======
        # Importar função utilitária do SAF-T se existir
        from apps.fiscal.utility import gerar_hash_documento, gerar_atcud_documento

        # Se o hash não foi definido ainda
        if not documento.hash_documento:
            documento.hash_documento = gerar_hash_documento(documento)

        # Gera ATCUD (código único do documento)
        if not documento.atcud:
            documento.atcud = gerar_atcud_documento(documento)

        # Salva com os novos campos
        documento.save(update_fields=["hash_documento", "atcud"])




        return documento

    @staticmethod
    def recalcular_totais(documento: DocumentoFiscal):
        """
        Recalcula os totais do documento com base nas linhas.
        """
        linhas = documento.linhas.all()

        valor_base = sum([l.valor_liquido for l in linhas])
        valor_iva = sum([l.valor_iva_linha for l in linhas])
        valor_total = sum([l.valor_total_linha for l in linhas])

        documento.valor_base = valor_base
        documento.valor_iva = valor_iva
        documento.valor_total = valor_total
        documento.save(update_fields=['valor_base', 'valor_iva', 'valor_total'])
        return documento

    @staticmethod
    def confirmar_documento(documento: DocumentoFiscal, usuario):
        """
        Confirma e assina digitalmente o documento.
        """
        if documento.status != 'draft':
            raise ValidationError("Apenas documentos em rascunho podem ser confirmados.")

        documento.confirmar_documento(usuario)
        return documento

    @staticmethod
    def cancelar_documento(documento: DocumentoFiscal, usuario, motivo=''):
        """
        Cancela um documento fiscal.
        """
        documento.cancelar_documento(usuario, motivo)
        return documento




class TaxaIVAService:
    """
    Serviço para gestão de Taxas de IVA compatível com SAF-T AO v1.01
    """
    
    @staticmethod
    def criar_taxa_iva(empresa: Empresa, dados: Dict) -> TaxaIVAAGT:
        """
        Cria uma nova taxa de IVA com validações SAF-T
        
        Args:
            empresa: Empresa proprietária da taxa
            dados: Dicionário com dados da taxa
            
        Returns:
            TaxaIVAAGT: Taxa criada
            
        Raises:
            FiscalServiceError: Se houver erro na criação
        """
        try:
            with transaction.atomic():
                # Validações SAF-T específicas
                TaxaIVAService._validar_dados_saft(dados)
                
                taxa = TaxaIVAAGT.objects.create(
                    empresa=empresa,
                    nome=dados['nome'],
                    tax_type=dados['tax_type'],
                    tax_code=dados['tax_code'],
                    tax_percentage=dados.get('tax_percentage', Decimal('0.00')),
                    exemption_reason=dados.get('exemption_reason'),
                    legislacao_referencia=dados.get('legislacao_referencia', ''),
                    ativa=dados.get('ativa', True)
                )
                
                logger.info(
                    f"Taxa IVA criada: {taxa.nome} para empresa {empresa.nome}",
                    extra={
                        'empresa_id': empresa.id,
                        'taxa_id': taxa.id,
                        'tax_type': taxa.tax_type,
                        'tax_percentage': float(taxa.tax_percentage)
                    }
                )
                
                return taxa
                
        except ValidationError as e:
            logger.error(f"Erro de validação ao criar taxa IVA: {e}")
            raise FiscalServiceError(f"Dados inválidos: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao criar taxa IVA: {e}")
            raise FiscalServiceError(f"Erro interno: {e}")
    
    @staticmethod
    def _validar_dados_saft(dados: Dict) -> None:
        """Valida dados conforme especificação SAF-T AO"""
        
        # Validar tax_type
        if dados['tax_type'] not in ['IVA', 'IS', 'NS']:
            raise ValidationError("tax_type deve ser IVA, IS ou NS")
        
        # Se for IVA, deve ter tax_percentage
        if dados['tax_type'] == 'IVA':
            if not dados.get('tax_percentage') or dados['tax_percentage'] < 0:
                raise ValidationError("IVA deve ter tax_percentage válida")
        
        # Se for IS ou NS, deve ter exemption_reason
        if dados['tax_type'] in ['IS', 'NS']:
            if not dados.get('exemption_reason'):
                raise ValidationError("Isenções e não sujeições devem ter exemption_reason")
    
    @staticmethod
    def obter_taxas_ativas(empresa: Empresa) -> List[TaxaIVAAGT]:
        """Obtém todas as taxas ativas de uma empresa"""
        return TaxaIVAAGT.objects.filter(
            empresa=empresa,
            ativa=True
        ).order_by('tax_type', '-tax_percentage')
    
    @staticmethod
    def calcular_iva(valor_base: Decimal, taxa: TaxaIVAAGT) -> Dict[str, Decimal]:
        """
        Calcula o IVA baseado no valor base e taxa
        
        Returns:
            Dict com valor_base, valor_iva, valor_total
        """
        if taxa.tax_type != 'IVA':
            return {
                'valor_base': valor_base,
                'valor_iva': Decimal('0.00'),
                'valor_total': valor_base,
                'taxa_aplicada': Decimal('0.00'),
                'motivo_isencao': taxa.exemption_reason
            }
        
        valor_iva = valor_base * (taxa.tax_percentage / Decimal('100.00'))
        valor_total = valor_base + valor_iva
        
        return {
            'valor_base': valor_base,
            'valor_iva': valor_iva,
            'valor_total': valor_total,
            'taxa_aplicada': taxa.tax_percentage
        }


logger = logging.getLogger(__name__)



class RetencaoFonteService:
    """
    Serviço para gestão de retenções na fonte
    """
    
    @staticmethod
    def criar_retencao(dados: Dict) -> RetencaoFonte:
        """
        Cria uma nova retenção na fonte com lançamentos contábeis
        
        Args:
            dados: Dados da retenção
            
        Returns:
            RetencaoFonte: Retenção criada
        """
        try:
            with transaction.atomic():
                retencao = RetencaoFonte.objects.create(**dados)
                
                # Gerar lançamento contábil
                RetencaoFonteService._gerar_lancamento_contabil(retencao)
                
                logger.info(
                    f"Retenção na fonte criada",
                    extra={
                        'retencao_id': retencao.id,
                        'tipo_retencao': retencao.tipo_retencao,
                        'valor_retido': float(retencao.valor_retido),
                        'fornecedor_id': retencao.fornecedor.id
                    }
                )
                
                return retencao
                
        except Exception as e:
            logger.error(f"Erro ao criar retenção: {e}")
            raise FiscalServiceError(f"Erro na criação: {e}")
    
   
    @staticmethod
    def processar_pagamento_estado(retencao_id: int, data_pagamento: date) -> RetencaoFonte:
        """
        Marca uma retenção como paga ao Estado
        
        Args:
            retencao_id: ID da retenção
            data_pagamento: Data do pagamento
            
        Returns:
            RetencaoFonte: Retenção atualizada
        """
        try:
            with transaction.atomic():
                retencao = RetencaoFonte.objects.get(id=retencao_id)
                retencao.paga_ao_estado = True
                retencao.save()
                
                logger.info(
                    f"Retenção marcada como paga ao Estado",
                    extra={
                        'retencao_id': retencao_id,
                        'data_pagamento': data_pagamento.isoformat(),
                        'valor': float(retencao.valor_retido)
                    }
                )
                
                return retencao
                
        except RetencaoFonte.DoesNotExist:
            logger.error(f"Retenção {retencao_id} não encontrada")
            raise FiscalServiceError("Retenção não encontrada")
        except Exception as e:
            logger.error(f"Erro ao processar pagamento: {e}")
            raise FiscalServiceError(f"Erro no processamento: {e}")





class SAFTExportService:
    """
    Serviço completo para exportação SAF-T AO v1.01_01 (AGT)
    100% compatível com o esquema XSD oficial SAFTAO1.01_01.xsd
    """

    NAMESPACE = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"

    @staticmethod
    def validar_xsd(xml_str: str):
        """Valida o XML conforme schema oficial SAF-T AO 1.01_01"""
        xsd_path = os.path.join(settings.BASE_DIR, "apps", "fiscal", "schemas", "SAFTAO1.01_01.xsd")
        xmlschema_doc = etree.parse(str(Path(xsd_path)))
        xmlschema = etree.XMLSchema(xmlschema_doc)
        xml_doc = etree.fromstring(xml_str.encode('utf-8'))
        xmlschema.assertValid(xml_doc)
        logger.info("Validação XSD SAF-T AO concluída com sucesso.")

    @staticmethod
    def gerar_saft_ao(empresa, data_inicio: date, data_fim: date) -> str:
        """Gera o arquivo SAF-T AO completo e validado"""
        try:
            logger.info(
                f"Iniciando geração SAF-T AO",
                extra={'empresa_id': empresa.id, 'data_inicio': data_inicio.isoformat(),
                       'data_fim': data_fim.isoformat()}
            )

            ET.register_namespace('', SAFTExportService.NAMESPACE)
            root = ET.Element("{%s}AuditFile" % SAFTExportService.NAMESPACE)

            root.append(SAFTExportService._criar_header(empresa, data_inicio, data_fim))
            root.append(SAFTExportService._criar_master_files(empresa))

            general_ledger = SAFTExportService._criar_general_ledger_entries(empresa, data_inicio, data_fim)
            if general_ledger is not None:
                root.append(general_ledger)

            source_docs = SAFTExportService._criar_source_documents(empresa, data_inicio, data_fim)
            if source_docs is not None:
                root.append(source_docs)

            xml_string = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            xml_formatted = xml_string.decode('utf-8')

            SAFTExportService.validar_xsd(xml_formatted)

            logger.info("SAF-T AO gerado e validado com sucesso.")
            return xml_formatted

        except Exception as e:
            logger.error(f"Erro ao gerar SAF-T AO: {e}")
            raise FiscalServiceError(f"Erro na geração SAF-T: {e}")

    @staticmethod
    def _criar_elemento(tag, texto=None):
        """Cria elemento XML com namespace correto"""
        elem = ET.Element("{%s}%s" % (SAFTExportService.NAMESPACE, tag))
        if texto is not None:
            elem.text = str(texto)
        return elem

    @staticmethod
    def _criar_subelemento(parent, tag, texto=None):
        """Cria subelemento XML com namespace correto"""
        elem = ET.SubElement(parent, "{%s}%s" % (SAFTExportService.NAMESPACE, tag))
        if texto is not None:
            elem.text = str(texto)
        return elem

    @staticmethod
    def _criar_header(empresa, data_inicio: date, data_fim: date):
        """Cria o elemento Header conforme XSD"""
        header = SAFTExportService._criar_elemento("Header")

        SAFTExportService._criar_subelemento(header, "AuditFileVersion", "1.01_01")
        SAFTExportService._criar_subelemento(header, "CompanyID", empresa.nif or str(empresa.id))
        SAFTExportService._criar_subelemento(header, "TaxRegistrationNumber", empresa.nif)
        SAFTExportService._criar_subelemento(header, "TaxAccountingBasis", "F")
        SAFTExportService._criar_subelemento(header, "CompanyName", empresa.nome[:200])

        if empresa.nome_fantasia:
            SAFTExportService._criar_subelemento(header, "BusinessName", empresa.nome_fantasia[:60])

        company_address = SAFTExportService._criar_subelemento(header, "CompanyAddress")
        SAFTExportService._criar_subelemento(company_address, "AddressDetail", empresa.endereco or "Desconhecido")
        SAFTExportService._criar_subelemento(company_address, "City", empresa.cidade or "Luanda")
        if empresa.postal:
            SAFTExportService._criar_subelemento(company_address, "PostalCode", empresa.postal[:10])
        SAFTExportService._criar_subelemento(company_address, "Country", "AO")

        SAFTExportService._criar_subelemento(header, "FiscalYear", str(data_inicio.year))
        SAFTExportService._criar_subelemento(header, "StartDate", data_inicio.strftime("%Y-%m-%d"))
        SAFTExportService._criar_subelemento(header, "EndDate", data_fim.strftime("%Y-%m-%d"))
        SAFTExportService._criar_subelemento(header, "CurrencyCode", "AOA")
        SAFTExportService._criar_subelemento(header, "DateCreated", timezone.now().strftime("%Y-%m-%d"))

        tax_entity = getattr(empresa, 'estabelecimento', None) or "Sede"
        SAFTExportService._criar_subelemento(header, "TaxEntity", tax_entity[:20])

        product_company_tax_id = getattr(settings, "PRODUCT_COMPANY_TAX_ID", empresa.nif or "999999999")
        SAFTExportService._criar_subelemento(header, "ProductCompanyTaxID", product_company_tax_id[:20])

        software_validation_number = getattr(settings, "SOFTWARE_VALIDATION_NUMBER", "0")
        SAFTExportService._criar_subelemento(header, "SoftwareValidationNumber", software_validation_number)

        product_id = getattr(settings, "ERP_PRODUCT_ID", "ERP/SoftwareHouse")
        SAFTExportService._criar_subelemento(header, "ProductID", product_id)

        product_version = getattr(settings, "ERP_PRODUCT_VERSION", "1.0")
        SAFTExportService._criar_subelemento(header, "ProductVersion", product_version[:30])

        if hasattr(empresa, 'telefone') and empresa.telefone:
            SAFTExportService._criar_subelemento(header, "Telephone", empresa.telefone[:20])

        if hasattr(empresa, 'email') and empresa.email:
            SAFTExportService._criar_subelemento(header, "Email", empresa.email[:255])

        if hasattr(empresa, 'website') and empresa.website:
            SAFTExportService._criar_subelemento(header, "Website", empresa.website[:60])

        return header

    @staticmethod
    def _criar_master_files(empresa):
        """Cria o elemento MasterFiles conforme XSD"""
        master_files = SAFTExportService._criar_elemento("MasterFiles")

        SAFTExportService._criar_general_ledger_accounts(master_files, empresa)
        SAFTExportService._criar_customers(master_files, empresa)
        SAFTExportService._criar_suppliers(master_files, empresa)
        SAFTExportService._criar_products(master_files, empresa)
        SAFTExportService._criar_tax_table(master_files, empresa)

        return master_files

    @staticmethod
    def _criar_general_ledger_accounts(master_files, empresa):
        """Cria GeneralLedgerAccounts conforme XSD"""
        if not hasattr(empresa, 'planos_contas'):
            return

        contas = empresa.planos_contas.filter(ativa=True)
        for conta in contas:
            gl_account = SAFTExportService._criar_subelemento(master_files, "GeneralLedgerAccounts")
            account = SAFTExportService._criar_subelemento(gl_account, "Account")

            SAFTExportService._criar_subelemento(account, "AccountID", conta.codigo[:30])
            SAFTExportService._criar_subelemento(account, "AccountDescription", conta.nome[:100])

            saldo_abertura_debito = getattr(conta, 'saldo_abertura_debito', Decimal("0.00"))
            SAFTExportService._criar_subelemento(account, "OpeningDebitBalance", f"{saldo_abertura_debito:.2f}")

            saldo_abertura_credito = getattr(conta, 'saldo_abertura_credito', Decimal("0.00"))
            SAFTExportService._criar_subelemento(account, "OpeningCreditBalance", f"{saldo_abertura_credito:.2f}")

            saldo_encerramento_debito = getattr(conta, 'saldo_encerramento_debito', Decimal("0.00"))
            SAFTExportService._criar_subelemento(account, "ClosingDebitBalance", f"{saldo_encerramento_debito:.2f}")

            saldo_encerramento_credito = getattr(conta, 'saldo_encerramento_credito', Decimal("0.00"))
            SAFTExportService._criar_subelemento(account, "ClosingCreditBalance", f"{saldo_encerramento_credito:.2f}")

            grouping_category = SAFTExportService._determinar_grouping_category(conta)
            SAFTExportService._criar_subelemento(account, "GroupingCategory", grouping_category)

            if hasattr(conta, 'conta_pai') and conta.conta_pai and grouping_category != "GR":
                SAFTExportService._criar_subelemento(account, "GroupingCode", conta.conta_pai.codigo[:30])

    @staticmethod
    def _determinar_grouping_category(conta):
        """Determina a categoria da conta"""
        if hasattr(conta, 'grouping_category'):
            return conta.grouping_category

        if hasattr(conta, 'nivel'):
            if conta.nivel == 1:
                return "GR"
            elif hasattr(conta, 'tem_filhos') and conta.tem_filhos:
                return "GA"
            else:
                return "GM"

        return "GM"

    @staticmethod
    def _criar_customers(master_files, empresa):
        """Cria elementos Customer conforme XSD"""
        from apps.clientes.models import Cliente

        clientes = Cliente.objects.filter(empresa=empresa)
        for cliente in clientes:
            customer = SAFTExportService._criar_subelemento(master_files, "Customer")

            SAFTExportService._criar_subelemento(customer, "CustomerID", str(cliente.id)[:30])

            account_id = getattr(cliente, 'conta_contabil', None)
            if account_id:
                SAFTExportService._criar_subelemento(customer, "AccountID", str(account_id)[:30])
            else:
                SAFTExportService._criar_subelemento(customer, "AccountID", "Desconhecido")

            customer_tax_id = cliente.nif if cliente.nif else "999999999"
            SAFTExportService._criar_subelemento(customer, "CustomerTaxID", customer_tax_id[:30])

            SAFTExportService._criar_subelemento(customer, "CompanyName", cliente.nome_exibicao[:200])

            billing_address = SAFTExportService._criar_subelemento(customer, "BillingAddress")
            SAFTExportService._criar_address_details(billing_address, cliente)

            SAFTExportService._criar_subelemento(customer, "SelfBillingIndicator", "0")

    @staticmethod
    def _criar_suppliers(master_files, empresa):
        """Cria elementos Supplier conforme XSD"""
        from apps.fornecedores.models import Fornecedor

        fornecedores = Fornecedor.objects.filter(empresa=empresa)
        for fornecedor in fornecedores:
            supplier = SAFTExportService._criar_subelemento(master_files, "Supplier")

            SAFTExportService._criar_subelemento(supplier, "SupplierID", str(fornecedor.id)[:30])

            account_id = getattr(fornecedor, 'conta_contabil', None)
            if account_id:
                SAFTExportService._criar_subelemento(supplier, "AccountID", str(account_id)[:30])
            else:
                SAFTExportService._criar_subelemento(supplier, "AccountID", "Desconhecido")

            supplier_tax_id = fornecedor.nif if fornecedor.nif else "999999999"
            SAFTExportService._criar_subelemento(supplier, "SupplierTaxID", supplier_tax_id[:20])

            SAFTExportService._criar_subelemento(supplier, "CompanyName", fornecedor.nome[:200])

            billing_address = SAFTExportService._criar_subelemento(supplier, "BillingAddress")
            SAFTExportService._criar_address_details(billing_address, fornecedor)

            SAFTExportService._criar_subelemento(supplier, "SelfBillingIndicator", "0")

    @staticmethod
    def _criar_address_details(address_element, entity):
        """Adiciona detalhes de endereço"""
        if hasattr(entity, 'numero_porta') and entity.numero_porta:
            SAFTExportService._criar_subelemento(address_element, "BuildingNumber", str(entity.numero_porta)[:15])

        if hasattr(entity, 'rua') and entity.rua:
            SAFTExportService._criar_subelemento(address_element, "StreetName", entity.rua[:200])

        endereco = getattr(entity, 'endereco', None) or "Desconhecido"
        SAFTExportService._criar_subelemento(address_element, "AddressDetail", endereco[:250])

        cidade = getattr(entity, 'cidade', None) or "Luanda"
        SAFTExportService._criar_subelemento(address_element, "City", cidade[:50])

        if hasattr(entity, 'codigo_postal') and entity.codigo_postal:
            SAFTExportService._criar_subelemento(address_element, "PostalCode", entity.codigo_postal[:20])

        if hasattr(entity, 'provincia') and entity.provincia:
            SAFTExportService._criar_subelemento(address_element, "Province", entity.provincia[:50])

        pais = getattr(entity, 'pais', None) or "AO"
        SAFTExportService._criar_subelemento(address_element, "Country", pais[:2] if len(pais) >= 2 else "AO")

    @staticmethod
    def _criar_products(master_files, empresa):
        """Cria elementos Product conforme XSD"""
        if not hasattr(empresa, 'produtos'):
            return

        produtos = empresa.produtos.all()
        for produto in produtos:
            product = SAFTExportService._criar_subelemento(master_files, "Product")

            product_type = getattr(produto, 'tipo_produto', 'P')
            if product_type not in ['P', 'S', 'O', 'E', 'I']:
                product_type = 'P'
            SAFTExportService._criar_subelemento(product, "ProductType", product_type)

            SAFTExportService._criar_subelemento(product, "ProductCode", produto.codigo_interno[:60])

            if hasattr(produto, 'grupo') and produto.grupo:
                SAFTExportService._criar_subelemento(product, "ProductGroup", str(produto.grupo)[:50])

            SAFTExportService._criar_subelemento(product, "ProductDescription", produto.nome_produto[:200])

            product_number_code = getattr(produto, 'codigo_ean', None) or produto.codigo_interno
            SAFTExportService._criar_subelemento(product, "ProductNumberCode", product_number_code[:60])

    @staticmethod
    def _criar_tax_table(master_files, empresa):
        """Cria elemento TaxTable conforme XSD"""
        if not hasattr(empresa, 'taxas_iva'):
            return

        taxas = empresa.taxas_iva.filter(ativo=True)
        if not taxas.exists():
            return

        tax_table = SAFTExportService._criar_subelemento(master_files, "TaxTable")

        for taxa in taxas:
            tax_entry = SAFTExportService._criar_subelemento(tax_table, "TaxTableEntry")

            tax_type = getattr(taxa, 'tax_type', 'IVA')
            if tax_type not in ['IVA', 'IS', 'NS']:
                tax_type = 'IVA'
            SAFTExportService._criar_subelemento(tax_entry, "TaxType", tax_type)

            if hasattr(taxa, 'tax_country_region') and taxa.tax_country_region:
                SAFTExportService._criar_subelemento(tax_entry, "TaxCountryRegion", taxa.tax_country_region[:6])

            tax_code = getattr(taxa, 'tax_code', 'NOR')
            SAFTExportService._criar_subelemento(tax_entry, "TaxCode", tax_code[:10])

            SAFTExportService._criar_subelemento(tax_entry, "Description", taxa.nome[:255])

            if hasattr(taxa, 'data_expiracao') and taxa.data_expiracao:
                SAFTExportService._criar_subelemento(tax_entry, "TaxExpirationDate", taxa.data_expiracao.strftime("%Y-%m-%d"))

            if hasattr(taxa, 'tax_percentage') and taxa.tax_percentage is not None:
                SAFTExportService._criar_subelemento(tax_entry, "TaxPercentage", f"{taxa.tax_percentage:.2f}")
            elif hasattr(taxa, 'tax_amount') and taxa.tax_amount is not None:
                SAFTExportService._criar_subelemento(tax_entry, "TaxAmount", f"{taxa.tax_amount:.2f}")
            else:
                SAFTExportService._criar_subelemento(tax_entry, "TaxPercentage", "0.00")

    @staticmethod
    def _criar_general_ledger_entries(empresa, data_inicio: date, data_fim: date):
        """Cria elemento GeneralLedgerEntries conforme XSD"""
        from apps.financeiro.models import MovimentacaoFinanceira

        if not hasattr(MovimentacaoFinanceira, 'objects'):
            return None

        movimentacoes = MovimentacaoFinanceira.objects.filter(
            empresa=empresa,
            data_movimentacao__gte=data_inicio,
            data_movimentacao__lte=data_fim,
            status="confirmada"
        ).select_related('plano_contas', 'cliente', 'fornecedor').order_by('data_movimentacao', 'id')

        if not movimentacoes.exists():
            return None

        gl_entries = SAFTExportService._criar_elemento("GeneralLedgerEntries")

        SAFTExportService._criar_subelemento(gl_entries, "NumberOfEntries", str(movimentacoes.count()))

        total_debit = sum(mov.debito or Decimal("0.00") for mov in movimentacoes)
        SAFTExportService._criar_subelemento(gl_entries, "TotalDebit", f"{total_debit:.2f}")

        total_credit = sum(mov.credito or Decimal("0.00") for mov in movimentacoes)
        SAFTExportService._criar_subelemento(gl_entries, "TotalCredit", f"{total_credit:.2f}")

        journals = {}
        for mov in movimentacoes:
            journal_id = getattr(mov, 'diario_id', None) or "GERAL"
            if journal_id not in journals:
                journals[journal_id] = []
            journals[journal_id].append(mov)

        for journal_id, movimentos in journals.items():
            SAFTExportService._criar_journal(gl_entries, journal_id, movimentos)

        return gl_entries

    @staticmethod
    def _criar_journal(gl_entries, journal_id, movimentos):
        """Cria um Journal dentro de GeneralLedgerEntries"""
        journal = SAFTExportService._criar_subelemento(gl_entries, "Journal")

        SAFTExportService._criar_subelemento(journal, "JournalID", str(journal_id)[:30])
        SAFTExportService._criar_subelemento(journal, "Description", f"Diário {journal_id}"[:200])

        for mov in movimentos:
            SAFTExportService._criar_transaction(journal, mov)

    @staticmethod
    def _criar_transaction(journal, mov):
        """Cria uma Transaction dentro de Journal"""
        transaction = SAFTExportService._criar_subelemento(journal, "Transaction")

        transaction_date = mov.data_movimentacao.strftime("%Y-%m-%d")
        journal_id = getattr(mov, 'diario_id', None) or "GERAL"
        doc_arch_number = getattr(mov, 'numero_documento', None) or str(mov.id)
        transaction_id = f"{transaction_date} {journal_id} {doc_arch_number}"
        SAFTExportService._criar_subelemento(transaction, "TransactionID", transaction_id[:70])

        periodo = mov.data_movimentacao.month
        SAFTExportService._criar_subelemento(transaction, "Period", str(periodo))

        SAFTExportService._criar_subelemento(transaction, "TransactionDate", transaction_date)

        source_id = getattr(mov, 'usuario_id', None) or "Sistema"
        SAFTExportService._criar_subelemento(transaction, "SourceID", str(source_id)[:30])

        descricao = mov.descricao or "Movimento Financeiro"
        SAFTExportService._criar_subelemento(transaction, "Description", descricao[:200])

        SAFTExportService._criar_subelemento(transaction, "DocArchivalNumber", str(doc_arch_number)[:20])

        transaction_type = getattr(mov, 'tipo_transacao', 'N')
        if transaction_type not in ['N', 'R', 'A', 'J']:
            transaction_type = 'N'
        SAFTExportService._criar_subelemento(transaction, "TransactionType", transaction_type)

        SAFTExportService._criar_subelemento(transaction, "GLPostingDate", transaction_date)

        if hasattr(mov, 'cliente') and mov.cliente:
            SAFTExportService._criar_subelemento(transaction, "CustomerID", str(mov.cliente.id)[:30])
        elif hasattr(mov, 'fornecedor') and mov.fornecedor:
            SAFTExportService._criar_subelemento(transaction, "SupplierID", str(mov.fornecedor.id)[:30])

        lines = SAFTExportService._criar_subelemento(transaction, "Lines")

        if mov.debito and mov.debito > 0:
            debit_line = SAFTExportService._criar_subelemento(lines, "DebitLine")
            SAFTExportService._criar_subelemento(debit_line, "RecordID", str(mov.id)[:30])
            account_id = mov.plano_contas.codigo if mov.plano_contas else "Desconhecido"
            SAFTExportService._criar_subelemento(debit_line, "AccountID", account_id[:30])
            SAFTExportService._criar_subelemento(debit_line, "SystemEntryDate", mov.data_movimentacao.strftime("%Y-%m-%dT%H:%M:%S"))
            SAFTExportService._criar_subelemento(debit_line, "Description", descricao[:200])
            SAFTExportService._criar_subelemento(debit_line, "DebitAmount", f"{mov.debito:.2f}")

        if mov.credito and mov.credito > 0:
            credit_line = SAFTExportService._criar_subelemento(lines, "CreditLine")
            SAFTExportService._criar_subelemento(credit_line, "RecordID", str(mov.id)[:30])
            account_id = mov.plano_contas.codigo if mov.plano_contas else "Desconhecido"
            SAFTExportService._criar_subelemento(credit_line, "AccountID", account_id[:30])
            SAFTExportService._criar_subelemento(credit_line, "SystemEntryDate", mov.data_movimentacao.strftime("%Y-%m-%dT%H:%M:%S"))
            SAFTExportService._criar_subelemento(credit_line, "Description", descricao[:200])
            SAFTExportService._criar_subelemento(credit_line, "CreditAmount", f"{mov.credito:.2f}")

    @staticmethod
    def _criar_source_documents(empresa, data_inicio: date, data_fim: date):
        """Cria elemento SourceDocuments conforme XSD"""
        source_documents = SAFTExportService._criar_elemento("SourceDocuments")
        has_content = False

        sales_invoices = SAFTExportService._criar_sales_invoices(empresa, data_inicio, data_fim)
        if sales_invoices is not None:
            source_documents.append(sales_invoices)
            has_content = True

        movement_of_goods = SAFTExportService._criar_movement_of_goods(empresa, data_inicio, data_fim)
        if movement_of_goods is not None:
            source_documents.append(movement_of_goods)
            has_content = True

        working_documents = SAFTExportService._criar_working_documents(empresa, data_inicio, data_fim)
        if working_documents is not None:
            source_documents.append(working_documents)
            has_content = True

        payments = SAFTExportService._criar_payments(empresa, data_inicio, data_fim)
        if payments is not None:
            source_documents.append(payments)
            has_content = True

        return source_documents if has_content else None

    @staticmethod
    def _criar_sales_invoices(empresa, data_inicio: date, data_fim: date):
        """Cria elemento SalesInvoices conforme XSD"""
        from apps.vendas.models import Venda

        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__date__gte=data_inicio,
            data_venda__date__lte=data_fim,
            status="finalizada"
        ).select_related("cliente").prefetch_related("itens__taxa_iva").order_by('data_venda', 'id')

        if not vendas.exists():
            return None

        sales_invoices = SAFTExportService._criar_elemento("SalesInvoices")

        vendas_normais = [v for v in vendas if getattr(v, 'invoice_status', 'N') == 'N']
        SAFTExportService._criar_subelemento(sales_invoices, "NumberOfEntries", str(len(vendas_normais)))

        total_debit = Decimal("0.00")
        total_credit = sum(v.total for v in vendas_normais)

        SAFTExportService._criar_subelemento(sales_invoices, "TotalDebit", f"{total_debit:.2f}")
        SAFTExportService._criar_subelemento(sales_invoices, "TotalCredit", f"{total_credit:.2f}")

        for venda in vendas:
            SAFTExportService._criar_invoice(sales_invoices, venda)

        return sales_invoices

    @staticmethod
    def _criar_invoice(sales_invoices, venda):
        """Cria um Invoice dentro de SalesInvoices"""
        invoice = SAFTExportService._criar_subelemento(sales_invoices, "Invoice")

        invoice_no = venda.numero_documento or f"FT SERIE001/{venda.id}"
        SAFTExportService._criar_subelemento(invoice, "InvoiceNo", invoice_no[:60])

        document_status = SAFTExportService._criar_subelemento(invoice, "DocumentStatus")
        invoice_status = getattr(venda, 'invoice_status', 'N')
        if invoice_status not in ['N', 'S', 'A', 'R']:
            invoice_status = 'N'
        SAFTExportService._criar_subelemento(document_status, "InvoiceStatus", invoice_status)

        status_date = getattr(venda, 'data_status', None) or venda.data_venda
        SAFTExportService._criar_subelemento(document_status, "InvoiceStatusDate", status_date.strftime("%Y-%m-%dT%H:%M:%S"))

        if hasattr(venda, 'motivo_anulacao') and venda.motivo_anulacao:
            SAFTExportService._criar_subelemento(document_status, "Reason", venda.motivo_anulacao[:50])

        source_id = getattr(venda, 'usuario_id', None) or "Sistema"
        SAFTExportService._criar_subelemento(document_status, "SourceID", str(source_id)[:30])

        source_billing = getattr(venda, 'source_billing', 'P')
        if source_billing not in ['P', 'I', 'M']:
            source_billing = 'P'
        SAFTExportService._criar_subelemento(document_status, "SourceBilling", source_billing)

        hash_control = getattr(venda, 'hash_control', None) or "0"
        hash_input = f"{venda.empresa.nif}{invoice_no}{venda.data_venda.strftime('%Y-%m-%d')}{venda.total}"
        hash_str = hashlib.sha1(hash_input.encode('utf-8')).hexdigest()
        SAFTExportService._criar_subelemento(invoice, "Hash", hash_str[:172])
        SAFTExportService._criar_subelemento(invoice, "HashControl", str(hash_control)[:70])

        if hasattr(venda, 'periodo') and venda.periodo:
            SAFTExportService._criar_subelemento(invoice, "Period", str(venda.periodo))

        SAFTExportService._criar_subelemento(invoice, "InvoiceDate", venda.data_venda.strftime("%Y-%m-%d"))

        invoice_type = getattr(venda, 'invoice_type', 'FT')
        if invoice_type not in ['FT', 'FR', 'GF', 'FG', 'AC', 'AR', 'ND', 'NC', 'AF', 'TV', 'RP', 'RE', 'CS', 'LD', 'RA']:
            invoice_type = 'FT'
        SAFTExportService._criar_subelemento(invoice, "InvoiceType", invoice_type)

        special_regimes = SAFTExportService._criar_subelemento(invoice, "SpecialRegimes")
        SAFTExportService._criar_subelemento(special_regimes, "SelfBillingIndicator", "0")
        SAFTExportService._criar_subelemento(special_regimes, "CashVATSchemeIndicator", "0")
        SAFTExportService._criar_subelemento(special_regimes, "ThirdPartiesBillingIndicator", "0")

        SAFTExportService._criar_subelemento(invoice, "SourceID", str(source_id)[:30])

        SAFTExportService._criar_subelemento(invoice, "SystemEntryDate", venda.data_venda.strftime("%Y-%m-%dT%H:%M:%S"))

        customer_id = str(venda.cliente.id) if venda.cliente else "1"
        SAFTExportService._criar_subelemento(invoice, "CustomerID", customer_id[:30])

        line_number = 1
        for item in venda.itens.all():
            line = SAFTExportService._criar_subelemento(invoice, "Line")

            SAFTExportService._criar_subelemento(line, "LineNumber", str(line_number))

            product_code = str(item.produto.id) if item.produto else "1"
            SAFTExportService._criar_subelemento(line, "ProductCode", product_code[:60])

            descricao = item.nome_produto or item.nome_servico or "Produto/Serviço"
            SAFTExportService._criar_subelemento(line, "ProductDescription", descricao[:200])

            SAFTExportService._criar_subelemento(line, "Quantity", f"{item.quantidade:.2f}")

            unidade = getattr(item, 'unidade_medida', 'UN')
            SAFTExportService._criar_subelemento(line, "UnitOfMeasure", unidade[:20])

            SAFTExportService._criar_subelemento(line, "UnitPrice", f"{item.preco_unitario:.2f}")

            tax_point_date = getattr(item, 'data_envio', None) or venda.data_venda
            SAFTExportService._criar_subelemento(line, "TaxPointDate", tax_point_date.strftime("%Y-%m-%d"))

            SAFTExportService._criar_subelemento(line, "Description", descricao[:200])

            SAFTExportService._criar_subelemento(line, "CreditAmount", f"{item.total:.2f}")

            tax = SAFTExportService._criar_subelemento(line, "Tax")
            tax_type = getattr(item, 'tax_type', 'IVA')
            if tax_type not in ['IVA', 'IS', 'NS']:
                tax_type = 'IVA'
            SAFTExportService._criar_subelemento(tax, "TaxType", tax_type)

            tax_code = getattr(item, 'tax_code', 'NOR')
            SAFTExportService._criar_subelemento(tax, "TaxCode", tax_code[:10])

            iva_percentual = item.iva_percentual or Decimal("0.00")
            SAFTExportService._criar_subelemento(tax, "TaxPercentage", f"{iva_percentual:.2f}")

            if iva_percentual == 0:
                exemption_reason = getattr(item, 'motivo_isencao', 'Isento nos termos da legislação aplicável')
                SAFTExportService._criar_subelemento(line, "TaxExemptionReason", exemption_reason[:60])

                exemption_code = getattr(item, 'codigo_isencao', 'M01')
                SAFTExportService._criar_subelemento(line, "TaxExemptionCode", exemption_code)

            line_number += 1

        document_totals = SAFTExportService._criar_subelemento(invoice, "DocumentTotals")

        tax_payable = venda.iva_valor or Decimal("0.00")
        SAFTExportService._criar_subelemento(document_totals, "TaxPayable", f"{tax_payable:.2f}")

        net_total = venda.subtotal or Decimal("0.00")
        SAFTExportService._criar_subelemento(document_totals, "NetTotal", f"{net_total:.2f}")

        gross_total = venda.total or Decimal("0.00")
        SAFTExportService._criar_subelemento(document_totals, "GrossTotal", f"{gross_total:.2f}")

    @staticmethod
    def _criar_movement_of_goods(empresa, data_inicio: date, data_fim: date):
        """Cria elemento MovementOfGoods se existir"""
        return None

    @staticmethod
    def _criar_working_documents(empresa, data_inicio: date, data_fim: date):
        """Cria elemento WorkingDocuments se existir"""
        return None

    @staticmethod
    def _criar_payments(empresa, data_inicio: date, data_fim: date):
        """Cria elemento Payments se existir"""
        return None

    @staticmethod
    def gerar_zip_assinado(xml_str: str, empresa):
        """Gera arquivo ZIP com o XML e hash"""
        xml_path = SAFTExportService.salvar_xml(xml_str, empresa)
        hash_str = hashlib.sha256(xml_str.encode('utf-8')).hexdigest()
        zip_path = xml_path.replace('.xml', '.zip')

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(xml_path, os.path.basename(xml_path))
            zipf.writestr('hash.txt', hash_str)

        logger.info(f"ZIP SAF-T assinado gerado: {zip_path}")
        return zip_path

    @staticmethod
    def salvar_xml(xml_str: str, empresa) -> str:
        """Salva o arquivo XML"""
        pasta = os.path.join(settings.MEDIA_ROOT, "saft", empresa.nome.replace(" ", "_"))
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, f"SAFT_{empresa.nif}_{timezone.now().strftime('%Y%m%d%H%M%S')}.xml")

        with open(caminho, "w", encoding="utf-8") as f:
            f.write(xml_str)

        return caminho



class FiscalDashboardService:
    """
    Serviço para métricas e dashboard fiscal
    """
    
    @staticmethod
    def obter_metricas_fiscais(empresa: Empresa, periodo: Tuple[date, date]) -> Dict:
        """
        Obtém métricas fiscais para dashboard
        
        Args:
            empresa: Empresa
            periodo: Tupla com data início e fim
            
        Returns:
            Dict com métricas fiscais
        """
        data_inicio, data_fim = periodo
        
        try:
            # Retenções no período
            retencoes = RetencaoFonte.objects.filter(
                empresa=empresa,
                data_retencao__range=[data_inicio, data_fim]
            )
            
            total_retencoes = sum(r.valor_retido for r in retencoes)
            retencoes_pagas = retencoes.filter(paga_ao_estado=True).count()
            retencoes_pendentes = retencoes.filter(paga_ao_estado=False).count()
            
            # Taxas ativas
            taxas_ativas = TaxaIVAAGT.objects.filter(empresa=empresa, ativo=True).count()
            
            # Documentos assinados
            assinatura = AssinaturaDigital.objects.filter(empresa=empresa).first()
            series_ativas = len(assinatura.dados_series_fiscais) if assinatura else 0
            
            metricas = {
                'retencoes': {
                    'total_valor': float(total_retencoes),
                    'total_count': retencoes.count(),
                    'pagas_count': retencoes_pagas,
                    'pendentes_count': retencoes_pendentes
                },
                'taxas': {
                    'ativas_count': taxas_ativas
                },
                'assinatura': {
                    'configurada': assinatura is not None,
                    'series_ativas': series_ativas,
                    'ultimo_hash': assinatura.ultimo_hash[:20] + '...' if assinatura and assinatura.ultimo_hash else None
                }
            }
            
            logger.info(
                f"Métricas fiscais calculadas",
                extra={
                    'empresa_id': empresa.id,
                    'periodo': f"{data_inicio} - {data_fim}",
                    'total_retencoes': float(total_retencoes)
                }
            )
            
            return metricas
            
        except Exception as e:
            logger.error(f"Erro ao calcular métricas fiscais: {e}")
            raise FiscalServiceError(f"Erro no cálculo: {e}")



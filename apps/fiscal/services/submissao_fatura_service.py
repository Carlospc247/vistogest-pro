# apps/fiscal/services/submissao_fatura_service.py
"""
Serviço de submissão de facturas à API AGT — endpoint /registarFactura.

Regras críticas:
- jwsDocumentSignature: assina os campos fiscais do documento com a chave DO CONTRIBUINTE
  via AssinaturaDigitalService.assinar_documento().
- jwsSignature: assina o payload da requisição (taxRegistrationNumber + submissionUUID)
  via AssinaturaDigitalService.assinar_requisicao().
- softwareInfo + jwsSoftwareSignature: montado por AssinaturaSoftwareService.montar_software_info()
  com a chave DA SOTARQ (nunca do contribuinte).
- Basic Auth: lida de AssinaturaDigital.api_username / api_password (decifrado via AESService).
- lineNumber: contador sequencial 1, 2, 3... por documento (nunca o ID do BD).
- Submissão é assíncrona: devolve requestID imediatamente; validação fiscal é diferida.
"""
import requests
import uuid
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

from apps.fiscal.services.assinatura_service import (
    AssinaturaDigitalService,
    AssinaturaSoftwareService,
)
from apps.fiscal.utility.crypto import AESService
from apps.fiscal.models import AssinaturaDigital
from .utils import FiscalServiceError

logger = logging.getLogger('fiscal.submissao')


class SubmissaoFaturaService:
    """
    Submete documentos fiscais à API AGT (/registarFactura).
    Isolamento físico: não recebe `empresa` como parâmetro — lê AssinaturaDigital
    do tenant activo (schema corrente).
    """

    def __init__(self):
        if settings.AGT_ENVIRONMENT == 'PRODUCTION':
            self.url = f"{settings.AGT_BASE_URL_PRODUCAO}/registarFactura"
        else:
            self.url = f"{settings.AGT_BASE_URL_HOMOLOGACAO}/registarFactura"

    # ------------------------------------------------------------------
    # Ponto de entrada principal
    # ------------------------------------------------------------------

    def submeter_documento(self, documento_fiscal):
        """
        Submete um DocumentoFiscal à AGT.
        `documento_fiscal` é uma instância de apps.fiscal.models.DocumentoFiscal.
        Devolve dict: {'success': True, 'requestID': '...'} ou {'success': False, 'error': '...'}.
        """
        config = AssinaturaDigital.obter_configuracao()
        if not config or not config.esta_configurada:
            raise FiscalServiceError(
                "Chave do contribuinte não configurada para este tenant. "
                "Configure-a em Configurações Fiscais."
            )

        try:
            document_node = self._montar_document_node(documento_fiscal, config)

            submission_uuid = str(uuid.uuid4())

            # Payload de assinatura da requisição: taxRegistrationNumber + submissionUUID
            payload_assinatura_req = {
                "taxRegistrationNumber": config.nif_contribuinte,
                "submissionUUID": submission_uuid,
            }
            jws_signature = AssinaturaDigitalService.assinar_requisicao(payload_assinatura_req)

            payload = {
                "schemaVersion": "2.0",
                "submissionUUID": submission_uuid,
                "taxRegistrationNumber": config.nif_contribuinte,
                "submissionTimeStamp": timezone.now().isoformat(),
                "softwareInfo": AssinaturaSoftwareService.montar_software_info(),
                "numberOfEntries": 1,
                "documents": [document_node],
                "jwsSignature": jws_signature,
            }

            credenciais = self._obter_credenciais(config)
            response = requests.post(
                self.url,
                json=payload,
                auth=(credenciais['username'], credenciais['password']),
                timeout=45,
            )
            return self._tratar_resposta(response, documento_fiscal)

        except FiscalServiceError:
            raise
        except Exception as e:
            logger.exception(f"Falha na submissão do documento {documento_fiscal.numero_documento}: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Compatibilidade retroactiva — aceita Venda directamente
    # ------------------------------------------------------------------

    def submeter_venda(self, venda):
        """
        Wrapper de compatibilidade para código que ainda usa a Venda directamente.
        Delega para submeter_documento usando o DocumentoFiscal ligado.
        """
        doc_fiscal = getattr(venda, 'documento_fiscal', None)
        if not doc_fiscal:
            raise FiscalServiceError(
                f"A Venda {venda.numero_documento} não tem DocumentoFiscal ligado. "
                "Chame venda.gerar_documento_fiscal(usuario) antes de submeter."
            )
        return self.submeter_documento(doc_fiscal)

    # ------------------------------------------------------------------
    # Montagem do nó "document"
    # ------------------------------------------------------------------

    def _montar_document_node(self, doc, config):
        """
        Constrói o objecto `document` conforme Decreto Executivo 683/25 — Anexo I.
        """
        # --- Campos para jwsDocumentSignature (Decreto, Anexo I) ---
        campos_assinatura = {
            "documentNo": doc.numero_documento,
            "taxRegistrationNumber": config.nif_contribuinte,
            "documentType": doc.tipo_documento,
            "documentDate": doc.data_emissao.isoformat(),
            "customerTaxID": doc.cliente_nif or "999999999",
            "customerCountry": "AO",
            "companyName": doc.cliente_nome or "Consumidor Final",
            "documentTotals": {
                "taxPayable": float(doc.valor_iva),
                "netTotal": float(doc.valor_base),
                "grossTotal": float(doc.valor_total),
            },
        }
        jws_doc_signature = AssinaturaDigitalService.assinar_documento(campos_assinatura)

        # --- Estado do documento ---
        document_status = "A" if doc.status == "cancelled" else "N"

        node = {
            "documentNo": doc.numero_documento,
            "documentStatus": document_status,
            "jwsDocumentSignature": jws_doc_signature,
            "documentDate": doc.data_emissao.isoformat(),
            "documentType": doc.tipo_documento,
            "eacCode": getattr(doc, 'eac_code', None) or getattr(
                settings, 'AGT_DEFAULT_EAC_CODE', '47110'),
            "systemEntryDate": doc.created_at.isoformat(),
            "customerCountry": "AO",
            "customerTaxID": doc.cliente_nif or "999999999",
            "companyName": doc.cliente_nome or "Consumidor Final",
            "documentTotals": {
                "taxPayable": float(doc.valor_iva),
                "netTotal": float(doc.valor_base),
                "grossTotal": float(doc.valor_total),
            },
        }

        # --- documentCancelReason (obrigatório quando anulado) ---
        if document_status == "A":
            motivo = getattr(doc, 'motivo_cancelamento_codigo', None) or "N"
            node["documentCancelReason"] = motivo

        # --- Currency (só quando moeda ≠ AOA) ---
        if doc.moeda and doc.moeda != "AOA":
            node["documentTotals"]["currency"] = {
                "currencyCode": doc.moeda,
                "currencyAmount": float(
                    doc.valor_total / doc.taxa_cambio if doc.taxa_cambio else doc.valor_total
                ),
                "exchangeRate": float(doc.taxa_cambio or 1),
            }

        # --- Linhas (obrigatório excepto para AR, RC, RG) ---
        tipos_sem_linhas = {"AR", "RC", "RG"}
        if doc.tipo_documento not in tipos_sem_linhas:
            node["lines"] = self._montar_linhas(doc)

        # --- paymentReceipt (só para AR, RC, RG) ---
        if doc.tipo_documento in tipos_sem_linhas:
            node["paymentReceipt"] = self._montar_payment_receipt(doc)

        # --- withholdingTaxList ---
        retencoes = self._montar_retencoes(doc)
        if retencoes:
            node["withholdingTaxList"] = retencoes

        return node

    def _montar_linhas(self, doc):
        """Constrói o array `lines` a partir das linhas do DocumentoFiscal."""
        from apps.fiscal.services.saft_mapping import mapear_withholding_tax_saft  # noqa — usado só para retenções

        linhas = []
        # Tentar obter as linhas a partir do relacionamento correcto (DocumentoFiscalLinha)
        linhas_qs = doc.linhas.all().order_by('numero_linha') if hasattr(doc, 'linhas') else []

        # Fallback: se não há linhas directas, tentar via Venda ligada
        if not linhas_qs:
            venda = getattr(doc, 'venda', None)
            if venda:
                return self._montar_linhas_de_venda(venda, doc)
            fatura = getattr(doc, 'fatura_credito', None)
            if fatura:
                return self._montar_linhas_de_fatura(fatura, doc)
            return []

        for idx, linha in enumerate(linhas_qs, start=1):
            line_node = {
                "lineNumber": idx,
                "productCode": linha.codigo_produto,
                "productDescription": linha.descricao,
                "quantity": float(linha.quantidade),
                "unitOfMeasure": getattr(linha, 'unidade', 'UN') or 'UN',
                "unitPriceBase": round(float(linha.valor_unitario), 4),
                "unitPrice": round(
                    float(linha.valor_unitario - (linha.desconto_linha or 0)), 4
                ),
                "creditAmount": float(linha.valor_sem_iva),
                "settlementAmount": float(self._calcular_settlement(linha, doc)),
                "taxes": self._montar_impostos_linha(linha),
            }
            # operationType (Decreto 683/25 — obrigatório)
            if hasattr(linha, 'operation_type') and linha.operation_type:
                line_node["operationType"] = linha.operation_type

            # referenceInfo por linha (NC)
            if doc.tipo_documento == "NC":
                ref = getattr(linha, 'referencia_documento_origem', None)
                if ref:
                    line_node["referenceInfo"] = {
                        "reference": ref,
                        "reason": getattr(linha, 'motivo_referencia', None) or "",
                    }

            linhas.append(line_node)

        return linhas

    def _montar_linhas_de_venda(self, venda, doc):
        """Fallback: constrói linhas a partir dos ItemVenda."""
        linhas = []
        for idx, item in enumerate(venda.itens.all().order_by('id'), start=1):
            p_code = item.produto.codigo_interno if item.produto else f"SRV-{item.servico.id}"
            p_desc = item.nome_produto if item.nome_produto else (
                item.produto.nome_produto if item.produto else
                (item.servico.nome if item.servico else "Item")
            )
            preco_base = float(item.preco_unitario)
            desconto_linha = float(item.desconto_item or 0)
            preco_com_desconto = round(preco_base - desconto_linha, 4)

            # settlementAmount = desconto de linha + proporção do desconto global
            settlement = self._calcular_settlement_venda(item, venda)

            taxes = []
            if item.taxa_iva:
                tax_node = {
                    "taxType": item.taxa_iva.tax_type or "IVA",
                    "taxCountryRegion": "AO",
                    "taxCode": item.taxa_iva.tax_code or "NOR",
                    "taxPercentage": float(item.taxa_iva.tax_percentage or 0),
                    "taxContribution": float(item.iva_valor or 0),
                }
                if float(item.taxa_iva.tax_percentage or 0) == 0 and item.taxa_iva.exemption_reason:
                    tax_node["taxExemptionCode"] = item.taxa_iva.exemption_reason
                taxes.append(tax_node)

            line_node = {
                "lineNumber": idx,
                "productCode": p_code,
                "productDescription": p_desc,
                "quantity": float(item.quantidade),
                "unitOfMeasure": "UN",
                "unitPriceBase": round(preco_base, 4),
                "unitPrice": preco_com_desconto,
                "creditAmount": float(item.subtotal_sem_iva or item.total),
                "settlementAmount": settlement,
                "taxes": taxes,
            }
            linhas.append(line_node)
        return linhas

    def _montar_linhas_de_fatura(self, fatura, doc):
        """Fallback: constrói linhas a partir dos ItemFatura."""
        linhas = []
        for idx, item in enumerate(fatura.itens.all().order_by('id'), start=1):
            preco_base = float(item.preco_unitario)
            desconto = float(item.desconto_item or 0)
            settlement = self._calcular_settlement_fatura(item, fatura)

            taxes = []
            if item.taxa_iva:
                tax_node = {
                    "taxType": item.taxa_iva.tax_type or "IVA",
                    "taxCountryRegion": "AO",
                    "taxCode": item.taxa_iva.tax_code or "NOR",
                    "taxPercentage": float(item.taxa_iva.tax_percentage or 0),
                    "taxContribution": float(item.iva_valor or 0),
                }
                if float(item.taxa_iva.tax_percentage or 0) == 0 and item.taxa_iva.exemption_reason:
                    tax_node["taxExemptionCode"] = item.taxa_iva.exemption_reason
                taxes.append(tax_node)

            linhas.append({
                "lineNumber": idx,
                "productCode": item.produto.codigo_interno if item.produto else f"SRV-{item.servico.id if item.servico else idx}",
                "productDescription": item.nome_item or "Item",
                "quantity": float(item.quantidade),
                "unitOfMeasure": "UN",
                "unitPriceBase": round(preco_base, 4),
                "unitPrice": round(preco_base - desconto, 4),
                "creditAmount": float(item.total or 0),
                "settlementAmount": settlement,
                "taxes": taxes,
            })
        return linhas

    def _montar_impostos_linha(self, linha):
        """Constrói o array `taxes` de uma DocumentoFiscalLinha."""
        taxa = getattr(linha, 'taxa_iva', None)
        if not taxa:
            return []
        tax_node = {
            "taxType": taxa.tax_type or "IVA",
            "taxCountryRegion": "AO",
            "taxCode": taxa.tax_code or "NOR",
            "taxPercentage": float(taxa.tax_percentage or 0),
            "taxContribution": float(getattr(linha, 'valor_iva', 0) or 0),
        }
        if float(taxa.tax_percentage or 0) == 0 and taxa.exemption_reason:
            tax_node["taxExemptionCode"] = taxa.exemption_reason
        return [tax_node]

    def _calcular_settlement(self, linha, doc):
        """
        SettlementAmount por linha = desconto de linha +
        proporção do desconto global (desconto_global * peso_linha_no_subtotal).
        """
        desconto_linha = float(getattr(linha, 'desconto_linha', 0) or 0)
        subtotal_doc = float(getattr(doc, 'valor_base', 0) or 0)
        desconto_global = float(getattr(doc, 'valor_desconto', 0) or 0)

        if subtotal_doc > 0 and desconto_global > 0:
            subtotal_linha = float(getattr(linha, 'valor_sem_iva', 0) or 0)
            proporcao = subtotal_linha / subtotal_doc
            return round(desconto_linha + desconto_global * proporcao, 4)
        return round(desconto_linha, 4)

    def _calcular_settlement_venda(self, item, venda):
        """SettlementAmount para linhas de Venda."""
        desconto_linha = float(item.desconto_item or 0)
        desconto_global = float(venda.desconto_valor or 0)
        subtotal_doc = float(venda.subtotal or 0)

        if subtotal_doc > 0 and desconto_global > 0:
            subtotal_linha = float(item.subtotal_sem_iva or (item.preco_unitario * item.quantidade))
            proporcao = float(subtotal_linha) / subtotal_doc
            return round(desconto_linha + desconto_global * proporcao, 4)
        return round(desconto_linha, 4)

    def _calcular_settlement_fatura(self, item, fatura):
        """SettlementAmount para linhas de FaturaCredito."""
        desconto_linha = float(item.desconto_item or 0)
        desconto_global = float(fatura.desconto_valor or 0)
        subtotal_doc = float(fatura.subtotal or 0)

        if subtotal_doc > 0 and desconto_global > 0:
            subtotal_linha = float(item.subtotal or (item.preco_unitario * item.quantidade))
            proporcao = float(subtotal_linha) / subtotal_doc
            return round(desconto_linha + desconto_global * proporcao, 4)
        return round(desconto_linha, 4)

    def _montar_payment_receipt(self, doc):
        """Constrói `paymentReceipt` para tipos AR, RC, RG."""
        # Tenta obter documentos de origem a partir do modelo ligado (Recibo)
        recibo = getattr(doc, 'recibo', None)
        source_docs = []
        if recibo and hasattr(recibo, 'fatura') and recibo.fatura:
            source_docs.append({
                "lineNo": 1,
                "sourceDocumentID": {
                    "originatingNo": recibo.fatura.numero_documento,
                    "documentDate": recibo.fatura.data_fatura.strftime('%Y-%m-%d'),
                },
                "creditAmount": float(doc.valor_total),
            })
        return {"sourceDocuments": source_docs}

    def _montar_retencoes(self, doc):
        """Constrói withholdingTaxList a partir das retenções do documento."""
        from apps.fiscal.services.saft_mapping import SAFT_WITHHOLDING_TAX_TYPE_MAP

        retencoes = []
        # Tenta obter retenções via Venda ligada
        venda = getattr(doc, 'venda', None)
        if venda:
            for ret in getattr(venda, 'retencoes', []):
                tipo = SAFT_WITHHOLDING_TAX_TYPE_MAP.get(ret.tipo_retencao, ret.tipo_retencao)
                retencoes.append({
                    "withholdingTaxType": tipo,
                    "withholdingTaxDescription": ret.codigo_tributario or "",
                    "withholdingTaxAmount": float(ret.valor_retido),
                })
        return retencoes

    # ------------------------------------------------------------------
    # Credenciais Basic Auth
    # ------------------------------------------------------------------

    def _obter_credenciais(self, config):
        """
        Lê as credenciais Basic Auth da AGT a partir de AssinaturaDigital.
        A password está cifrada com AESService — decifrar antes de usar.
        """
        username = config.api_username
        if not username:
            raise FiscalServiceError(
                "Username da API AGT não configurado. "
                "Aceda a Configurações Fiscais e insira as credenciais emitidas pela AGT."
            )
        password_cifrada = config.api_password
        if not password_cifrada:
            raise FiscalServiceError(
                "Password da API AGT não configurada. "
                "Aceda a Configurações Fiscais e insira as credenciais emitidas pela AGT."
            )
        password = AESService.decrypt(password_cifrada)
        return {"username": username, "password": password}

    # ------------------------------------------------------------------
    # Tratamento da resposta
    # ------------------------------------------------------------------

    def _tratar_resposta(self, response, doc):
        if response.status_code == 200:
            data = response.json()
            request_id = data.get('requestID')
            logger.info(f"Documento {doc.numero_documento} aceite pela AGT. RequestID: {request_id}")
            # Guardar requestID nos metadados do DocumentoFiscal
            if not doc.metadados:
                doc.metadados = {}
            doc.metadados['request_id_agt'] = request_id
            doc.metadados['submetido_em'] = timezone.now().isoformat()
            doc.save(update_fields=['metadados'])
            return {"success": True, "requestID": request_id}
        else:
            logger.error(
                f"Erro AGT na submissão de {doc.numero_documento}: "
                f"HTTP {response.status_code} — {response.text[:500]}"
            )
            try:
                erro_json = response.json()
            except Exception:
                erro_json = {"raw": response.text}
            return {
                "success": False,
                "error": erro_json,
                "code": response.status_code,
            }

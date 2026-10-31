# apps/fiscal/services/submissao_fatura_service.py
"""
Serviço de submissão de facturas à API AGT — endpoint /registarFactura.

A comunicação HTTP (Basic Auth do produtor lido do .env, softwareInfo,
jwsSignature, timeouts) está no AGTClient. Este serviço:
  * monta o nó `document` (Decreto Executivo 683/25 — Anexo I);
  * assina os campos do documento com a chave DO CONTRIBUINTE
    (AssinaturaDigitalService.assinar_documento → jwsDocumentSignature);
  * persiste em `metadados` do DocumentoFiscal o submissionUUID ANTES de
    enviar (para repetir a mesma submissão sem duplicar) e o requestID depois.

Submissão é assíncrona: devolve requestID; a validação fiscal vem depois via
obterEstado (FiscalPollingService).

Campos usados de DocumentoFiscalLinha: codigo_produto, descricao, unidade,
quantidade, preco_unitario, valor_desconto_linha (TOTAL da linha),
valor_liquido (qtd x preço - desconto), taxa_iva, valor_iva_linha.
"""
import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
import requests

from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.services.agt_client import AGTClient, AGTError
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, AssinaturaSoftwareService
from .utils import FiscalServiceError

logger = logging.getLogger('fiscal.submissao')

_CENTIMO = Decimal("0.01")


def _f2(valor) -> float:
    return float(Decimal(valor or 0).quantize(_CENTIMO))


class SubmissaoFaturaService:
    """
    Submete documentos fiscais à API AGT (/registarFactura).
    Isolamento físico: não recebe `empresa` — lê AssinaturaDigital do tenant activo.
    """

    def __init__(self, client: AGTClient = None):
        self.client = client or AGTClient()

    """
    def submeter_documento(self, documento_fiscal):
        #Prepara/captura o payload e submete o documento à AGT.
        from apps.fiscal.services.payload_inspector import PayloadInspectorService

        captura = None
        tentativa_http = False
        ambiente = getattr(settings, "AGT_ENVIRONMENT", "HOMOLOGACAO")
        config = None

        try:
            config = AssinaturaDigital.obter_configuracao()
            if not config or not config.esta_configurada:
                raise FiscalServiceError(
                    "Chave do contribuinte não configurada para este tenant. "
                    "Configure-a em Configurações Fiscais."
                )

            document_node = self._montar_document_node(documento_fiscal, config)
            submission_uuid = str(uuid.uuid4())

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

            # Capturar o corpo exacto do pedido antes de tentar obter Basic Auth.
            # A falha do Inspector nunca deve bloquear o fluxo normal de submissão.
            try:
                captura = PayloadInspectorService.registar_payload(
                    payload=payload,
                    endpoint=self.url,
                    ambiente=ambiente,
                )
            except Exception:
                logger.exception(
                    "Não foi possível guardar o payload AGT do documento %s no Inspector.",
                    documento_fiscal.numero_documento,
                )

            # As credenciais ainda podem não ter sido emitidas/configuradas pela AGT.
            credenciais = self._obter_credenciais(config)

            if captura:
                try:
                    PayloadInspectorService.marcar_enviado(captura)
                except Exception:
                    logger.exception("Falha ao actualizar o estado do payload AGT #%s.", captura.pk)

            # Depois deste ponto o pedido pode ter saído do processo, mesmo se ocorrer timeout.
            tentativa_http = True
            response = requests.post(
                self.url,
                json=payload,
                auth=(credenciais["username"], credenciais["password"]),
                timeout=45,
            )

            if captura:
                try:
                    PayloadInspectorService.registar_resposta(captura, response)
                except Exception:
                    logger.exception("Falha ao guardar a resposta do payload AGT #%s.", captura.pk)

            return self._tratar_resposta(response, documento_fiscal)

        except FiscalServiceError as exc:
            if captura:
                try:
                    PayloadInspectorService.marcar_falha(captura, exc, pedido_enviado=tentativa_http)
                except Exception:
                    logger.exception("Falha ao registar erro do payload AGT #%s.", captura.pk)
            else:
                # Regista que a preparação falhou; payload={} significa que não existia JSON completo.
                try:
                    PayloadInspectorService.registar_erro_preparacao(
                        documento=documento_fiscal,
                        erro=exc,
                        endpoint=self.url,
                        ambiente=ambiente,
                    )
                except Exception:
                    logger.exception("Falha ao registar erro de preparação do payload AGT.")
            raise

        except Exception as exc:
            logger.exception(
                "Falha na submissão do documento %s: %s",
                getattr(documento_fiscal, "numero_documento", "(sem número)"),
                exc,
            )
            if captura:
                try:
                    PayloadInspectorService.marcar_falha(captura, exc, pedido_enviado=tentativa_http)
                except Exception:
                    logger.exception("Falha ao registar erro do payload AGT #%s.", captura.pk)
            else:
                try:
                    PayloadInspectorService.registar_erro_preparacao(
                        documento=documento_fiscal,
                        erro=exc,
                        endpoint=self.url,
                        ambiente=ambiente,
                    )
                except Exception:
                    logger.exception("Falha ao registar erro de preparação do payload AGT.")
            return {"success": False, "error": str(exc)}
    """
        
    def submeter_documento(self, documento_fiscal):
        """
        Compatibilidade com os módulos antigos.
        A construção, captura e submissão são encaminhadas para o fluxo central.
        """

        from apps.fiscal.services.submissao_documento_agt import (
            submeter_documento_agt,
        )

        return submeter_documento_agt(
            documento=documento_fiscal,
            cliente_agt=self.client,
        )


    
    def submeter_venda(self, venda):
        """Compatibilidade: delega para submeter_documento via DocumentoFiscal ligado."""
        doc_fiscal = getattr(venda, 'documento_fiscal', None)
        if not doc_fiscal:
            raise FiscalServiceError(
                f"A Venda {venda.numero_documento} não tem DocumentoFiscal ligado. "
                "Chame venda.gerar_documento_fiscal(usuario) antes de submeter."
            )
        return self.submeter_documento(doc_fiscal)

    @staticmethod
    def _registar_sucesso(doc, resultado, estado_envio):
        meta = doc.metadados if isinstance(doc.metadados, dict) else {}
        meta["request_id_agt"] = resultado["requestID"]
        meta["submission_uuid_agt"] = resultado["submissionUUID"]
        meta["estado_submetido"] = estado_envio
        meta["submetido_em"] = timezone.now().isoformat()
        doc.metadados = meta
        doc.save(update_fields=['metadados'])
        logger.info("Documento %s aceite pela AGT. RequestID: %s",
                    doc.numero_documento, resultado["requestID"])
        return {"success": True, "requestID": resultado["requestID"]}

    # ------------------------------------------------------------------
    # Montagem do nó "document"
    # ------------------------------------------------------------------

    @staticmethod
    def _totais(doc) -> dict:
        return {
            "taxPayable": _f2(doc.valor_iva),
            "netTotal": _f2(doc.valor_base),
            "grossTotal": _f2(doc.valor_total),
        }

    def _verificar_coerencia(self, doc, totais):
        """Avisa (não bloqueia) se as linhas não somam os totais do documento."""
        try:
            linhas = list(doc.linhas.all())
        except Exception:
            return
        if not linhas:
            return
        net = sum((l.valor_liquido or 0) for l in linhas)
        iva = sum((l.valor_iva_linha or 0) for l in linhas)
        if abs(float(net) - totais["netTotal"]) > 0.05 or abs(float(iva) - totais["taxPayable"]) > 0.05:
            logger.warning(
                "Documento %s: totais incoerentes com as linhas "
                "(linhas net=%.2f iva=%.2f | documento net=%.2f iva=%.2f). "
                "A AGT pode rejeitar.", doc.numero_documento, net, iva,
                totais["netTotal"], totais["taxPayable"],
            )

    def _montar_document_node(self, doc, config):
        """Constrói o objecto `document` — Decreto Executivo 683/25, Anexo I."""
        totais = self._totais(doc)
        self._verificar_coerencia(doc, totais)

        nif_cliente = doc.cliente_nif or "999999999"
        nome_cliente = doc.cliente_nome or "Consumidor Final"

        # Campos de jwsDocumentSignature, NA ORDEM do Anexo I.
        campos_assinatura = {
            "documentNo": doc.numero_documento,
            "taxRegistrationNumber": config.nif_contribuinte,
            "documentType": doc.tipo_documento,
            "documentDate": doc.data_emissao.isoformat(),
            "customerTaxID": nif_cliente,
            "customerCountry": "AO",
            "companyName": nome_cliente,
            "documentTotals": dict(totais),
        }
        jws_doc_signature = AssinaturaDigitalService.assinar_documento(campos_assinatura)

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
            "customerTaxID": nif_cliente,
            "companyName": nome_cliente,
            "documentTotals": dict(totais),
        }

        if document_status == "A":
            node["documentCancelReason"] = (
                getattr(doc, 'motivo_cancelamento_codigo', None) or "N")

        if doc.moeda and doc.moeda != "AOA":
            taxa = doc.taxa_cambio or Decimal("1")
            node["documentTotals"]["currency"] = {
                "currencyCode": doc.moeda,
                "currencyAmount": _f2(Decimal(doc.valor_total or 0) / taxa),
                "exchangeRate": float(taxa),
            }

        tipos_sem_linhas = {"AR", "RC", "RG"}
        if doc.tipo_documento in tipos_sem_linhas:
            node["paymentReceipt"] = self._montar_payment_receipt(doc)
        else:
            node["lines"] = self._montar_linhas(doc)

        retencoes = self._montar_retencoes(doc)
        if retencoes:
            node["withholdingTaxList"] = retencoes
        return node

    @staticmethod
    def _tax_code_api(taxa):
        """A API AGT usa taxCode=ISE para taxType=NS; o catálogo interno/SAF-T mantém NS."""
        if not taxa:
            return "NOR"
        if getattr(taxa, "tax_type", None) == "NS":
            return "ISE"
        return getattr(taxa, "tax_code", None) or "NOR"
    

    def _montar_linhas(self, doc):
        """Constrói `lines` a partir das DocumentoFiscalLinha."""
        linhas_qs = list(doc.linhas.all().order_by('numero_linha')) if hasattr(doc, 'linhas') else []

        # Fallback: documento sem linhas próprias -> Venda / FaturaCredito ligadas.
        if not linhas_qs:
            venda = getattr(doc, 'venda', None)
            if venda:
                return self._montar_linhas_de_venda(venda, doc)
            fatura = getattr(doc, 'fatura_credito', None)
            if fatura:
                return self._montar_linhas_de_fatura(fatura, doc)
            return []

        linhas = []
        for idx, linha in enumerate(linhas_qs, start=1):
            qtd = Decimal(linha.quantidade or 0)
            desconto_total = Decimal(linha.valor_desconto_linha or 0)
            preco = Decimal(linha.preco_unitario or 0)
            desconto_unit = (desconto_total / qtd) if qtd else Decimal("0")

            line_node = {
                "lineNumber": idx,
                "productCode": linha.codigo_produto,
                "productDescription": linha.descricao,
                "quantity": float(qtd),
                "unitOfMeasure": getattr(linha, 'unidade', 'UN') or 'UN',
                "unitPriceBase": round(float(preco), 4),
                "unitPrice": round(float(preco - desconto_unit), 4),
                "creditAmount": _f2(linha.valor_liquido),
                "settlementAmount": _f2(desconto_total),
                "taxes": self._montar_impostos_linha(linha),
            }
            if getattr(linha, 'operation_type', None):
                line_node["operationType"] = linha.operation_type

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
                    "taxCode": self._tax_code_api(item.taxa_iva),
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
                    "taxCode": self._tax_code_api(item.taxa_iva),
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
        """Constrói `taxes` de uma DocumentoFiscalLinha."""
        taxa = getattr(linha, 'taxa_iva', None)
        if not taxa:
            return []
        tax_node = {
            "taxType": taxa.tax_type or "IVA",
            "taxCountryRegion": "AO",
            "taxCode": self._tax_code_api(taxa),
            "taxPercentage": float(taxa.tax_percentage or 0),
            "taxContribution": _f2(getattr(linha, 'valor_iva_linha', 0)),
        }
        if float(taxa.tax_percentage or 0) == 0 and taxa.exemption_reason:
            tax_node["taxExemptionCode"] = taxa.exemption_reason
        return [tax_node]

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
        """Constrói withholdingTaxList a partir das retenções da Venda ligada."""
        from apps.fiscal.services.saft_mapping import SAFT_WITHHOLDING_TAX_TYPE_MAP

        venda = getattr(doc, 'venda', None)
        if not venda:
            return []
        origem = getattr(venda, 'retencoes', None)
        itens = origem.all() if hasattr(origem, 'all') else (origem or [])

        retencoes = []
        for ret in itens:
            tipo = SAFT_WITHHOLDING_TAX_TYPE_MAP.get(ret.tipo_retencao, ret.tipo_retencao)
            retencoes.append({
                "withholdingTaxType": tipo,
                "withholdingTaxDescription": ret.codigo_tributario or "",
                "withholdingTaxAmount": _f2(ret.valor_retido),
            })
        return retencoes
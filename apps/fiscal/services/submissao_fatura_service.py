# apps/fiscal/services/submissao_fatura_service.py
import requests
import uuid
import logging
from django.conf import settings
from django.utils import timezone
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService

logger = logging.getLogger('fiscal.submissao')

class SubmissaoFaturaService:
    """
    Serviço para submeter facturas à API da AGT via JWS.
    Conforme Manual de Integração - Endpoint /registarFactura
    """

    def __init__(self, empresa):
        self.empresa = empresa
        self.config = getattr(empresa, 'configuracao_integracao', None)
        # Seleção de URL baseada no .env mapeado no settings
        if settings.AGT_ENVIRONMENT == 'PRODUCTION':
            self.url = "https://sifp.minfin.gov.ao/sigt/fe/v1/registarFactura"
        else:
            self.url = "https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura"

    def submeter_venda(self, venda):
        """
        Transforma a Venda em JSON, assina e envia para a AGT.
        """
        try:
            # 1. Montar o Objeto de Dados da Factura (Document Payload)
            document_data = self._montar_payload_documento(venda)

            # 2. Gerar jwsDocumentSignature (Assinatura do Documento)
            # Regra AGT: Assinar o objeto document_data completo
            jws_document_signature = AssinaturaDigitalService.gerar_jws(self.empresa, document_data)

            # 3. Montar o Payload Principal da Requisição
            submission_uuid = str(uuid.uuid4())
            payload_principal = {
                "schemaVersion": "1.2",
                "submissionUUID": submission_uuid,
                "taxRegistrationNumber": self.empresa.nif,
                "submissionTimeStamp": timezone.now().isoformat(),
                "softwareInfo": {
                    "softwareInfoDetail": {
                        "productId": settings.AGT_SOFTWARE_NAME,
                        "productVersion": settings.AGT_SOFTWARE_VERSION,
                        "softwareValidationNumber": settings.AGT_CERTIFICATE_NUMBER
                    },
                    "jwsSoftwareSignature": settings.AGT_JWS_SOFTWARE_SIGNATURE
                },
                "numberOfEntries": 1,
                "documents": [
                    {
                        **document_data,
                        "jwsDocumentSignature": jws_document_signature
                    }
                ]
            }

            # 4. Gerar jwsSignature (Assinatura da Requisição completa)
            # Payload para esta assinatura: taxRegistrationNumber + submissionUUID
            payload_req_signature = {
                "taxRegistrationNumber": self.empresa.nif,
                "submissionUUID": submission_uuid
            }
            payload_principal["jwsSignature"] = AssinaturaDigitalService.gerar_jws(self.empresa, payload_req_signature)

            # 5. Enviar via POST (Basic Auth)
            credenciais = self.config.get_credenciais()
            response = requests.post(
                self.url,
                json=payload_principal,
                auth=(credenciais['username'], credenciais['password']),
                timeout=45
            )

            return self._tratar_resposta(response, venda)

        except Exception as e:
            logger.exception(f"Falha na submissão da venda {venda.numero_documento}: {e}")
            return {"success": False, "error": str(e)}

    def _montar_payload_documento(self, venda):
        """Helper para estruturar o nó 'document' conforme Anexo 5.1.2.2 do manual."""
        lines = []
        for item in venda.itens.all():
            line = {
                "lineNumber": item.id, # No deploy usar contador sequencial 1,2,3
                "productCode": item.produto.codigo_interno if item.produto else f"SRV-{item.servico.id}",
                "productDescription": item.nome_produto if item.produto else item.nome_servico,
                "quantity": float(item.quantidade),
                "unitOfMeasure": "UN",
                "unitPrice": float(item.preco_unitario),
                "unitPriceBase": float(item.preco_unitario),
                "creditAmount": float(item.subtotal_sem_iva),
                "taxes": [{
                    "taxType": item.tax_type or "IVA",
                    "taxCountryRegion": "AO",
                    "taxCode": item.tax_code or "NOR",
                    "taxPercentage": float(item.iva_percentual),
                    "taxContribution": float(item.iva_valor)
                }],
                "settlementAmount": float(item.desconto_item)
            }
            lines.append(line)

        return {
            "documentNo": venda.numero_documento,
            "documentStatus": "N",
            "documentDate": venda.data_venda.strftime('%Y-%m-%d'),
            "documentType": "FR", # Fatura-Recibo
            "systemEntryDate": venda.created_at.strftime('%Y-%m-%dT%H:%M:%S'),
            "customerTaxID": venda.cliente.nif if venda.cliente and venda.cliente.nif else "999999999",
            "customerCountry": "AO",
            "companyName": venda.cliente.nome_completo if venda.cliente else "Consumidor Final",
            "lines": lines,
            "documentTotals": {
                "taxPayable": float(venda.iva_valor),
                "netTotal": float(venda.subtotal),
                "grossTotal": float(venda.total)
            }
        }

    def _tratar_resposta(self, response, venda):
        if response.status_code == 200:
            data = response.json()
            request_id = data.get('requestID')
            # Salva o RequestID para o serviço de Polling consultar depois
            venda.metadados['request_id_agt'] = request_id
            venda.save()
            return {"success": True, "requestID": request_id}
        else:
            logger.error(f"Erro AGT Submissão: {response.text}")
            return {"success": False, "error": response.text, "code": response.status_code}
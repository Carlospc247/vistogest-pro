# apps/fiscal/services/polling_service.py
import requests
import logging
from django.conf import settings
from django.utils import timezone
from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService

logger = logging.getLogger('fiscal')

class FiscalPollingService:
    """
    Serviço de alta integridade para consulta de estado assíncrono na AGT.
    Implementa as regras de conformidade do Manual de Integração Angolano.
    """
    
    def __init__(self, empresa):
        self.empresa = empresa
        self.config = getattr(empresa, 'configuracao_integracao', None)
        
        # DECISÃO TÉCNICA: Alternância dinâmica de ambiente via .env/Settings
        # Referência: Padrão 12-Factor App para isolamento de infraestrutura.
        if settings.AGT_ENVIRONMENT == 'PRODUCTION':
            self.url = "https://sifp.minfin.gov.ao/sigt/fe/v1/obterEstado"
        else:
            self.url = "https://sifphml.minfin.gov.ao/sigt/fe/v1/obterEstado"
        
    def consultar_estado_documento(self, request_id):
        """
        Inicia a consulta à API da AGT usando o Identificador de Pedido (RequestID).
        """
        if not request_id:
            logger.error(f"Tentativa de polling sem RequestID para empresa {self.empresa.id}")
            return None

        # 1. Construção do Payload rigorosamente conforme Anexo Técnico AGT
        payload = {
            "schemaVersion": "1.2",
            "taxRegistrationNumber": self.empresa.nif,
            "requestID": request_id,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": {
                "softwareInfoDetail": {
                    "productId": settings.AGT_SOFTWARE_NAME,
                    "productVersion": settings.AGT_SOFTWARE_VERSION,
                    "softwareValidationNumber": settings.AGT_CERTIFICATE_NUMBER
                }
            }
        }

        # 2. Assinatura da Requisição (JWS Signature)
        # Campos obrigatórios para o payload de assinatura: taxRegistrationNumber + requestID
        payload_assinatura = {
            "taxRegistrationNumber": self.empresa.nif,
            "requestID": request_id
        }
        payload["jwsSignature"] = AssinaturaDigitalService.gerar_jws(self.empresa, payload_assinatura)

        # 3. Execução da Chamada REST (Basic Auth per-tenant)
        try:
            # Obtém credenciais decifradas em memória (AES-256)
            credenciais = self.config.get_credenciais()
            
            response = requests.post(
                self.url,
                json=payload,
                auth=(credenciais['username'], credenciais['password']),
                timeout=30
            )
            
            if response.status_code == 200:
                return self._processar_resposta_agt(response.json(), request_id)
            else:
                logger.error(f"Erro Crítico API AGT Polling [{response.status_code}]: {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.exception(f"Falha de rede na conexão com AGT (Polling): {e}")
            return False

    def _processar_resposta_agt(self, data, request_id):
        """
        Analisa o resultCode e aplica lógica de negócio:
        - 0/1/2: Processamento concluído (Válido ou Inválido).
        - 8: Em curso (Aguardar próximo ciclo do Celery).
        """
        result_code = str(data.get('resultCode'))
        
        # Conforme Manual: 8 indica que o processamento em Batch ainda não terminou.
        if result_code == "8":
            return "PROCESSING"

        # Itera sobre a lista de documentos para atualização individual de status
        document_status_list = data.get('documentStatusList', [])
        
        for doc_status in document_status_list:
            doc_no = doc_status.get('documentNo')
            status_agt = doc_status.get('documentStatus') # V = Válido | I = Inválido
            
            try:
                # Busca documento garantindo isolamento multi-tenant
                doc_fiscal = DocumentoFiscal.objects.get(
                    empresa=self.empresa, 
                    numero_documento=doc_no
                )
                
                if status_agt == 'V':
                    # Documento Aceite pela Administração Tributária
                    doc_fiscal.status = 'posted' 
                    doc_fiscal.metadados['validacao_agt'] = data
                    logger.info(f"Documento {doc_no} validado com sucesso pela AGT.")
                else:
                    # CASO DE REJEIÇÃO: Implementação de contingência e alerta
                    doc_fiscal.status = 'cancelled'
                    lista_erros = doc_status.get('errorList', [])
                    doc_fiscal.metadados['erros_agt'] = lista_erros
                    
                    # NOTIFICAÇÃO EM TEMPO REAL VIA WHATSAPP (Critical Alert)
                    # Decisão Técnica: Notificar imediatamente para correção dentro do prazo legal.
                    try:
                        from apps.fiscal.services.whatsapp_service import FiscalWhatsAppService
                        ws_service = FiscalWhatsAppService(self.empresa)
                        ws_service.enviar_alerta_rejeicao(doc_fiscal, lista_erros)
                    except Exception as ws_err:
                        logger.error(f"Falha ao enviar notificação WhatsApp: {ws_err}")
                
                doc_fiscal.save()

            except DocumentoFiscal.DoesNotExist:
                logger.warning(f"Documento {doc_no} (RequestID {request_id}) retornado pela AGT mas inexistente no BD local.")

        return "FINISHED"
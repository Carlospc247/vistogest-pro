# apps/fiscal/services/whatsapp_service.py
import requests
import logging
from django.conf import settings

logger = logging.getLogger('fiscal.whatsapp')

class FiscalWhatsAppService:
    """
    Serviço Enterprise para notificações críticas de faturamento via WhatsApp Cloud API.
    Focado em alertar rejeições da AGT em tempo real.
    """

    def __init__(self, empresa):
        self.empresa = empresa
        self.url = settings.WHATSAPP_API_URL
        self.token = settings.WHATSAPP_API_TOKEN
        # O telefone do gestor deve estar configurado no cadastro da Empresa
        self.telefone_gestor = getattr(empresa, 'telefone_alertas_fiscal', None)

    def enviar_alerta_rejeicao(self, documento, erros):
        """
        Envia uma mensagem formatada com os códigos de erro retornados pela AGT.
        """
        if not self.telefone_gestor or not self.token:
            logger.error(f"Configuração de WhatsApp pendente para a empresa {self.empresa.nome}")
            return False

        # Formatação dos erros para leitura rápida no celular
        detalhes_msg = ""
        for err in erros:
            detalhes_msg += f"• *{err.get('errorCode')}*: {err.get('errorDescription')}\n"

        mensagem = (
            f"🚨 *ALERTA FISCAL - SOTARQ VENDOR*\n\n"
            f"Atenção, Gestor da *{self.empresa.nome}*.\n"
            f"O documento *{documento.numero_documento}* foi *REJEITADO* pela AGT.\n\n"
            f"*ERROS DETECTADOS:*\n{detalhes_msg}\n"
            f"⚠️ *Ação Necessária:* Corrija os dados no sistema e emita um novo documento para evitar multas."
        )

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": self.telefone_gestor,
            "type": "text",
            "text": {"body": mensagem}
        }

        try:
            response = requests.post(self.url, json=payload, headers=headers, timeout=20)
            if response.status_code in [200, 201]:
                logger.info(f"Notificação de rejeição enviada com sucesso para {self.empresa.nome}")
                return True
            else:
                logger.error(f"Erro na API do WhatsApp ({response.status_code}): {response.text}")
                return False
        except Exception as e:
            logger.exception(f"Falha de conexão com serviço de WhatsApp: {e}")
            return False

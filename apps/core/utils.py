# apps/core/utils.py
import logging

import requests
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


def get_current_user():
    """
    Retorna o utilizador da requisição atual capturado pelo Middleware.
    Utilizado pelos signals de Auditoria para identificar o autor da ação.
    """
    from apps.core.middleware import get_current_authenticated_user
    user = get_current_authenticated_user()

    # Se o usuário estiver autenticado (não for AnonymousUser), retorna o objeto
    if user and user.is_authenticated:
        return user
    return None


def get_user_empresa(user):
    """
    Retorna a Empresa/Tenant ativo para o utilizador, baseado no schema
    atual da conexão (django_tenants) — não num FK no model Usuario.

    Confirma também que o utilizador tem acesso a esse tenant, quando
    a relação 'tenants' existir no model de utilizador.
    """
    tenant = getattr(connection, 'tenant', None)

    if not tenant or getattr(tenant, 'schema_name', 'public') == 'public':
        return None

    if user and hasattr(user, 'tenants'):
        if not user.tenants.filter(pk=tenant.pk).exists():
            return None

    return tenant


class WhatsAppService:
    def __init__(self):
        self.token = settings.WHATSAPP_API_TOKEN
        self.url_base = settings.WHATSAPP_API_URL  # Ex: https://graph.facebook.com/v23.0/ID_TELEFONE/messages
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def enviar_documento(self, telefone, pdf_content, filename):
        """
        1. Faz upload do PDF para a Meta
        2. Envia o documento para o cliente
        """
        try:
            # Higienizar telefone (deve ter código do país 244...)
            telefone = str(telefone).replace("+", "").replace(" ", "")

            # Passo A: Upload do Media
            upload_url = self.url_base.replace("/messages", "/media")
            files = {
                'file': (filename, pdf_content, 'application/pdf'),
            }
            data = {
                "messaging_product": "whatsapp",
                "type": "application/pdf"
            }

            response_upload = requests.post(
                upload_url,
                headers={"Authorization": f"Bearer {self.token}"},
                files=files,
                data=data
            )
            media_id = response_upload.json().get('id')

            if not media_id:
                logger.error(f"Erro no upload WhatsApp: {response_upload.text}")
                return False

            # Passo B: Enviar Mensagem com o Documento
            payload = {
                "messaging_product": "whatsapp",
                "to": telefone,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": filename
                }
            }

            response_send = requests.post(self.url_base, headers=self.headers, json=payload)
            return response_send.status_code == 200

        except Exception as e:
            logger.error(f"Falha crítica WhatsApp Service: {str(e)}")
            return False
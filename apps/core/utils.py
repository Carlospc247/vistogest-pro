# apps/core/utils.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import black, darkblue
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from django.core.exceptions import PermissionDenied
import io
import qrcode
from PIL import Image
from django.conf import settings
from django.utils import timezone
import uuid
import requests
import json
import logging
from django.conf import settings




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
    Retorna a empresa associada ao utilizador autenticado.
    Lógica multi-tenant centralizada.
    """
    if not user or not user.is_authenticated:
        return None

    empresa = getattr(user, 'empresa', None)

    if not empresa and hasattr(user, 'usuario'):
        empresa = getattr(user.usuario, 'empresa', None)

    if not empresa and hasattr(user, 'funcionario'):
        empresa = getattr(user.funcionario, 'empresa', None)

    if not empresa and not user.is_superuser:
        raise PermissionDenied("Utilizador não associado a nenhuma empresa.")

    return empresa



logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        self.token = settings.WHATSAPP_API_TOKEN
        self.url_base = settings.WHATSAPP_API_URL # Ex: https://graph.facebook.com/v23.0/ID_TELEFONE/messages
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


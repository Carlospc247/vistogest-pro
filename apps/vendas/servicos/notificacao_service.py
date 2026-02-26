#apps/vendas/servicos/notificacao_service.py
from django.core.mail import EmailMessage
from django.conf import settings
from apps.core.utils import WhatsAppService
from apps.funcionarios.models import Funcionario

import logging

logger = logging.getLogger(__name__)

class NotificacaoVendaService:
    @staticmethod
    def disparar_todas(venda, email_avulso=None, whats_avulso=None):
        """
        RIGOR SOTARQ: Dispara notificações para Cliente e Diretoria.
        Trata valores NULL e erros de rede sem travar o PDV.
        """
        try:
            # 1. Preparar PDF (Reutiliza o motor AGT)
            from apps.fiscal.services.pdf_agt_service import PDFDocumentoService
            pdf_service = PDFDocumentoService(venda)
            pdf_buffer = pdf_service.gerar()
            pdf_content = pdf_buffer.getvalue()
            filename = f"{venda.numero_documento}.pdf"

            # --- FLUXO DE E-MAIL ---
            diretoria_email = Funcionario.objects.filter(
                empresa=venda.empresa, 
                ativo=True, 
                recebe_copia_faturamento_email=True
            ).values_list('email_corporativo', flat=True)
            
            emails_destino = list(filter(None, diretoria_email))
            
            # Email do cliente cadastrado ou digitado na hora
            email_cli = email_avulso or (venda.cliente.email if venda.cliente else None)
            if email_cli:
                emails_destino.append(email_cli)

            if emails_destino:
                msg = EmailMessage(
                    subject=f"Documento Fiscal: {venda.numero_documento} | {venda.empresa.nome}",
                    body=f"Olá,\n\nSegue em anexo o documento fiscal referente à transação.\nTotal: {venda.total} Kz",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=emails_destino
                )
                msg.attach(filename, pdf_content, 'application/pdf')
                msg.send(fail_silently=True)

            # --- FLUXO DE WHATSAPP ---
            ws = WhatsAppService()
            
            # Enviar para Cliente
            whats_cli = whats_avulso or (venda.cliente.telefone if venda.cliente else None)
            if whats_cli:
                ws.enviar_documento(whats_cli, pdf_content, filename)
            
            # Enviar para Diretores Fiscais
            diretores_whats = Funcionario.objects.filter(
                empresa=venda.empresa, 
                ativo=True, 
                recebe_copia_faturamento_whatsapp=True
            )
            for d in diretores_whats:
                num = d.whatsapp or d.telefone
                if num:
                    ws.enviar_documento(num, pdf_content, filename)

        except Exception as e:
            logger.error(f"Erro ao disparar notificações da venda {venda.id}: {str(e)}")
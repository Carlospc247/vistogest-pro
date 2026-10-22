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
                ativo=True, 
                recebe_copia_faturamento_whatsapp=True
            )
            for d in diretores_whats:
                num = d.whatsapp or d.telefone
                if num:
                    ws.enviar_documento(num, pdf_content, filename)

        except Exception as e:
            logger.error(f"Erro ao disparar notificações da venda {venda.id}: {str(e)}")
    

"""Notificações opcionais de Proforma e Fatura a Crédito, com PDF anexado.

WhatsApp fica ligado através da configuração VISTOGEST_WHATSAPP_DOCUMENT_SENDER,
um callable importável que aceite os argumentos documentados no README.
"""
from __future__ import annotations

import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class NotificacaoDocumentoService:
    MODELOS = {
        "proforma": ("apps.vendas.models", "FaturaProforma", "FP"),
        "fatura_credito": ("apps.vendas.models", "FaturaCredito", "FT"),
    }

    @classmethod
    def disparar(cls, *, tipo_documento, documento_id, email_destino=None, whatsapp_destino=None):
        """Tenta cada canal em separado; falha numa notificação não altera o documento."""
        import importlib
        from apps.fiscal.services.pdf_agt_service import PDFDocumentoService

        if tipo_documento not in cls.MODELOS:
            raise ValueError(f"Tipo de documento não suportado: {tipo_documento}")
        module_name, class_name, prefix = cls.MODELOS[tipo_documento]
        model = getattr(importlib.import_module(module_name), class_name)
        documento = model.objects.select_related("cliente").get(pk=documento_id)
        resultado = {"email": "não solicitado", "whatsapp": "não solicitado"}

        if not email_destino and not whatsapp_destino:
            return resultado

        pdf_buffer = PDFDocumentoService(documento).gerar()
        if hasattr(pdf_buffer, "getvalue"):
            pdf_bytes = pdf_buffer.getvalue()
        else:
            pdf_buffer.seek(0)
            pdf_bytes = pdf_buffer.read()
        numero = str(getattr(documento, "numero_documento", "") or documento.pk)
        safe_number = numero.replace("/", "_").replace(" ", "_")
        filename = f"{prefix}_{safe_number}.pdf"

        if email_destino:
            try:
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
                if not from_email:
                    raise ImproperlyConfigured("DEFAULT_FROM_EMAIL não está configurado.")
                message = EmailMessage(
                    subject=f"{prefix} {numero} — documento comercial",
                    body=(
                        f"Segue em anexo o documento {numero}.\n\n"
                        "Esta mensagem foi enviada pelo sistema de facturação da empresa."
                    ),
                    from_email=from_email,
                    to=[email_destino],
                )
                message.attach(filename, pdf_bytes, "application/pdf")
                message.send(fail_silently=False)
                resultado["email"] = "enviado"
            except Exception as exc:
                resultado["email"] = "erro"
                logger.exception("Falha ao enviar %s #%s por e-mail para %s: %s", tipo_documento, documento_id, email_destino, exc)

        if whatsapp_destino:
            try:
                sender_setting = getattr(settings, "VISTOGEST_WHATSAPP_DOCUMENT_SENDER", "")
                if not sender_setting:
                    resultado["whatsapp"] = "não configurado"
                    logger.warning(
                        "WhatsApp pedido para %s #%s, mas VISTOGEST_WHATSAPP_DOCUMENT_SENDER não está configurado.",
                        tipo_documento, documento_id,
                    )
                else:
                    sender = import_string(sender_setting) if isinstance(sender_setting, str) else sender_setting
                    sender(
                        telefone=whatsapp_destino,
                        documento=documento,
                        tipo_documento=tipo_documento,
                        nome_ficheiro=filename,
                        ficheiro_pdf=pdf_bytes,
                    )
                    resultado["whatsapp"] = "enviado"
            except Exception as exc:
                resultado["whatsapp"] = "erro"
                logger.exception("Falha ao enviar %s #%s por WhatsApp para %s: %s", tipo_documento, documento_id, whatsapp_destino, exc)

        return resultado


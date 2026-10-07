# apps/fiscal/views_integracoes.py
"""
Webhooks e integrações externas do módulo fiscal.

Segurança:
  - Webhooks externos (AGT, Banco Central) usam HMAC-SHA256 para verificar
    a autenticidade da origem. A chave partilhada é GATEWAY_WEBHOOK_SECRET.
  - Endpoints de integração interna requerem login (@login_required).
  - Endpoints de debug só funcionam com DEBUG=True.
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.fiscal.models import TaxaIVAAGT
from apps.fornecedores.models import Fornecedor

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS DE SEGURANÇA PARA WEBHOOKS
# ──────────────────────────────────────────────────────────────────────────────

def _verificar_hmac_webhook(request, header_assinatura: str = 'X-Webhook-Signature') -> bool:
    """
    Verifica a assinatura HMAC-SHA256 de um webhook.

    O remetente deve incluir no cabeçalho `X-Webhook-Signature` o valor:
        sha256=<hex_digest>
    onde o digest é HMAC-SHA256 do corpo da mensagem com GATEWAY_WEBHOOK_SECRET.

    Retorna True se válido, False se inválido ou se o segredo não estiver configurado.
    """
    secret = getattr(settings, 'GATEWAY_WEBHOOK_SECRET', None)
    if not secret:
        # Segredo não configurado — rejeitar em produção, aceitar em DEBUG
        if settings.DEBUG:
            logger.warning("GATEWAY_WEBHOOK_SECRET não configurado — webhook aceite em modo DEBUG.")
            return True
        logger.error("GATEWAY_WEBHOOK_SECRET não configurado — webhook rejeitado em produção.")
        return False

    assinatura_recebida = request.headers.get(header_assinatura, '')
    if not assinatura_recebida.startswith('sha256='):
        logger.warning("Webhook sem assinatura HMAC no cabeçalho '%s'.", header_assinatura)
        return False

    hash_recebido = assinatura_recebida[7:]  # remover prefixo "sha256="
    hash_esperado = hmac.new(
        secret.encode('utf-8'),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    # Comparação em tempo constante (evita timing attacks)
    return hmac.compare_digest(hash_recebido, hash_esperado)


# ──────────────────────────────────────────────────────────────────────────────
# WEBHOOKS — Notificações externas
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def webhook_agt_notification(request):
    """
    Recebe notificações da AGT (validação de facturas, estado de submissões, etc.).
    Protegido por verificação HMAC-SHA256.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Método não permitido.")

    if not _verificar_hmac_webhook(request, 'X-AGT-Signature'):
        logger.warning(
            "Webhook AGT rejeitado — assinatura inválida | IP: %s",
            request.META.get('REMOTE_ADDR', '?'),
        )
        return HttpResponse("Assinatura inválida.", status=401)

    try:
        data     = json.loads(request.body.decode('utf-8'))
        nif      = data.get('nif', '')
        status   = data.get('status', '')
        mensagem = data.get('mensagem', '')

        logger.info("[AGT Webhook] NIF=%s STATUS=%s MSG=%s", nif, status, mensagem)

        # TODO: actualizar DocumentoFiscal com o estado recebido da AGT
        # DocumentoFiscal.objects.filter(nif_contribuinte=nif).update(status_validacao=status)

        return JsonResponse({"success": True, "message": "Notificação AGT processada."})

    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Webhook AGT: payload inválido — %s", exc)
        return JsonResponse({"success": False, "error": "Payload inválido."}, status=400)
    except Exception as exc:
        logger.exception("Erro ao processar webhook AGT.")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
def webhook_banco_central(request):
    """
    Webhook do Banco Central para eventos financeiros (câmbio, taxas, etc.).
    Protegido por verificação HMAC-SHA256.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Método não permitido.")

    if not _verificar_hmac_webhook(request, 'X-BancoCentral-Signature'):
        logger.warning(
            "Webhook BancoCentral rejeitado — assinatura inválida | IP: %s",
            request.META.get('REMOTE_ADDR', '?'),
        )
        return HttpResponse("Assinatura inválida.", status=401)

    try:
        data        = json.loads(request.body.decode('utf-8'))
        evento      = data.get('evento', '')
        valor       = data.get('valor', '')
        data_evento = data.get('data', str(timezone.now()))

        logger.info("[BancoCentral Webhook] Evento=%s Valor=%s Data=%s", evento, valor, data_evento)

        # TODO: persistir em LogFinanceiro ou BancoCentralEvento

        return JsonResponse({"success": True, "message": "Webhook Banco Central recebido."})

    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Webhook BancoCentral: payload inválido — %s", exc)
        return JsonResponse({"success": False, "error": "Payload inválido."}, status=400)
    except Exception as exc:
        logger.exception("Erro ao processar webhook Banco Central.")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRAÇÕES INTERNAS — Requerem autenticação
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def integracao_agt_validar(request):
    """
    Endpoint interno para validação de documentos fiscais via API AGT.
    Requer utilizador autenticado.
    """
    try:
        data             = json.loads(request.body.decode('utf-8'))
        numero_documento = data.get('numero_documento', '')
        nif_cliente      = data.get('nif_cliente', '')

        if not numero_documento or not nif_cliente:
            return JsonResponse({"success": False, "error": "numero_documento e nif_cliente são obrigatórios."}, status=400)

        logger.info("Validando fatura AGT: Nº %s | NIF %s | User: %s",
                    numero_documento, nif_cliente, request.user.username)

        # TODO: integrar com a API real da AGT quando disponível
        return JsonResponse({
            "numero_documento": numero_documento,
            "nif_cliente":      nif_cliente,
            "status":           "válido",
            "mensagem":         "Documento validado com sucesso pela AGT (simulação).",
        })

    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"success": False, "error": "Payload inválido."}, status=400)
    except Exception as exc:
        logger.exception("Erro na integração AGT validar.")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_POST
def integracao_saft_submit(request):
    """
    Endpoint interno para submissão de ficheiro SAF-T.
    Requer utilizador autenticado.
    """
    try:
        ficheiro = request.FILES.get('ficheiro')
        if not ficheiro:
            return JsonResponse({"success": False, "error": "Ficheiro SAF-T não enviado."}, status=400)

        # Validar extensão
        if not ficheiro.name.lower().endswith('.xml'):
            return JsonResponse({"success": False, "error": "Apenas ficheiros .xml são aceites."}, status=400)

        # Limitar tamanho: 50 MB
        MAX_SIZE = 50 * 1024 * 1024
        if ficheiro.size > MAX_SIZE:
            return JsonResponse({"success": False, "error": "Ficheiro demasiado grande (máx. 50 MB)."}, status=400)

        logger.info("Submissão SAF-T: %s (%d bytes) por %s",
                    ficheiro.name, ficheiro.size, request.user.username)

        # TODO: enviar para a AGT ou guardar localmente com validação XSD

        return JsonResponse({
            "ficheiro": ficheiro.name,
            "status":   "submetido",
            "mensagem": "Ficheiro SAF-T recebido e processado (simulação).",
        })

    except Exception as exc:
        logger.exception("Erro ao submeter ficheiro SAF-T.")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


# ──────────────────────────────────────────────────────────────────────────────
# DEBUG — Gerar dados de teste (apenas com DEBUG=True)
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
@transaction.atomic
def debug_gerar_dados_teste(request):
    """
    Gera dados de teste para desenvolvimento.
    Bloqueado automaticamente em produção (DEBUG=False).
    """
    if not settings.DEBUG:
        return JsonResponse({"success": False, "message": "Não disponível em produção."}, status=403)

    try:
        for i in range(3):
            Fornecedor.objects.get_or_create(
                nome=f"Fornecedor Teste {i + 1}",
                defaults={'nif': f"50000000{i + 1}"},
            )

        for perc in [7, 14, 23]:
            TaxaIVAAGT.objects.get_or_create(
                tax_percentage=Decimal(str(perc)),
                defaults={
                    'nome':      f'IVA {perc}% (teste)',
                    'descricao': f'Taxa de IVA de {perc}% para testes',
                    'ativa':     True,
                },
            )

        return JsonResponse({"success": True, "message": "Dados de teste criados."})

    except Exception as exc:
        logger.exception("Erro ao gerar dados de teste.")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

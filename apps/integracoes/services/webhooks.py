# apps/integracoes/services/webhooks.py
import json
import logging

from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from ..models import ConfiguracaoIntegracao, WebhookIntegracao
from .crypto import ChaveNaoConfigurada
from .providers import ProviderBase, obter_provider

logger = logging.getLogger('integracoes')
MAX_BYTES = 1_000_000
HEADERS_EXCLUIDOS = {'cookie', 'authorization', 'proxy-authorization'}


def receber(request, token):
    config = (ConfiguracaoIntegracao.objects.select_related('tipo_integracao')
              .filter(webhook_token=token, ativa=True, tipo_integracao__suporta_webhook=True).first())
    if config is None:
        return HttpResponse(status=404)
    try:
        provider = obter_provider(config) or ProviderBase(config)
    except ChaveNaoConfigurada:
        logger.error("Webhook recebido mas ENCRYPTION_KEY indisponível.")
        return HttpResponse(status=503)

    if request.method == 'GET':
        return provider.responder_verificacao(request) or HttpResponse(status=405)
    if len(request.body) > MAX_BYTES:
        return HttpResponse(status=413)
    if not provider.verificar_webhook(request):
        logger.warning("Webhook %s rejeitado: assinatura inválida (IP %s)", config, request.META.get('REMOTE_ADDR'))
        return HttpResponse('Assinatura inválida.', status=401)

    if request.content_type == 'application/x-www-form-urlencoded':
        payload = request.POST.dict()
    else:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except ValueError:
            return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    ident = provider.extrair_identificador(request, payload)
    if ident and WebhookIntegracao.objects.filter(configuracao=config, identificador_externo=ident).exists():
        return JsonResponse({'ok': True, 'duplicado': True})
    try:
        wh = WebhookIntegracao.objects.create(
            configuracao=config, evento=provider.extrair_evento(payload), identificador_externo=ident,
            ip_origem=request.META.get('REMOTE_ADDR'),
            headers={k: v for k, v in request.headers.items() if k.lower() not in HEADERS_EXCLUIDOS},
            payload=request.body.decode('utf-8', 'replace'),
            assinatura=(request.headers.get('X-Webhook-Signature') or request.headers.get('X-Hub-Signature-256', ''))[:255])
    except IntegrityError:
        return JsonResponse({'ok': True, 'duplicado': True})
    processar(wh, provider)
    return JsonResponse({'ok': True})


def processar(wh, provider=None):
    """Executa o processamento (síncrono). Se tiverem Celery, chamem isto numa task."""
    wh.tentativas_processamento += 1
    try:
        provider = provider or obter_provider(wh.configuracao) or ProviderBase(wh.configuracao)
        provider.processar_webhook(wh)
    except Exception as exc:
        logger.exception("Falha a processar webhook %s", wh.pk)
        wh.processado, wh.erro_processamento = False, str(exc)[:1000]
    else:
        wh.processado, wh.erro_processamento, wh.processado_em = True, '', timezone.now()
    wh.save()

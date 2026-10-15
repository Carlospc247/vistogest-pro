# apps/integracoes/services/api.py
from ..models import ConfiguracaoIntegracao
from .cliente import ErroIntegracao
from .crypto import ChaveNaoConfigurada
from .providers import REGISTRO, obter_provider


def enviar_mensagem(destino, texto, *, canal=None, assunto=''):
    """Envia por uma integração de mensagens activa (WhatsApp/SMS/e-mail).
    `canal` = código do tipo ('whatsapp_cloud', 'twilio', 'sendgrid'); None = a 1.ª activa.
    Devolve (ok: bool, mensagem: str). Nunca levanta excepção."""
    codigos = [c for c, cls in REGISTRO.items() if cls.suporta_mensagens]
    qs = ConfiguracaoIntegracao.objects.select_related('tipo_integracao').filter(
        ativa=True, tipo_integracao__ativo=True,
        tipo_integracao__codigo__in=[canal] if canal else codigos).order_by('tipo_integracao__ordem')
    config = qs.first()
    if not config:
        return False, 'Nenhuma integração de mensagens activa.'
    try:
        return obter_provider(config).enviar_mensagem(destino, texto, assunto)
    except (ErroIntegracao, ChaveNaoConfigurada, KeyError) as exc:
        return False, str(exc)


def emitir_evento(evento, dados):
    """Envia um evento para o webhook de saída activo (se existir). Devolve True/False."""
    config = (ConfiguracaoIntegracao.objects.select_related('tipo_integracao')
              .filter(ativa=True, tipo_integracao__codigo='webhook_saida').first())
    if not config:
        return False
    try:
        return obter_provider(config).emitir(evento, dados)[0]
    except (ErroIntegracao, ChaveNaoConfigurada, KeyError):
        return False

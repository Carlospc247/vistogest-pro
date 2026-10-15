# apps/integracoes/views.py
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, FormView, ListView, TemplateView

from .forms import ConfiguracaoForm, EnvioTesteForm
from .models import ConfiguracaoIntegracao, LogIntegracao, TipoIntegracao, WebhookIntegracao
from .services import webhooks as svc_webhooks
from .services.catalogo import garantir_catalogo
from .services.cliente import ErroIntegracao
from .services.crypto import ChaveNaoConfigurada
from .services.providers import REGISTRO, obter_provider


class IntegracoesMixin(LoginRequiredMixin):
    """Exige login e a permissão 'acessar_configuracoes' do cargo."""
    acao_requerida = 'acessar_configuracoes'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        func = getattr(request.user, 'funcionario', None)
        if not (func and func.pode_realizar_acao(self.acao_requerida)):
            messages.error(request, 'O seu cargo não permite gerir integrações.')
            return redirect('core_tenants:dashboard')
        return super().dispatch(request, *args, **kwargs)


def _json_bonito(texto):
    try:
        return json.dumps(json.loads(texto), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return texto


# ── Painel e guia ────────────────────────────────────────────────────────────
class DashboardView(IntegracoesMixin, TemplateView):
    template_name = 'integracoes/dashboard.html'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        garantir_catalogo()
        hoje = timezone.localdate()
        configs = {c.tipo_integracao_id: c for c in ConfiguracaoIntegracao.objects.select_related('tipo_integracao')}
        ctx.update(
            chave_ok=bool(getattr(settings, 'ENCRYPTION_KEY', None)),
            itens=[{'tipo': t, 'config': configs.get(t.pk)} for t in TipoIntegracao.objects.filter(ativo=True)],
            total_ativas=sum(1 for c in configs.values() if c.status == 'ativa'),
            total_erro=sum(1 for c in configs.values() if c.status == 'erro'),
            pedidos_hoje=sum(c.requests_utilizadas_hoje for c in configs.values() if c.data_contagem == hoje),
            webhooks_pendentes=WebhookIntegracao.objects.filter(processado=False).count(),
            logs_recentes=LogIntegracao.objects.select_related('configuracao__tipo_integracao')[:8],
        )
        return ctx


class GuiaView(IntegracoesMixin, TemplateView):
    template_name = 'integracoes/guia.html'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        garantir_catalogo()
        ctx['tipos'] = TipoIntegracao.objects.filter(ativo=True)
        ctx['exemplo_url'] = self.request.build_absolute_uri('/integracoes/webhook/SEU_TOKEN/')
        return ctx


# ── Configuração ─────────────────────────────────────────────────────────────
class ConfigurarView(IntegracoesMixin, FormView):
    template_name = 'integracoes/configurar.html'
    form_class = ConfiguracaoForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.tipo = get_object_or_404(TipoIntegracao, codigo=kwargs['codigo'], ativo=True)
        self.config = ConfiguracaoIntegracao.objects.filter(tipo_integracao=self.tipo).first()

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw.update(tipo=self.tipo, config=self.config)
        return kw

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(tipo=self.tipo, config=self.config)
        return ctx

    def form_valid(self, form):
        try:
            self.config = form.salvar(self.request.user)
        except ChaveNaoConfigurada as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, 'Configuração guardada. Teste a ligação antes de activar.')
        return redirect('integracoes:detalhe', pk=self.config.pk)


class DetalheView(IntegracoesMixin, DetailView):
    model = ConfiguracaoIntegracao
    template_name = 'integracoes/detalhe.html'
    context_object_name = 'config'

    def get_queryset(self):
        return super().get_queryset().select_related('tipo_integracao')

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        c = self.object
        try:
            ctx['credenciais'] = c.credenciais_mascaradas()
        except ChaveNaoConfigurada as exc:
            ctx['credenciais'], ctx['erro_chave'] = [], str(exc)
        cls = REGISTRO.get(c.tipo_integracao.codigo)
        hoje = timezone.localdate()
        uso = c.requests_utilizadas_hoje if c.data_contagem == hoje else 0
        ctx.update(
            uso_hoje=uso, uso_pct=min(100, int(uso * 100 / c.limite_requests_dia)) if c.limite_requests_dia else 0,
            suporta_mensagens=bool(cls and cls.suporta_mensagens), form_teste=EnvioTesteForm(),
            webhook_url=self.request.build_absolute_uri(
                __import__('django.urls', fromlist=['reverse']).reverse('integracoes:webhook_receber', args=[c.webhook_token])),
            segredo_novo=self.request.session.pop('integracoes_segredo_novo', {}).get(str(c.pk)),
            logs=c.logs.all()[:8], webhooks=c.webhooks.all()[:5])
        return ctx


class _AcaoBase(IntegracoesMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        self.config = get_object_or_404(ConfiguracaoIntegracao.objects.select_related('tipo_integracao'), pk=pk)
        return self.executar(request) or redirect('integracoes:detalhe', pk=self.config.pk)


class AtivarView(_AcaoBase):
    def executar(self, request):
        if not self.config.configurada:
            messages.error(request, 'Complete as credenciais obrigatórias antes de activar.')
        else:
            self.config.ativa = True
            self.config.save(update_fields=['ativa'])
            if self.config.ultimo_teste_ok is None:
                messages.warning(request, 'Integração activada sem teste de ligação. Recomenda-se testar.')
            else:
                messages.success(request, 'Integração activada.')


class DesativarView(_AcaoBase):
    def executar(self, request):
        self.config.ativa = False
        self.config.save(update_fields=['ativa'])
        messages.info(request, 'Integração desactivada.')


class TestarView(_AcaoBase):
    def executar(self, request):
        try:
            provider = obter_provider(self.config)
            if provider is None:
                messages.error(request, 'Esta integração não tem conector de teste.')
                return
            ok, msg = provider.testar_conexao()
        except ErroIntegracao as exc:
            ok, msg = False, str(exc)
        except ChaveNaoConfigurada as exc:
            ok, msg = False, str(exc)
        except KeyError as exc:
            ok, msg = False, f'Credencial em falta: {exc}'
        self.config.ultimo_teste_em, self.config.ultimo_teste_ok = timezone.now(), ok
        if ok:
            self.config.erro_ultima_sincronizacao = ''
        self.config.save(update_fields=['ultimo_teste_em', 'ultimo_teste_ok', 'erro_ultima_sincronizacao'])
        (messages.success if ok else messages.error)(request, f'Teste de ligação: {msg}')


class EnviarTesteView(_AcaoBase):
    def executar(self, request):
        form = EnvioTesteForm(request.POST)
        cls = REGISTRO.get(self.config.tipo_integracao.codigo)
        if not (cls and cls.suporta_mensagens):
            messages.error(request, 'Esta integração não envia mensagens.')
        elif not form.is_valid():
            messages.error(request, 'Preencha o destino e o texto.')
        else:
            d = form.cleaned_data
            try:
                ok, msg = obter_provider(self.config).enviar_mensagem(d['destino'], d['texto'], d['assunto'])
            except (ErroIntegracao, ChaveNaoConfigurada, KeyError) as exc:
                ok, msg = False, str(exc)
            (messages.success if ok else messages.error)(request, msg)


class RegenerarSegredoView(_AcaoBase):
    def executar(self, request):
        novo = self.config.regenerar_webhook_segredo()
        self.config.save(update_fields=['webhook_segredo_cifrado'])
        request.session['integracoes_segredo_novo'] = {str(self.config.pk): novo}
        messages.warning(request, 'Novo segredo gerado. Copie-o agora: não voltará a ser mostrado.')


class LimparCredenciaisView(_AcaoBase):
    def executar(self, request):
        c = self.config
        c.credenciais_criptografadas, c.ativa = '', False
        c.ultimo_teste_ok = c.ultimo_teste_em = None
        c.save(update_fields=['credenciais_criptografadas', 'ativa', 'ultimo_teste_ok', 'ultimo_teste_em'])
        messages.info(request, 'Credenciais removidas e integração desactivada.')


class RemoverView(_AcaoBase):
    def executar(self, request):
        self.config.delete()
        messages.success(request, 'Configuração removida (logs e webhooks incluídos).')
        return redirect('integracoes:dashboard')


# ── Logs e webhooks ──────────────────────────────────────────────────────────
class LogListView(IntegracoesMixin, ListView):
    model = LogIntegracao
    template_name = 'integracoes/log_list.html'
    context_object_name = 'logs'
    paginate_by = 40

    def get_queryset(self):
        qs = super().get_queryset().select_related('configuracao__tipo_integracao')
        g = self.request.GET
        if g.get('config', '').isdigit():
            qs = qs.filter(configuracao_id=g['config'])
        if g.get('status') in dict(LogIntegracao.STATUS_CHOICES):
            qs = qs.filter(status=g['status'])
        if g.get('direcao') in dict(LogIntegracao.DIRECAO_CHOICES):
            qs = qs.filter(direcao=g['direcao'])
        if g.get('q'):
            qs = qs.filter(Q(url__icontains=g['q']) | Q(response_data__icontains=g['q']))
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(configs=ConfiguracaoIntegracao.objects.select_related('tipo_integracao'),
                   status_choices=LogIntegracao.STATUS_CHOICES, direcao_choices=LogIntegracao.DIRECAO_CHOICES)
        return ctx


class LogDetailView(IntegracoesMixin, DetailView):
    model = LogIntegracao
    template_name = 'integracoes/log_detail.html'
    context_object_name = 'log'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(headers_json=json.dumps(self.object.headers, indent=2, ensure_ascii=False),
                   payload_fmt=_json_bonito(self.object.payload), resposta_fmt=_json_bonito(self.object.response_data))
        return ctx


class WebhookListView(IntegracoesMixin, ListView):
    model = WebhookIntegracao
    template_name = 'integracoes/webhook_list.html'
    context_object_name = 'webhooks'
    paginate_by = 40

    def get_queryset(self):
        qs = super().get_queryset().select_related('configuracao__tipo_integracao')
        g = self.request.GET
        if g.get('config', '').isdigit():
            qs = qs.filter(configuracao_id=g['config'])
        if g.get('estado') == 'pendentes':
            qs = qs.filter(processado=False)
        elif g.get('estado') == 'processados':
            qs = qs.filter(processado=True)
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['configs'] = ConfiguracaoIntegracao.objects.select_related('tipo_integracao')
        return ctx


class WebhookDetailView(IntegracoesMixin, DetailView):
    model = WebhookIntegracao
    template_name = 'integracoes/webhook_detail.html'
    context_object_name = 'webhook'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['payload_fmt'] = _json_bonito(self.object.payload)
        ctx['headers_json'] = json.dumps(self.object.headers, indent=2, ensure_ascii=False)
        return ctx


class ReprocessarWebhookView(IntegracoesMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        wh = get_object_or_404(WebhookIntegracao.objects.select_related('configuracao__tipo_integracao'), pk=pk)
        svc_webhooks.processar(wh)
        (messages.success if wh.processado else messages.error)(
            request, 'Webhook processado.' if wh.processado else f'Falhou: {wh.erro_processamento}')
        return redirect('integracoes:webhook_detalhe', pk=pk)


# ── Receptor público (sem login, sem CSRF — protegido por token + assinatura) ─
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def webhook_receber(request, token):
    return svc_webhooks.receber(request, token)

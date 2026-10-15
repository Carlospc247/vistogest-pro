# apps/funcionarios/views_recibo.py
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.fiscal.services.pdf_agt_service import PDFReciboVencimentoService

from . import motor_salarial as motor
from .forms_recibo import (
    AjusteForm, AtribuicaoForm, ConfiguracaoReciboForm, ConfirmacaoForm, DadosSalariaisForm, EscalaFormSet,
    LancamentoForm, MotivoForm, PagamentoForm, ParametroFiscalForm, ProcessamentoForm, RubricaForm, TabelaIRTForm,
)
from .models import Funcionario
from .models_recibo import (
    AuditoriaSalarial, ConfiguracaoRecibo, DadosSalariaisFuncionario, ParametroFiscal, ProcessamentoSalarial,
    ReciboVencimento, Rubrica, RubricaFuncionario, TabelaIRT,
)


# ── permissões (reutilizam as flags já existentes no Cargo) ──────────────────
def funcionario_de(user):
    for attr in ('funcionario', 'funcionario_relacionado'):
        try:
            f = getattr(user, attr, None)
        except ObjectDoesNotExist:
            f = None
        if f:
            return f
    return None


def pode(user, acao):
    f = funcionario_de(user)
    return bool(f and f.pode_realizar_acao(acao))


class AcoesMixin(LoginRequiredMixin):
    acoes = ('acessar_rh',)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not all(pode(request.user, a) for a in self.acoes):
            messages.error(request, "O seu cargo não permite aceder a esta área.")
            return redirect('core_tenants:dashboard')
        return super().dispatch(request, *args, **kwargs)


class ProcessarMixin(AcoesMixin):
    acoes = ('acessar_rh', 'pagar_salario')


class ConfigurarMixin(AcoesMixin):
    acoes = ('acessar_rh', 'acessar_financeiro')


class EstornarMixin(AcoesMixin):
    acoes = ('acessar_rh', 'estornar_pagamento')


def _ser(d):
    return json.loads(json.dumps(d, default=str)) if d is not None else None


class AuditaMixin:
    """Regista quem alterou o quê (antes/depois) em configurações salariais."""
    def form_valid(self, form):
        existente = getattr(self, 'object', None)
        antes = _ser(form.initial) if existente is not None and existente.pk else None
        resp = super().form_valid(form)
        AuditoriaSalarial.registar(self.request.user, 'ALTERADO' if antes is not None else 'CRIADO', self.object,
                                   antes=antes, depois=_ser(form.cleaned_data), ip=self.request.META.get('REMOTE_ADDR'))
        return resp


def _logo_url():
    foto = getattr(connection.tenant, 'foto', None)
    try:
        return foto.url if foto else ''
    except Exception:
        return ''


def _partes(r):
    linhas = list(r.linhas.all())
    return {'linhas_remun': [l for l in linhas if l.tipo == 'REMUNERACAO'],
            'linhas_desc': [l for l in linhas if l.tipo == 'DESCONTO'],
            'linhas_enc': [l for l in linhas if l.tipo == 'ENCARGO']}


def _acessivel(user, r):
    if pode(user, 'acessar_rh'):
        return True
    f = funcionario_de(user)
    return bool(f and r.funcionario_id == f.pk and r.estado in ('EMITIDO', 'PAGO'))


def _iban_completo(user, r):
    f = funcionario_de(user)
    return pode(user, 'pagar_salario') or bool(f and f.pk == r.funcionario_id)


# ══════════════════════════════════════════════════════════════════════════════
# RECIBOS
# ══════════════════════════════════════════════════════════════════════════════
class ReciboListView(AcoesMixin, ListView):
    model = ReciboVencimento
    template_name = 'recibos/recibo_list.html'
    context_object_name = 'recibos'
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('processamento')
        g = self.request.GET
        if g.get('q'):
            qs = qs.filter(Q(func_nome__icontains=g['q']) | Q(numero__icontains=g['q']) | Q(func_matricula__icontains=g['q']))
        if g.get('mes', '').isdigit():
            qs = qs.filter(mes=g['mes'])
        if g.get('ano', '').isdigit():
            qs = qs.filter(ano=g['ano'])
        if g.get('estado') in dict(ReciboVencimento.ESTADOS):
            qs = qs.filter(estado=g['estado'])
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(estados=ReciboVencimento.ESTADOS, hoje=timezone.localdate(),
                   funcionarios_ativos=Funcionario.objects.filter(ativo=True).order_by('nome_completo'))
        return ctx


class MeusRecibosView(LoginRequiredMixin, ListView):
    template_name = 'recibos/recibo_list.html'
    context_object_name = 'recibos'
    paginate_by = 24

    def get_queryset(self):
        f = funcionario_de(self.request.user)
        qs = ReciboVencimento.objects.filter(estado__in=('EMITIDO', 'PAGO'))
        return qs.filter(funcionario=f) if f else qs.none()

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['somente_proprios'] = True
        return ctx


class ReciboDetailView(LoginRequiredMixin, DetailView):
    model = ReciboVencimento
    template_name = 'recibos/recibo_detail.html'
    context_object_name = 'r'

    def get_object(self, queryset=None):
        r = super().get_object(queryset)
        if not _acessivel(self.request.user, r):
            raise PermissionDenied
        return r

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        r, u = self.object, self.request.user
        proc = pode(u, 'acessar_rh') and pode(u, 'pagar_salario')
        ctx.update(_partes(r))
        ctx.update(
            logo_url=_logo_url(), pode_processar=proc, pode_estornar=pode(u, 'acessar_rh') and pode(u, 'estornar_pagamento'),
            iban_txt=r.func_iban if _iban_completo(u, r) else r.func_iban_mascarado,
            form_lancamento=LancamentoForm(), form_pagamento=PagamentoForm(), form_ajuste=AjusteForm(),
            lancamentos=[(Rubrica.objects.filter(codigo=c).first(), v) for c, v in (r.lancamentos or {}).items()],
            auditoria=AuditoriaSalarial.objects.filter(modelo='ReciboVencimento', objeto_id=str(r.pk))[:10])
        return ctx


class ReciboImprimirView(LoginRequiredMixin, DetailView):
    model = ReciboVencimento
    template_name = 'recibos/recibo_imprimir.html'
    context_object_name = 'r'

    def get_object(self, queryset=None):
        r = super().get_object(queryset)
        if not _acessivel(self.request.user, r):
            raise PermissionDenied
        AuditoriaSalarial.registar(self.request.user, 'RECIBO_IMPRESSO', r, ip=self.request.META.get('REMOTE_ADDR'))
        return r

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        r = self.object
        ctx.update(_partes(r))
        ctx.update(logo_url=_logo_url(), iban_txt=r.func_iban if _iban_completo(self.request.user, r) else r.func_iban_mascarado)
        return ctx


class ReciboPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        r = get_object_or_404(ReciboVencimento, pk=pk)
        if not _acessivel(request.user, r):
            raise PermissionDenied
        cfg = ConfiguracaoRecibo.get_solo()
        completo = _iban_completo(request.user, r) and (cfg.mostrar_iban_completo or funcionario_de(request.user).pk == r.funcionario_id
                                                         if funcionario_de(request.user) else False)
        buf = PDFReciboVencimentoService(r, mostrar_iban_completo=bool(completo), configuracao=cfg).gerar()
        AuditoriaSalarial.registar(request.user, 'RECIBO_PDF', r, ip=request.META.get('REMOTE_ADDR'))
        resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
        disp = 'attachment' if request.GET.get('download') else 'inline'
        resp['Content-Disposition'] = f'{disp}; filename="{r.numero.replace(" ", "_").replace("/", "-")}.pdf"'
        return resp


class ReciboPreviaView(AcoesMixin, TemplateView):
    """Pré-visualização do processamento (nada é gravado)."""
    template_name = 'recibos/previa.html'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        g = self.request.GET
        try:
            func = Funcionario.objects.select_related('cargo', 'departamento').get(pk=int(g.get('funcionario')))
            mes, ano = int(g.get('mes')), int(g.get('ano'))
            if not (1 <= mes <= 12):
                raise ValueError
        except (TypeError, ValueError, Funcionario.DoesNotExist):
            ctx['erro_parametros'] = "Escolha o funcionário, o mês e o ano."
            return ctx
        recibo, res = motor.pre_visualizar(func, mes, ano)
        ctx.update(r=recibo, res=res, previa=True, logo_url=_logo_url(), iban_txt=recibo.func_iban_mascarado,
                   linhas_remun=[l for l in res.linhas if l.tipo == 'REMUNERACAO'],
                   linhas_desc=[l for l in res.linhas if l.tipo == 'DESCONTO'],
                   linhas_enc=[l for l in res.linhas if l.tipo == 'ENCARGO'])
        return ctx


class _ReciboAcao(View):
    http_method_names = ['post']

    def post(self, request, pk):
        self.recibo = get_object_or_404(ReciboVencimento.objects.select_related('processamento', 'funcionario'), pk=pk)
        destino = None
        try:
            destino = self.executar(request)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        return destino or redirect('funcionarios:recibo_detalhe', pk=pk)


class ReciboRecalcularView(ProcessarMixin, _ReciboAcao):
    def executar(self, request):
        if not self.recibo.editavel:
            raise ValidationError("Recibo já emitido: use a retificação.")
        r = motor.recalcular_recibo(self.recibo, request.user)
        (messages.warning if r.erros else messages.success)(request, "Recibo recalculado." if not r.erros else "Recalculado com erros: " + "; ".join(r.erros))


class ReciboLancamentoView(ProcessarMixin, _ReciboAcao):
    """Define (ou remove) a quantidade/valor mensal de uma rubrica variável e recalcula."""
    def executar(self, request):
        if not self.recibo.editavel:
            raise ValidationError("Recibo já emitido: use a retificação.")
        lanc = dict(self.recibo.lancamentos or {})
        if request.POST.get('remover'):
            lanc.pop(request.POST['remover'], None)
        else:
            form = LancamentoForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Lançamento inválido.")
            d = form.cleaned_data
            lanc[d['rubrica'].codigo] = {'quantidade': str(d['quantidade']) if d['quantidade'] is not None else None,
                                         'valor': str(d['valor']) if d['valor'] is not None else None}
        motor.processar_recibo(self.recibo.processamento, self.recibo.funcionario, request.user, lancamentos=lanc)
        messages.success(request, "Lançamentos actualizados e recibo recalculado.")


class ReciboAjusteView(ProcessarMixin, _ReciboAcao):
    def executar(self, request):
        if not self.recibo.editavel:
            raise ValidationError("Recibo já emitido: use a retificação.")
        form = AjusteForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Valor inválido.")
        novo = form.cleaned_data['ajuste_salario_base']
        AuditoriaSalarial.registar(request.user, 'SALARIO_BASE_AJUSTADO', self.recibo,
                                   antes={'ajuste': str(self.recibo.ajuste_salario_base)}, depois={'ajuste': str(novo)})
        motor.processar_recibo(self.recibo.processamento, self.recibo.funcionario, request.user, ajuste=novo)
        messages.success(request, "Salário-base ajustado só neste recibo; o cadastro do funcionário não foi alterado.")


class ReciboEmitirView(ProcessarMixin, _ReciboAcao):
    def executar(self, request):
        self.recibo.emitir(request.user)
        messages.success(request, f"Recibo {self.recibo.numero} emitido.")


class ReciboPagarView(ProcessarMixin, _ReciboAcao):
    def executar(self, request):
        form = PagamentoForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Indique a data de pagamento.")
        self.recibo.marcar_pago(request.user, form.cleaned_data['data_pagamento'], form.cleaned_data['referencia_pagamento'])
        messages.success(request, "Pagamento registado.")


class ReciboAnularView(EstornarMixin, _ReciboAcao):
    def executar(self, request):
        form = MotivoForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Indique o motivo (mín. 5 caracteres).")
        self.recibo.anular(request.user, form.cleaned_data['motivo'])
        messages.warning(request, "Recibo anulado.")


class ReciboRetificarView(EstornarMixin, _ReciboAcao):
    def executar(self, request):
        form = MotivoForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Indique o motivo (mín. 5 caracteres).")
        novo = self.recibo.retificar(request.user, form.cleaned_data['motivo'])
        novo = motor.recalcular_recibo(novo, request.user)
        messages.success(request, f"Criado o recibo retificativo {novo.numero} (em rascunho/calculado).")
        return redirect('funcionarios:recibo_detalhe', pk=novo.pk)


class ReciboConfirmacaoView(ProcessarMixin, UpdateView):
    """Assinaturas, responsável, contabilista e referência de pagamento (campos operacionais)."""
    model = ReciboVencimento
    form_class = ConfirmacaoForm
    template_name = 'recibos/form.html'
    extra_context = {'titulo': 'Assinaturas e confirmação de pagamento'}

    def get_success_url(self):
        return reverse('funcionarios:recibo_detalhe', kwargs={'pk': self.object.pk})


# ══════════════════════════════════════════════════════════════════════════════
# PROCESSAMENTOS
# ══════════════════════════════════════════════════════════════════════════════
class ProcessamentoListView(AcoesMixin, ListView):
    model = ProcessamentoSalarial
    template_name = 'recibos/processamento_list.html'
    context_object_name = 'processamentos'
    paginate_by = 24


class ProcessamentoCreateView(ProcessarMixin, CreateView):
    model = ProcessamentoSalarial
    form_class = ProcessamentoForm
    template_name = 'recibos/form.html'
    extra_context = {'titulo': 'Novo processamento salarial'}

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        if not form.instance.descricao:
            form.instance.descricao = f"Processamento {form.instance.mes:02d}/{form.instance.ano}"
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('funcionarios:processamento_detalhe', kwargs={'pk': self.object.pk})


class ProcessamentoDetailView(AcoesMixin, DetailView):
    model = ProcessamentoSalarial
    template_name = 'recibos/processamento_detail.html'
    context_object_name = 'p'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        p = self.object
        ctx.update(recibos=p.recibos.select_related('funcionario').order_by('func_nome'), totais=p.totais(),
                   pode_processar=pode(self.request.user, 'pagar_salario'), form_pagamento=PagamentoForm(),
                   pendentes=p.recibos.filter(estado__in=('RASCUNHO', 'CALCULADO')).count(),
                   por_emitir=p.recibos.filter(estado='CALCULADO').count(),
                   por_pagar=p.recibos.filter(estado='EMITIDO').count())
        return ctx


class _ProcAcao(ProcessarMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        self.p = get_object_or_404(ProcessamentoSalarial, pk=pk)
        try:
            self.executar(request)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        return redirect('funcionarios:processamento_detalhe', pk=pk)


class ProcessamentoGerarView(_ProcAcao):
    def executar(self, request):
        if not self.p.aberto:
            raise ValidationError("Este processamento já foi fechado.")
        r = motor.processar_todos(self.p, request.user)
        messages.success(request, f"{r['processados']} recibo(s) processado(s); {r['com_erros']} com erros.")
        for f in r['falhas'][:15]:
            messages.warning(request, f)


class ProcessamentoEmitirView(_ProcAcao):
    @transaction.atomic
    def executar(self, request):
        n = 0
        for r in self.p.recibos.filter(estado='CALCULADO'):
            r.emitir(request.user)
            n += 1
        if not self.p.recibos.filter(estado__in=('RASCUNHO', 'CALCULADO')).exists() and self.p.recibos.exists():
            self.p.estado, self.p.fechado_por, self.p.fechado_em = 'FECHADO', request.user, timezone.now()
            self.p.save(update_fields=['estado', 'fechado_por', 'fechado_em', 'updated_at'])
        AuditoriaSalarial.registar(request.user, 'PROCESSAMENTO_EMITIDO', self.p, depois={'recibos': n})
        messages.success(request, f"{n} recibo(s) emitido(s).")


class ProcessamentoPagarView(_ProcAcao):
    @transaction.atomic
    def executar(self, request):
        form = PagamentoForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Indique a data de pagamento.")
        d = form.cleaned_data
        n = 0
        for r in self.p.recibos.filter(estado='EMITIDO'):
            r.marcar_pago(request.user, d['data_pagamento'], d['referencia_pagamento'])
            n += 1
        if not self.p.recibos.filter(estado__in=('RASCUNHO', 'CALCULADO', 'EMITIDO')).exists():
            self.p.estado, self.p.data_pagamento = 'PAGO', d['data_pagamento']
            self.p.save(update_fields=['estado', 'data_pagamento', 'updated_at'])
        messages.success(request, f"{n} recibo(s) marcado(s) como pago(s).")


class ProcessamentoCancelarView(_ProcAcao):
    @transaction.atomic
    def executar(self, request):
        if self.p.recibos.filter(estado__in=('EMITIDO', 'PAGO')).exists():
            raise ValidationError("Há recibos emitidos: anule/retifique-os individualmente.")
        for r in self.p.recibos.all():
            r.estado = 'ANULADO'
            r.save(_transicao=True)
        self.p.estado = 'CANCELADO'
        self.p.save(update_fields=['estado', 'updated_at'])
        AuditoriaSalarial.registar(request.user, 'PROCESSAMENTO_CANCELADO', self.p)
        messages.warning(request, "Processamento cancelado.")


# ══════════════════════════════════════════════════════════════════════════════
# RUBRICAS
# ══════════════════════════════════════════════════════════════════════════════
class RubricaListView(ConfigurarMixin, ListView):
    model = Rubrica
    template_name = 'recibos/rubrica_list.html'
    context_object_name = 'rubricas'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        rs = list(ctx['rubricas'])
        ctx.update(remuneracoes=[r for r in rs if r.tipo == 'REMUNERACAO'], descontos=[r for r in rs if r.tipo == 'DESCONTO'],
                   encargos=[r for r in rs if r.tipo == 'ENCARGO_PATRONAL'])
        return ctx


class RubricaCreateView(ConfigurarMixin, AuditaMixin, CreateView):
    model = Rubrica
    form_class = RubricaForm
    template_name = 'recibos/rubrica_form.html'
    success_url = reverse_lazy('funcionarios:rubrica_lista')
    extra_context = {'titulo': 'Nova rubrica'}


class RubricaUpdateView(ConfigurarMixin, AuditaMixin, UpdateView):
    model = Rubrica
    form_class = RubricaForm
    template_name = 'recibos/rubrica_form.html'
    success_url = reverse_lazy('funcionarios:rubrica_lista')
    extra_context = {'titulo': 'Editar rubrica'}


class RubricaAlternarView(ConfigurarMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        r = get_object_or_404(Rubrica, pk=pk)
        if r.ativa and (r.obrigatoria_por_lei or r.eh_sistema):
            messages.error(request, "Rubricas legalmente obrigatórias ou de sistema não podem ser desactivadas.")
        else:
            r.ativa = not r.ativa
            r.save(update_fields=['ativa', 'updated_at'])
            AuditoriaSalarial.registar(request.user, 'RUBRICA_ATIVADA' if r.ativa else 'RUBRICA_DESATIVADA', r)
            messages.success(request, f"Rubrica {'activada' if r.ativa else 'desactivada'}.")
        return redirect('funcionarios:rubrica_lista')


class RubricaOrdemView(ConfigurarMixin, View):
    http_method_names = ['post']

    def post(self, request):
        try:
            ids = [int(i) for i in json.loads(request.body).get('ids', [])]
        except (ValueError, TypeError):
            return JsonResponse({'ok': False}, status=400)
        with transaction.atomic():
            for pos, pk in enumerate(ids, start=1):
                Rubrica.objects.filter(pk=pk).update(ordem_calculo=pos * 10)
        AuditoriaSalarial.registar(request.user, 'RUBRICAS_REORDENADAS', Rubrica(pk=0), depois={'ids': ids})
        return JsonResponse({'ok': True})


class AtribuicaoListView(ConfigurarMixin, ListView):
    template_name = 'recibos/atribuicao_list.html'
    context_object_name = 'atribuicoes'

    def get_queryset(self):
        self.rubrica = get_object_or_404(Rubrica, pk=self.kwargs['pk'])
        return self.rubrica.atribuicoes.select_related('funcionario')

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['rubrica'] = self.rubrica
        return ctx


class AtribuicaoCreateView(ConfigurarMixin, CreateView):
    model = RubricaFuncionario
    form_class = AtribuicaoForm
    template_name = 'recibos/form.html'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        self.rubrica = get_object_or_404(Rubrica, pk=self.kwargs['pk'])
        kw['rubrica'] = self.rubrica
        return kw

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['titulo'] = f"Atribuição individual — {self.rubrica.nome}"
        return ctx

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        resp = super().form_valid(form)
        AuditoriaSalarial.registar(self.request.user, 'ATRIBUICAO_CRIADA', self.object, depois=_ser(form.cleaned_data))
        return resp

    def get_success_url(self):
        return reverse('funcionarios:atribuicao_lista', kwargs={'pk': self.rubrica.pk})


class AtribuicaoRemoverView(ConfigurarMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        a = get_object_or_404(RubricaFuncionario, pk=pk)
        rubrica_pk = a.rubrica_id
        AuditoriaSalarial.registar(request.user, 'ATRIBUICAO_REMOVIDA', a)
        a.delete()
        messages.info(request, "Atribuição removida.")
        return redirect('funcionarios:atribuicao_lista', pk=rubrica_pk)


# ══════════════════════════════════════════════════════════════════════════════
# PARÂMETROS, TABELAS, CONFIGURAÇÃO, DADOS, AUDITORIA
# ══════════════════════════════════════════════════════════════════════════════
class ParametroListView(ConfigurarMixin, ListView):
    model = ParametroFiscal
    template_name = 'recibos/parametro_list.html'
    context_object_name = 'parametros'


class ParametroCreateView(ConfigurarMixin, AuditaMixin, CreateView):
    model = ParametroFiscal
    form_class = ParametroFiscalForm
    template_name = 'recibos/form.html'
    success_url = reverse_lazy('funcionarios:parametro_lista')
    extra_context = {'titulo': 'Novo parâmetro fiscal (nova vigência)'}


class ParametroUpdateView(ConfigurarMixin, AuditaMixin, UpdateView):
    model = ParametroFiscal
    form_class = ParametroFiscalForm
    template_name = 'recibos/form.html'
    success_url = reverse_lazy('funcionarios:parametro_lista')
    extra_context = {'titulo': 'Editar parâmetro fiscal'}


class TabelaIRTListView(ConfigurarMixin, ListView):
    model = TabelaIRT
    template_name = 'recibos/tabela_irt_list.html'
    context_object_name = 'tabelas'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('escalas')


class TabelaIRTFormView(ConfigurarMixin, View):
    def _contexto(self, form, formset, obj):
        return {'form': form, 'formset': formset, 'obj': obj}

    def get(self, request, pk=None):
        obj = get_object_or_404(TabelaIRT, pk=pk) if pk else None
        form = TabelaIRTForm(instance=obj)
        return render(request, 'recibos/tabela_irt_form.html', self._contexto(form, EscalaFormSet(instance=obj or TabelaIRT()), obj))

    def post(self, request, pk=None):
        obj = get_object_or_404(TabelaIRT, pk=pk) if pk else None
        form = TabelaIRTForm(request.POST, instance=obj)
        formset = EscalaFormSet(request.POST, instance=form.instance)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                tabela = form.save()
                formset.instance = tabela
                formset.save()
                AuditoriaSalarial.registar(request.user, 'TABELA_IRT_ALTERADA' if obj else 'TABELA_IRT_CRIADA', tabela,
                                           depois=tabela.snapshot())
            messages.success(request, "Tabela de IRT guardada. Recibos já emitidos não são afectados.")
            return redirect('funcionarios:tabela_irt_lista')
        return render(request, 'recibos/tabela_irt_form.html', self._contexto(form, formset, obj))


class ConfiguracaoReciboView(ConfigurarMixin, AuditaMixin, UpdateView):
    form_class = ConfiguracaoReciboForm
    template_name = 'recibos/form.html'
    success_url = reverse_lazy('funcionarios:recibo_lista')
    extra_context = {'titulo': 'Configuração do Recibo de Vencimento'}

    def get_object(self, queryset=None):
        return ConfiguracaoRecibo.get_solo()


class DadosSalariaisView(ProcessarMixin, AuditaMixin, UpdateView):
    """NIF, n.º INSS, IBAN e unidade do funcionário (dados sensíveis: exige 'pagar_salario')."""
    form_class = DadosSalariaisForm
    template_name = 'recibos/form.html'

    def get_object(self, queryset=None):
        self.func = get_object_or_404(Funcionario, pk=self.kwargs['funcionario_pk'])
        return DadosSalariaisFuncionario.objects.get_or_create(funcionario=self.func)[0]

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['titulo'] = f"Dados salariais — {self.func.nome_completo}"
        return ctx

    def get_success_url(self):
        return reverse('funcionarios:detail', kwargs={'pk': self.func.pk})


class AuditoriaListView(ConfigurarMixin, ListView):
    model = AuditoriaSalarial
    template_name = 'recibos/auditoria_list.html'
    context_object_name = 'registos'
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related('utilizador')
        g = self.request.GET
        if g.get('modelo'):
            qs = qs.filter(modelo=g['modelo'])
        if g.get('q'):
            qs = qs.filter(Q(acao__icontains=g['q']) | Q(objeto_repr__icontains=g['q']))
        return qs

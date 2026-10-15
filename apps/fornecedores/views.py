# apps/fornecedores/views.py
import csv
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Avg, Count, Q, Sum, ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.produtos.models import Produto
from .forms import (
    AvaliacaoForm, ContatoForm, ContratoForm, CotacaoForm, FornecedorForm, PedidoCompraForm,
)
from .models import (
    AvaliacaoFornecedor, ContatoFornecedor, ContratoFornecedor, CotacaoFornecedor,
    Fornecedor, HistoricoPedido, Pedido,
)

ESTADOS_COMPRA = ['aprovado', 'recebido', 'finalizado']


def kz(valor):
    v = Decimal(valor or 0)
    return f"{v:,.2f} Kz".replace(',', 'X').replace('.', ',').replace('X', '.')


# ==============================================================================
# MIXINS
# ==============================================================================
class PermissaoAcaoMixin(AccessMixin):
    acao_requerida = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        try:
            funcionario = request.user.funcionario
        except Exception:
            messages.error(request, "Acesso negado. O seu utilizador não está ligado a um funcionário.")
            return self.handle_no_permission()
        if self.acao_requerida and not funcionario.pode_realizar_acao(self.acao_requerida):
            messages.error(request, f"O seu cargo não permite a acção '{self.acao_requerida}'.")
            return redirect(reverse_lazy('core_tenants:dashboard'))
        return super().dispatch(request, *args, **kwargs)


class FornecedoresMixin(PermissaoAcaoMixin):
    """Todas as views do módulo exigem login + permissão do cargo."""
    acao_requerida = 'acessar_fornecedores'


FORM_TPL = 'fornecedores/form_generico.html'
DEL_TPL = 'fornecedores/confirmar_exclusao.html'


# ==============================================================================
# FORNECEDORES
# ==============================================================================
class FornecedorListView(FornecedoresMixin, ListView):
    model = Fornecedor
    paginate_by = 24
    template_name = 'fornecedores/fornecedor_list.html'
    context_object_name = 'fornecedores'

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        estado = self.request.GET.get('estado', '')
        if q:
            qs = qs.filter(
                Q(razao_social__icontains=q) | Q(nome_fantasia__icontains=q)
                | Q(nif_bi__icontains=q) | Q(codigo_fornecedor__icontains=q)
            )
        if estado == 'ativos':
            qs = qs.filter(ativo=True, bloqueado=False)
        elif estado == 'inativos':
            qs = qs.filter(ativo=False, bloqueado=False)
        elif estado == 'bloqueados':
            qs = qs.filter(bloqueado=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['estado'] = self.request.GET.get('estado', '')
        return ctx


class FornecedorDetailView(FornecedoresMixin, DetailView):
    model = Fornecedor
    template_name = 'fornecedores/fornecedor_detail.html'
    context_object_name = 'fornecedor'


class FornecedorCreateView(FornecedoresMixin, CreateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = FORM_TPL
    success_url = reverse_lazy('fornecedores:lista')
    extra_context = {'titulo': 'Novo Fornecedor'}

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor criado com sucesso.")
        return super().form_valid(form)


class FornecedorUpdateView(FornecedoresMixin, UpdateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = FORM_TPL
    extra_context = {'titulo': 'Editar Fornecedor'}

    def get_success_url(self):
        return reverse('fornecedores:detail', kwargs={'pk': self.object.pk})


class FornecedorDeleteView(FornecedoresMixin, DeleteView):
    model = Fornecedor
    template_name = DEL_TPL
    success_url = reverse_lazy('fornecedores:lista')
    extra_context = {'titulo': 'Eliminar Fornecedor'}

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(self.request, "Fornecedor eliminado.")
            return response
        except ProtectedError:
            messages.error(self.request, "Este fornecedor tem pedidos associados. Bloqueie-o em vez de eliminar.")
            return redirect('fornecedores:detail', pk=self.kwargs['pk'])


class AtivarFornecedorView(FornecedoresMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(Fornecedor, pk=pk)
        f.ativo, f.bloqueado, f.motivo_bloqueio = True, False, ''
        f.save(update_fields=['ativo', 'bloqueado', 'motivo_bloqueio'])
        messages.success(request, "Fornecedor activado.")
        return redirect('fornecedores:detail', pk=pk)


class BloquearFornecedorView(FornecedoresMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(Fornecedor, pk=pk)
        f.bloqueado = True
        f.motivo_bloqueio = request.POST.get('motivo', '').strip()
        f.save(update_fields=['bloqueado', 'motivo_bloqueio'])
        messages.success(request, "Fornecedor bloqueado.")
        return redirect('fornecedores:detail', pk=pk)


# ==============================================================================
# AVALIAÇÕES
# ==============================================================================
class AvaliacaoCreateView(FornecedoresMixin, CreateView):
    model = AvaliacaoFornecedor
    form_class = AvaliacaoForm
    template_name = FORM_TPL

    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get('fornecedor_pk') or kwargs.get('pk')
        self.fornecedor = get_object_or_404(Fornecedor, pk=pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f"Avaliar {self.fornecedor.nome_exibicao}"
        return ctx

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if 'pedido' in form.fields:  # só pedidos deste fornecedor ainda sem avaliação
            form.fields['pedido'].queryset = Pedido.objects.filter(
                fornecedor=self.fornecedor, avaliacao__isnull=True)
        return form

    def form_valid(self, form):
        form.instance.fornecedor = self.fornecedor
        form.instance.avaliador = self.request.user
        messages.success(self.request, "Avaliação registada.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('fornecedores:detail', kwargs={'pk': self.fornecedor.pk})


class AvaliarFornecedorView(AvaliacaoCreateView):
    """URL /<pk>/avaliar/ — mesma lógica, o kwarg chama-se pk."""


class HistoricoFornecedorView(FornecedoresMixin, ListView):
    template_name = 'fornecedores/avaliacao_list.html'
    context_object_name = 'avaliacoes'

    def get_queryset(self):
        self.fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['pk'])
        return self.fornecedor.avaliacoes.select_related('pedido', 'avaliador')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(fornecedor=self.fornecedor, titulo=f"Histórico — {self.fornecedor.nome_exibicao}")
        return ctx


class AvaliacaoListView(FornecedoresMixin, ListView):
    model = AvaliacaoFornecedor
    template_name = 'fornecedores/avaliacao_list.html'
    context_object_name = 'avaliacoes'
    extra_context = {'titulo': 'Avaliações de Fornecedores'}

    def get_queryset(self):
        return super().get_queryset().select_related('fornecedor', 'pedido', 'avaliador')


# ==============================================================================
# CONTACTOS
# ==============================================================================
class ContatoListView(FornecedoresMixin, ListView):
    template_name = 'fornecedores/contato_list.html'
    context_object_name = 'contatos'

    def get_queryset(self):
        self.fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['fornecedor_pk'])
        return self.fornecedor.contatos.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['fornecedor'] = self.fornecedor
        return ctx


class ContatoCreateView(FornecedoresMixin, CreateView):
    model = ContatoFornecedor
    form_class = ContatoForm
    template_name = FORM_TPL
    extra_context = {'titulo': 'Novo Contacto'}

    def form_valid(self, form):
        form.instance.fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['fornecedor_pk'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('fornecedores:contato_lista', kwargs={'fornecedor_pk': self.kwargs['fornecedor_pk']})


class ContatoUpdateView(FornecedoresMixin, UpdateView):
    model = ContatoFornecedor
    form_class = ContatoForm
    template_name = FORM_TPL
    extra_context = {'titulo': 'Editar Contacto'}

    def get_success_url(self):
        return reverse('fornecedores:contato_lista', kwargs={'fornecedor_pk': self.object.fornecedor_id})


class ContatoDeleteView(FornecedoresMixin, DeleteView):
    model = ContatoFornecedor
    template_name = DEL_TPL
    extra_context = {'titulo': 'Eliminar Contacto'}

    def get_success_url(self):
        return reverse('fornecedores:contato_lista', kwargs={'fornecedor_pk': self.object.fornecedor_id})


# ==============================================================================
# PEDIDOS DE COMPRA
# ==============================================================================
class PedidoCompraListView(FornecedoresMixin, ListView):
    model = Pedido
    template_name = 'fornecedores/pedido_list.html'
    context_object_name = 'pedidos'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related('fornecedor')
        estado = self.request.GET.get('estado', '')
        q = self.request.GET.get('q', '').strip()
        if estado:
            qs = qs.filter(status=estado)
        if q:
            qs = qs.filter(Q(numero_pedido__icontains=q) | Q(fornecedor__razao_social__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(estados=Pedido.STATUS_CHOICES, estado=self.request.GET.get('estado', ''),
                   q=self.request.GET.get('q', ''))
        return ctx


class PedidoCompraCreateView(FornecedoresMixin, CreateView):
    model = Pedido
    form_class = PedidoCompraForm
    template_name = FORM_TPL
    extra_context = {'titulo': 'Novo Pedido de Compra'}

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get('fornecedor'):
            initial['fornecedor'] = self.request.GET['fornecedor']
        return initial

    def form_valid(self, form):
        form.instance.solicitante = self.request.user
        messages.success(self.request, "Pedido criado como rascunho.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('fornecedores:pedido_detail', kwargs={'pk': self.object.pk})


class PedidoCompraDetailView(FornecedoresMixin, DetailView):
    model = Pedido
    template_name = 'fornecedores/pedido_detail.html'
    context_object_name = 'pedido'


class PedidoCompraUpdateView(FornecedoresMixin, UpdateView):
    model = Pedido
    form_class = PedidoCompraForm
    template_name = FORM_TPL
    extra_context = {'titulo': 'Editar Pedido'}

    def get_success_url(self):
        return reverse('fornecedores:pedido_detail', kwargs={'pk': self.object.pk})


class PedidoCompraDeleteView(FornecedoresMixin, DeleteView):
    model = Pedido
    template_name = DEL_TPL
    success_url = reverse_lazy('fornecedores:pedido_lista')
    extra_context = {'titulo': 'Eliminar Pedido'}


def _mudar_status(request, pedido, novo, permitidos, msg, **extra):
    if pedido.status not in permitidos:
        messages.error(request, f"Não é possível fazer isto com um pedido '{pedido.get_status_display()}'.")
        return False
    anterior = pedido.status
    pedido.status = novo
    for campo, valor in extra.items():
        setattr(pedido, campo, valor)
    pedido.save()
    HistoricoPedido.objects.create(
        pedido=pedido, status_anterior=anterior, status_novo=novo,
        usuario=request.user, observacoes=msg)
    messages.success(request, msg)
    return True


class EnviarPedidoView(FornecedoresMixin, View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        try:
            pedido.enviar_pedido(request.user)
            messages.success(request, "Pedido enviado.")
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
        return redirect('fornecedores:pedido_detail', pk=pk)


class AprovarPedidoView(FornecedoresMixin, View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        _mudar_status(request, pedido, 'aprovado', ['enviado', 'confirmado'], "Pedido aprovado.",
                      aprovador=request.user, data_aprovacao=timezone.now())
        return redirect('fornecedores:pedido_detail', pk=pk)


class CancelarPedidoView(FornecedoresMixin, View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        _mudar_status(request, pedido, 'cancelado',
                      [s for s, _ in Pedido.STATUS_CHOICES if s not in ('finalizado', 'cancelado')],
                      "Pedido cancelado.", motivo_cancelamento=request.POST.get('motivo', '').strip())
        return redirect('fornecedores:pedido_detail', pk=pk)


class ReceberPedidoView(FornecedoresMixin, View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        _mudar_status(request, pedido, 'recebido',
                      ['aprovado', 'confirmado', 'em_producao', 'em_transito', 'recebido_parcial'],
                      "Pedido recebido.", data_entrega_real=date.today())
        return redirect('fornecedores:pedido_detail', pk=pk)


class ImprimirPedidoView(FornecedoresMixin, DetailView):
    model = Pedido
    template_name = 'fornecedores/pedido_imprimir.html'
    context_object_name = 'pedido'


class PedidoPDFView(FornecedoresMixin, DetailView):
    model = Pedido

    def render_to_response(self, context, **kwargs):
        p = self.object
        resp = HttpResponse(content_type='application/pdf')
        resp['Content-Disposition'] = f'inline; filename="{p.numero_pedido}.pdf"'
        c = canvas.Canvas(resp, pagesize=A4)
        w, h = A4
        y = h - 2 * cm
        c.setFont('Helvetica-Bold', 14)
        c.drawString(2 * cm, y, f"PEDIDO DE COMPRA {p.numero_pedido}")
        y -= 1 * cm
        c.setFont('Helvetica', 10)
        for linha in (f"Fornecedor: {p.fornecedor.razao_social}", f"NIF/BI: {p.fornecedor.nif_bi}",
                      f"Data: {p.data_pedido:%d/%m/%Y}", f"Estado: {p.get_status_display()}"):
            c.drawString(2 * cm, y, linha)
            y -= 0.6 * cm
        y -= 0.4 * cm
        c.setFont('Helvetica-Bold', 9)
        c.drawString(2 * cm, y, "Produto")
        c.drawRightString(12 * cm, y, "Qtd")
        c.drawRightString(15.5 * cm, y, "P.Unit.")
        c.drawRightString(w - 2 * cm, y, "Total")
        y -= 0.6 * cm
        c.setFont('Helvetica', 9)
        for it in p.itens.select_related('produto'):
            if y < 4 * cm:
                c.showPage()
                y = h - 2 * cm
                c.setFont('Helvetica', 9)
            c.drawString(2 * cm, y, it.produto.nome_comercial[:45])
            c.drawRightString(12 * cm, y, str(it.quantidade))
            c.drawRightString(15.5 * cm, y, kz(it.preco_unitario))
            c.drawRightString(w - 2 * cm, y, kz(it.total))
            y -= 0.5 * cm
        y -= 0.5 * cm
        c.setFont('Helvetica-Bold', 11)
        c.drawRightString(w - 2 * cm, y, f"TOTAL: {kz(p.total)}")
        c.showPage()
        c.save()
        return resp


class PedidoXMLView(FornecedoresMixin, DetailView):
    model = Pedido

    def render_to_response(self, context, **kwargs):
        p = self.object
        root = ET.Element('PedidoCompra', numero=p.numero_pedido, estado=p.status)
        ET.SubElement(root, 'Fornecedor', nif=p.fornecedor.nif_bi).text = p.fornecedor.razao_social
        ET.SubElement(root, 'Data').text = p.data_pedido.isoformat()
        itens = ET.SubElement(root, 'Itens')
        for it in p.itens.select_related('produto'):
            ET.SubElement(itens, 'Item', codigo=it.produto.codigo_interno,
                          quantidade=str(it.quantidade), precoUnitario=str(it.preco_unitario),
                          total=str(it.total)).text = it.produto.nome_comercial
        ET.SubElement(root, 'Total').text = str(p.total)
        resp = HttpResponse(ET.tostring(root, encoding='utf-8', xml_declaration=True),
                            content_type='application/xml')
        resp['Content-Disposition'] = f'attachment; filename="{p.numero_pedido}.xml"'
        return resp


# ==============================================================================
# CONTRATOS
# ==============================================================================
class ContratoListView(FornecedoresMixin, ListView):
    model = ContratoFornecedor
    template_name = 'fornecedores/contrato_list.html'
    context_object_name = 'contratos'

    def get_queryset(self):
        return super().get_queryset().select_related('fornecedor')


class ContratoCreateView(FornecedoresMixin, CreateView):
    model = ContratoFornecedor
    form_class = ContratoForm
    template_name = FORM_TPL
    success_url = reverse_lazy('fornecedores:contrato_lista')
    extra_context = {'titulo': 'Novo Contrato'}

    def form_valid(self, form):
        form.instance.usuario_criador = self.request.user
        return super().form_valid(form)


class ContratoDetailView(FornecedoresMixin, DetailView):
    model = ContratoFornecedor
    template_name = 'fornecedores/contrato_detail.html'
    context_object_name = 'contrato'


class ContratoUpdateView(FornecedoresMixin, UpdateView):
    model = ContratoFornecedor
    form_class = ContratoForm
    template_name = FORM_TPL
    success_url = reverse_lazy('fornecedores:contrato_lista')
    extra_context = {'titulo': 'Editar Contrato'}


class RenovarContratoView(FornecedoresMixin, View):
    def post(self, request, pk):
        c = get_object_or_404(ContratoFornecedor, pk=pk)
        try:
            meses = max(1, int(request.POST.get('meses', 12)))
        except ValueError:
            meses = 12
        base = max(c.data_fim, date.today())
        c.data_fim = base + timedelta(days=30 * meses)
        c.ativo = True
        c.save(update_fields=['data_fim', 'ativo'])
        messages.success(request, f"Contrato renovado até {c.data_fim:%d/%m/%Y}.")
        return redirect('fornecedores:contrato_detail', pk=pk)


class EncerrarContratoView(FornecedoresMixin, View):
    def post(self, request, pk):
        c = get_object_or_404(ContratoFornecedor, pk=pk)
        c.ativo = False
        c.data_fim = min(c.data_fim, date.today())
        c.save(update_fields=['ativo', 'data_fim'])
        messages.success(request, "Contrato encerrado.")
        return redirect('fornecedores:contrato_detail', pk=pk)


# ==============================================================================
# COTAÇÕES
# ==============================================================================
class CotacaoListView(FornecedoresMixin, ListView):
    model = CotacaoFornecedor
    template_name = 'fornecedores/cotacao_list.html'
    context_object_name = 'cotacoes'

    def get_queryset(self):
        return super().get_queryset().select_related('fornecedor')


class CotacaoCreateView(FornecedoresMixin, CreateView):
    model = CotacaoFornecedor
    form_class = CotacaoForm
    template_name = FORM_TPL
    success_url = reverse_lazy('fornecedores:cotacao_lista')
    extra_context = {'titulo': 'Nova Cotação'}

    def form_valid(self, form):
        form.instance.usuario_criador = self.request.user
        return super().form_valid(form)


class CotacaoDetailView(FornecedoresMixin, DetailView):
    model = CotacaoFornecedor
    template_name = 'fornecedores/cotacao_detail.html'
    context_object_name = 'cotacao'


class CompararCotacaoView(FornecedoresMixin, DetailView):
    model = CotacaoFornecedor
    template_name = 'fornecedores/cotacao_comparar.html'
    context_object_name = 'cotacao'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['outras'] = (CotacaoFornecedor.objects
                         .filter(ativo=True, data_validade__gte=date.today())
                         .exclude(pk=self.object.pk).select_related('fornecedor').order_by('total'))
        return ctx


# ==============================================================================
# QUALIFICAÇÃO, RANKING E RELATÓRIOS (todos usam relatorio.html)
# ==============================================================================
class RelatorioBase(FornecedoresMixin, TemplateView):
    template_name = 'fornecedores/relatorio.html'
    titulo = ''
    com_periodo = False

    def periodo(self):
        hoje = date.today()
        try:
            ini = date.fromisoformat(self.request.GET.get('inicio', ''))
        except ValueError:
            ini = hoje.replace(day=1)
        try:
            fim = date.fromisoformat(self.request.GET.get('fim', ''))
        except ValueError:
            fim = hoje
        return ini, fim

    def dados(self):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(titulo=self.titulo, com_periodo=self.com_periodo, **self.dados())
        if self.com_periodo:
            ctx['inicio'], ctx['fim'] = self.periodo()
        return ctx


class QualificacaoFornecedorView(RelatorioBase):
    titulo = 'Qualificação de Fornecedores'

    def dados(self):
        hoje = date.today()
        linhas = []
        for f in Fornecedor.objects.filter(ativo=True).prefetch_related('documentos'):
            vencidos = sum(1 for d in f.documentos.all() if d.data_validade and d.data_validade < hoje)
            linhas.append([f.nome_exibicao, f.nota_avaliacao or '—', f"{f.pontualidade_entrega}%",
                           vencidos, 'Bloqueado' if f.bloqueado else 'Qualificado' if (f.nota_avaliacao or 0) >= 7 and not vencidos else 'Atenção'])
        return {'cabecalho': ['Fornecedor', 'Nota', 'Pontualidade', 'Docs vencidos', 'Situação'], 'linhas': linhas}


class RankingFornecedorView(RelatorioBase):
    titulo = 'Ranking de Fornecedores'

    def dados(self):
        qs = (Fornecedor.objects.annotate(media=Avg('avaliacoes__nota_geral'),
                                          n_pedidos=Count('pedidos', distinct=True))
              .filter(media__isnull=False).order_by('-media')[:20])
        linhas = [[i, f.nome_exibicao, f"{f.media:.2f}", f.n_pedidos] for i, f in enumerate(qs, 1)]
        return {'cabecalho': ['#', 'Fornecedor', 'Nota média', 'Pedidos'], 'linhas': linhas}


class FornecedorRelatoriosView(FornecedoresMixin, TemplateView):
    template_name = 'fornecedores/relatorios_index.html'


class RelatorioComprasView(RelatorioBase):
    titulo = 'Relatório de Compras'
    com_periodo = True

    def dados(self):
        ini, fim = self.periodo()
        qs = (Fornecedor.objects.annotate(
            total=Sum('pedidos__total', filter=Q(pedidos__status__in=ESTADOS_COMPRA,
                                                 pedidos__data_pedido__range=(ini, fim))),
            n=Count('pedidos', filter=Q(pedidos__status__in=ESTADOS_COMPRA,
                                        pedidos__data_pedido__range=(ini, fim)), distinct=True))
            .filter(n__gt=0).order_by('-total'))
        total_geral = sum((f.total or 0) for f in qs)
        return {'cards': [('Total comprado', kz(total_geral)), ('Fornecedores', qs.count())],
                'cabecalho': ['Fornecedor', 'Pedidos', 'Total'],
                'linhas': [[f.nome_exibicao, f.n, kz(f.total)] for f in qs]}


class RelatorioPerformanceView(RelatorioBase):
    titulo = 'Performance de Fornecedores'

    def dados(self):
        hoje = date.today()
        abertos = ['enviado', 'confirmado', 'aprovado', 'em_producao', 'em_transito', 'recebido_parcial']
        qs = Fornecedor.objects.annotate(
            atrasados=Count('pedidos', filter=Q(pedidos__status__in=abertos,
                                                pedidos__data_entrega_prevista__lt=hoje), distinct=True),
            media=Avg('avaliacoes__nota_geral')).order_by('-atrasados', 'razao_social')
        return {'cards': [('Pedidos atrasados', sum(f.atrasados for f in qs))],
                'cabecalho': ['Fornecedor', 'Pontualidade', 'Nota média', 'Pedidos atrasados'],
                'linhas': [[f.nome_exibicao, f"{f.pontualidade_entrega}%",
                            f"{f.media:.2f}" if f.media else '—', f.atrasados] for f in qs]}


class RelatorioPagamentosView(RelatorioBase):
    titulo = 'Pagamentos a Fornecedores (por liquidar)'

    def dados(self):
        pedidos = (Pedido.objects.filter(status__in=['aprovado', 'recebido'])
                   .select_related('fornecedor', 'condicao_pagamento').order_by('data_pedido'))
        linhas, total = [], Decimal('0')
        for p in pedidos:
            prazo = p.condicao_pagamento.prazo_dias if p.condicao_pagamento else 0
            venc = p.data_pedido + timedelta(days=prazo)
            total += p.total
            linhas.append([p.numero_pedido, p.fornecedor.nome_exibicao,
                           p.condicao_pagamento.nome if p.condicao_pagamento else '—',
                           venc.strftime('%d/%m/%Y'), kz(p.total)])
        return {'cards': [('Total por liquidar', kz(total))],
                'cabecalho': ['Pedido', 'Fornecedor', 'Condição', 'Vencimento', 'Valor'], 'linhas': linhas}


# ==============================================================================
# IMPORTAR / EXPORTAR
# ==============================================================================
class ImportarFornecedoresView(FornecedoresMixin, View):
    """CSV com colunas: razao_social, nif_bi, email_principal, telefone_principal,
    endereco, cidade, provincia (as restantes recebem valores por defeito)."""

    def post(self, request):
        arquivo = request.FILES.get('arquivo_fornecedores')
        if not arquivo or not arquivo.name.lower().endswith('.csv'):
            messages.error(request, "Seleccione um ficheiro .csv.")
            return redirect('fornecedores:lista')

        texto = arquivo.read().decode('utf-8-sig').splitlines()
        delim = ';' if texto and texto[0].count(';') > texto[0].count(',') else ','
        criados = erros = 0
        for row in csv.DictReader(texto, delimiter=delim):
            try:
                Fornecedor.objects.update_or_create(
                    nif_bi=row['nif_bi'].strip(),
                    defaults={
                        'razao_social': row['razao_social'].strip(),
                        'email_principal': row.get('email_principal', '').strip(),
                        'telefone_principal': row.get('telefone_principal', '').strip(),
                        'endereco': row.get('endereco', '-').strip() or '-',
                        'cidade': row.get('cidade', '-').strip() or '-',
                        'provincia': row.get('provincia', 'LUA').strip() or 'LUA',
                        'numero': 'S/N', 'bairro': '-', 'postal': '00000-000',
                    })
                criados += 1
            except Exception:
                erros += 1
        messages.success(request, f"{criados} fornecedor(es) importado(s)/actualizado(s).")
        if erros:
            messages.warning(request, f"{erros} linha(s) ignorada(s) por dados inválidos.")
        return redirect('fornecedores:lista')


class ExportarFornecedoresView(FornecedoresMixin, View):
    def get(self, request):
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="fornecedores_{date.today()}.csv"'
        resp.write('\ufeff')  # Excel reconhece UTF-8
        w = csv.writer(resp, delimiter=';')
        w.writerow(['Código', 'Razão Social', 'NIF/BI', 'Categoria', 'Telefone', 'Email', 'Estado', 'Nota'])
        for f in Fornecedor.objects.all():
            w.writerow([f.codigo_fornecedor, f.razao_social, f.nif_bi, f.get_categoria_display(),
                        f.telefone_principal, f.email_principal,
                        'Bloqueado' if f.bloqueado else 'Activo' if f.ativo else 'Inactivo',
                        f.nota_avaliacao if f.nota_avaliacao is not None else ''])
        return resp


# ==============================================================================
# AJAX
# ==============================================================================
class BuscarFornecedorAjaxView(FornecedoresMixin, View):
    def get(self, request):
        term = request.GET.get('q', '').strip()
        qs = Fornecedor.objects.filter(ativo=True, bloqueado=False).filter(
            Q(razao_social__icontains=term) | Q(nome_fantasia__icontains=term) | Q(nif_bi__icontains=term)
        )[:10]
        return JsonResponse({'results': [{'id': f.id, 'text': f"{f.nome_exibicao} (NIF: {f.nif_bi})"} for f in qs]})


class ValidarNifView(FornecedoresMixin, View):
    def get(self, request):
        nif = request.GET.get('nif', '').strip()
        if not nif:
            return JsonResponse({'valido': False, 'mensagem': 'NIF/BI é obrigatório.'}, status=400)
        if len(nif) not in (10, 14):
            return JsonResponse({'valido': False, 'mensagem': 'NIF: 10 dígitos. BI: 14 caracteres.'})
        qs = Fornecedor.objects.filter(nif_bi=nif)
        if request.GET.get('excluir'):
            qs = qs.exclude(pk=request.GET['excluir'])
        if qs.exists():
            return JsonResponse({'valido': False, 'mensagem': f'NIF/BI {nif} já está registado.'})
        return JsonResponse({'valido': True, 'mensagem': 'NIF/BI válido.'})


class CalcularPrazoEntregaView(FornecedoresMixin, View):
    def get(self, request):
        f = Fornecedor.objects.filter(pk=request.GET.get('fornecedor_id') or 0).first()
        dias = f.prazo_entrega_dias if f else 7
        return JsonResponse({'prazo_dias': dias,
                             'data_prevista': (date.today() + timedelta(days=dias)).isoformat(),
                             'padrao': f is None})


# ==============================================================================
# COMUNICAÇÃO
# ==============================================================================
class ComunicacaoListView(FornecedoresMixin, ListView):
    model = Fornecedor
    template_name = 'fornecedores/comunicacao_list.html'
    context_object_name = 'fornecedores'
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)


class EnviarEmailView(FornecedoresMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(Fornecedor, pk=pk)
        if not f.email_principal:
            messages.error(request, "Este fornecedor não tem email principal.")
        else:
            try:
                send_mail(request.POST.get('assunto', 'Comunicação'), request.POST.get('corpo', ''),
                          getattr(settings, 'DEFAULT_FROM_EMAIL', None), [f.email_principal])
                messages.success(request, f"Email enviado para {f.email_principal}.")
            except Exception as e:
                messages.error(request, f"Falha ao enviar email: {e}")
        return redirect(request.POST.get('next') or reverse('fornecedores:detail', kwargs={'pk': pk}))


class EnviarWhatsAppView(FornecedoresMixin, View):
    def post(self, request, pk):
        f = get_object_or_404(Fornecedor, pk=pk)
        numero = ''.join(c for c in f.whatsapp if c.isdigit())
        if not numero:
            messages.error(request, "Este fornecedor não tem WhatsApp registado.")
            return redirect('fornecedores:detail', pk=pk)
        texto = request.POST.get('mensagem', 'Olá, gostaríamos de falar sobre o nosso pedido.')
        return redirect(f"https://api.whatsapp.com/send?phone={numero}&text={quote(texto)}")


# ==============================================================================
# API
# ==============================================================================
class BuscarProdutosFornecedorAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        fid = request.GET.get('fornecedor')
        if not fid:
            return Response({'detail': "O parâmetro 'fornecedor' é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)
        produtos = Produto.objects.filter(fornecedor_id=fid, ativo=True).values(
            'id', 'codigo_interno', 'nome_comercial', 'preco_custo')
        return Response(list(produtos))


class CalcularFreteAPIView(APIView):
    """PLACEHOLDER: regra de frete fictícia até haver tabela de transportadoras."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            valor = Decimal(request.GET.get('valor_total', '0'))
        except InvalidOperation:
            return Response({'detail': "'valor_total' deve ser numérico."}, status=status.HTTP_400_BAD_REQUEST)
        frete = Decimal('0.00') if valor >= 500 else Decimal('10.00') + valor * Decimal('0.02')
        return Response({'frete': frete.quantize(Decimal('0.01')), 'prazo_dias': 3})


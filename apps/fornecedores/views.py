# apps/fornecedores/views.py
from datetime import date, timedelta

from django.db.models import Q, Avg, Count, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.http import JsonResponse, HttpResponse
from django.contrib import messages

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    ContatoFornecedor, ContratoFornecedor, CotacaoFornecedor, Fornecedor, Pedido, AvaliacaoFornecedor
)
from .forms import AvaliacaoForm, ContatoForm, ContratoForm, CotacaoForm, FornecedorForm, PedidoCompraForm
from .filters import FornecedorFilter, PedidoCompraFilter
from .api.serializers import (
    FornecedorSerializer, PedidoCompraSerializer, AvaliacaoFornecedorSerializer, ProdutoSerializer
)
from django.contrib.auth.mixins import AccessMixin


class EmpresaQuerysetMixin:
    """
    Filtra automaticamente queryset pelo usuário logado e sua empresa.
    """
    def get_queryset(self):
        qs = super().get_queryset()  # super() deve ser ListView com model definido
        return qs.filter(empresa=self.request.user.empresa)


class PermissaoAcaoMixin(AccessMixin):
    # CRÍTICO: Definir esta variável na View
    acao_requerida = None 

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            # Tenta obter o Funcionario (ligação fundamental)
            funcionario = request.user.funcionario 
        except Exception:
            messages.error(request, "Acesso negado. O seu usuário não está ligado a um registro de funcionário.")
            return self.handle_no_permission()

        if self.acao_requerida:
            # Usa a lógica dinâmica do modelo Funcionario (que já criámos)
            if not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.")
                return redirect(reverse_lazy('core:dashboard'))

        return super().dispatch(request, *args, **kwargs)




class FornecedorViewSet(viewsets.ModelViewSet):
    serializer_class = FornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = FornecedorFilter
    search_fields = ['nome_fantasia', 'razao_social', 'nif', 'email_principal']
    ordering_fields = ['nome_fantasia', 'avaliacao', 'total_comprado', 'created_at']
    ordering = ['nome_fantasia']
    
    def get_queryset(self):
        return Fornecedor.objects.filter(
            empresa=self.request.user.empresa
        ).select_related('empresa').prefetch_related('contatos', 'documentos')
    
    def perform_create(self, serializer):
        serializer.save(empresa=self.request.user.empresa)
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Estatísticas para o dashboard de fornecedores"""
        queryset = self.get_queryset()
        
        stats = {
            'total_fornecedores': queryset.count(),
            'fornecedores_ativos': queryset.filter(status='ativo').count(),
            'fornecedores_inativos': queryset.filter(status='inativo').count(),
            'fornecedores_bloqueados': queryset.filter(status='bloqueado').count(),
            'avaliacao_media': queryset.aggregate(Avg('avaliacao'))['avaliacao__avg'] or 0,
            'total_comprado_mes': self.get_total_comprado_mes(),
            'pedidos_pendentes': self.get_pedidos_pendentes(),
        }
        
        return Response(stats)
    
    def get_total_comprado_mes(self):
        """Total comprado no mês atual"""
        inicio_mes = date.today().replace(day=1)
        return Pedido.objects.filter(
            empresa=self.request.user.empresa,
            data_pedido__gte=inicio_mes,
            status='finalizado'
        ).aggregate(Sum('total'))['total__sum'] or 0
    
    def get_pedidos_pendentes(self):
        """Número de pedidos pendentes"""
        return Pedido.objects.filter(
            empresa=self.request.user.empresa,
            status__in=['enviado', 'confirmado', 'entregue_parcial']
        ).count()
    
    @action(detail=True, methods=['get'])
    def pedidos(self, request, pk=None):
        """Lista pedidos de um fornecedor específico"""
        fornecedor = self.get_object()
        pedidos = PedidoCompra.objects.filter(
            fornecedor=fornecedor
        ).order_by('-data_pedido')
        
        serializer = PedidoCompraSerializer(pedidos, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def avaliacoes(self, request, pk=None):
        """Lista avaliações de um fornecedor específico"""
        fornecedor = self.get_object()
        avaliacoes = AvaliacaoFornecedor.objects.filter(
            fornecedor=fornecedor
        ).order_by('-created_at')
        
        serializer = AvaliacaoFornecedorSerializer(avaliacoes, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def avaliar(self, request, pk=None):
        """Avalia um fornecedor"""
        fornecedor = self.get_object()
        
        data = request.data.copy()
        data['fornecedor'] = fornecedor.id
        data['usuario'] = request.user.id
        
        serializer = AvaliacaoFornecedorSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            
            # Recalcular avaliação média do fornecedor
            media = AvaliacaoFornecedor.objects.filter(
                fornecedor=fornecedor
            ).aggregate(Avg('nota'))['nota__avg']
            
            fornecedor.avaliacao = round(media, 2) if media else 0
            fornecedor.save()
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def melhores_avaliados(self, request):
        """Fornecedores com melhor avaliação"""
        fornecedores = self.get_queryset().filter(
            status='ativo',
            avaliacao__gt=0
        ).order_by('-avaliacao')[:10]
        
        serializer = self.get_serializer(fornecedores, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def com_pedidos_atrasados(self, request):
        """Fornecedores com pedidos atrasados"""
        hoje = date.today()
        fornecedores_ids = Pedido.objects.filter(
            empresa=self.request.user.empresa,
            status__in=['enviado', 'confirmado', 'entregue_parcial'],
            data_prevista_entrega__lt=hoje
        ).values_list('fornecedor_id', flat=True).distinct()
        
        fornecedores = self.get_queryset().filter(id__in=fornecedores_ids)
        serializer = self.get_serializer(fornecedores, many=True)
        return Response(serializer.data)

class PedidoCompraViewSet(viewsets.ModelViewSet):
    serializer_class = PedidoCompraSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PedidoCompraFilter
    search_fields = ['numero_pedido', 'fornecedor__nome_fantasia', 'observacoes']
    ordering_fields = ['data_pedido', 'data_prevista_entrega', 'total', 'status']
    ordering = ['-data_pedido']
    
    def get_queryset(self):
        return Pedido.objects.filter(
            empresa=self.request.user.empresa
        ).select_related('fornecedor', 'usuario_criacao').prefetch_related('itens')
    
    def perform_create(self, serializer):
        serializer.save(
            empresa=self.request.user.empresa,
            usuario_criacao=self.request.user
        )
    
    @action(detail=True, methods=['post'])
    def confirmar(self, request, pk=None):
        """Confirma um pedido de compra"""
        pedido = self.get_object()
        
        if pedido.status != 'enviado':
            return Response(
                {'error': 'Pedido deve estar com status "enviado" para ser confirmado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pedido.status = 'confirmado'
        pedido.usuario_aprovacao = request.user
        pedido.data_aprovacao = timezone.now()
        pedido.save()
        
        return Response({'message': 'Pedido confirmado com sucesso'})
    
    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """Cancela um pedido de compra"""
        pedido = self.get_object()
        
        if pedido.status in ['finalizado', 'cancelado']:
            return Response(
                {'error': 'Não é possível cancelar pedido finalizado ou já cancelado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        motivo = request.data.get('motivo', '')
        pedido.status = 'cancelado'
        pedido.observacoes += f"\nCancelado em {date.today()}: {motivo}"
        pedido.save()
        
        return Response({'message': 'Pedido cancelado com sucesso'})
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Estatísticas de pedidos para dashboard"""
        queryset = self.get_queryset()
        hoje = date.today()
        
        stats = {
            'total_pedidos': queryset.count(),
            'pedidos_pendentes': queryset.filter(
                status__in=['enviado', 'confirmado', 'entregue_parcial']
            ).count(),
            'pedidos_atrasados': queryset.filter(
                status__in=['enviado', 'confirmado', 'entregue_parcial'],
                data_prevista_entrega__lt=hoje
            ).count(),
            'total_pendente': queryset.filter(
                status__in=['enviado', 'confirmado', 'entregue_parcial']
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'pedidos_mes': queryset.filter(
                data_pedido__month=hoje.month,
                data_pedido__year=hoje.year
            ).count(),
        }
        
        return Response(stats)


from django.views.generic import (
    ListView, 
    DetailView, 
    CreateView, 
    UpdateView, 
    DeleteView
)
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from .models import Fornecedor
# from .forms import FornecedorForm # Crie este formulário para as views de edição

# Defina a URL de sucesso centralizada (muda se usar o Django 5.0 com success_url)
SUCCESS_URL = reverse_lazy('fornecedores:lista') 

# --- MIXINS CRÍTICOS (Garantir Segurança e Filtro por Empresa) ---

class BaseFornecedorMixin(LoginRequiredMixin):
    """Mixins base para garantir autenticação."""
    model = Fornecedor
    context_object_name = 'fornecedor' # Nome do objeto singular no template (para Detail)
    
    def get_queryset(self):
        """Filtra objetos apenas para a empresa do utilizador logado."""
        # Assume que request.user.empresa existe
        return self.model.objects.filter(empresa=self.request.user.empresa)


class FornecedorListView(EmpresaQuerysetMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_fornecedores'
    model = Fornecedor
    paginate_by = 25
    template_name = 'fornecedores/fornecedor_list.html'
    context_object_name = 'fornecedores'



class FornecedorDetailView(EmpresaQuerysetMixin, DetailView):
    """
    Exibe os detalhes de um fornecedor específico.
    Procura por template: fornecedores/fornecedor_detail.html
    """
    template_name = 'fornecedores/fornecedor_detail.html'
    
    # Não precisa de get_queryset se usar BaseFornecedorMixin

class FornecedorCreateView(EmpresaQuerysetMixin, CreateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = 'fornecedores/fornecedor_form.html'
    success_url = reverse_lazy('fornecedores:lista')

    def form_valid(self, form):
        # Associa o fornecedor à empresa do usuário logado
        form.instance.empresa = self.request.user.empresa
        return super().form_valid(form)

from django.views.generic.edit import UpdateView
from .models import Fornecedor

class FornecedorUpdateView(EmpresaQuerysetMixin, UpdateView):
    model = Fornecedor  # informa o modelo
    template_name = 'fornecedores/fornecedor_form.html'
    fields = [
        'codigo_fornecedor', 'razao_social', 'nome_fantasia', 'tipo_pessoa',
        'categoria', 'porte', 'foto', 'nif_bi', 'endereco', 'numero',
        'bairro', 'cidade', 'provincia', 'postal', 'pais',
        'telefone_principal', 'telefone_secundario', 'whatsapp', 'email_principal',
        'email_financeiro', 'email_comercial', 'site', 'condicao_pagamento_padrao',
        'prazo_entrega_dias', 'valor_minimo_pedido', 'banco_principal', 'agencia',
        'conta_corrente', 'permite_devolucao', 'prazo_devolucao_dias',
        'trabalha_consignacao', 'aceita_cartao', 'entrega_proprio', 'nota_avaliacao',
        'pontualidade_entrega', 'qualidade_produtos', 'ativo', 'bloqueado',
        'motivo_bloqueio', 'observacoes', 'observacoes_internas'
    ]
    success_url = '/fornecedores/'  # ou reverse_lazy('fornecedores:list')
   

class FornecedorDeleteView(EmpresaQuerysetMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'acessar_fornecedores'
    
    template_name = 'fornecedores/fornecedor_confirm_delete.html'
    success_url = SUCCESS_URL
# =====================================
# FORNECEDORES CRUD
# =====================================




# =====================================
# AÇÕES ESPECIAIS FORNECEDORES
# =====================================
class AtivarFornecedorView(View):
    def post(self, request, pk):
        fornecedor = get_object_or_404(Fornecedor, pk=pk)
        fornecedor.ativo = True
        fornecedor.save()
        messages.success(request, "Fornecedor ativado com sucesso.")
        return redirect("fornecedores:detail", pk=pk)

class BloquearFornecedorView(View):
    def post(self, request, pk):
        fornecedor = get_object_or_404(Fornecedor, pk=pk)
        fornecedor.ativo = False
        fornecedor.save()
        messages.success(request, "Fornecedor bloqueado com sucesso.")
        return redirect("fornecedores:detail", pk=pk)

class AvaliarFornecedorView(CreateView):
    model = AvaliacaoFornecedor
    form_class = AvaliacaoForm
    template_name = "fornecedores/avaliar.html"

    def form_valid(self, form):
        fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['pk'])
        form.instance.fornecedor = fornecedor
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("fornecedores:detail", kwargs={"pk": self.kwargs["pk"]})

class HistoricoFornecedorView(ListView):
    model = AvaliacaoFornecedor
    template_name = "fornecedores/historico.html"
    context_object_name = "historico"

    def get_queryset(self):
        fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['pk'])
        return AvaliacaoFornecedor.objects.filter(fornecedor=fornecedor)

# =====================================
# CONTATOS
# =====================================
class ContatoListView(ListView):
    model = ContatoFornecedor
    template_name = "contatos/lista.html"
    context_object_name = "contatos"

    def get_queryset(self):
        return ContatoFornecedor.objects.filter(fornecedor_id=self.kwargs['fornecedor_pk'])

class ContatoCreateView(CreateView):
    model = ContatoFornecedor
    form_class = ContatoForm
    template_name = "contatos/form.html"

    def form_valid(self, form):
        fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['fornecedor_pk'])
        form.instance.fornecedor = fornecedor
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("fornecedores:contato_lista", kwargs={"fornecedor_pk": self.kwargs["fornecedor_pk"]})

class ContatoUpdateView(UpdateView):
    model = ContatoFornecedor
    form_class = ContatoForm
    template_name = "contatos/form.html"

    def get_success_url(self):
        return reverse_lazy("fornecedores:contato_lista", kwargs={"fornecedor_pk": self.object.fornecedor.pk})

class ContatoDeleteView(DeleteView):
    model = ContatoFornecedor
    template_name = "contatos/confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy("fornecedores:contato_lista", kwargs={"fornecedor_pk": self.object.fornecedor.pk})

# =====================================
# PEDIDOS DE COMPRA CRUD E STATUS
# =====================================
class PedidoCompraListView(EmpresaQuerysetMixin, ListView):
    model = Pedido
    template_name = "pedidos/lista.html"
    context_object_name = "pedidos"

class PedidoCompraCreateView(CreateView):
    model = Pedido
    form_class = PedidoCompraForm
    template_name = "pedidos/form.html"
    success_url = reverse_lazy("fornecedores:pedido_lista")

class PedidoCompraDetailView(DetailView):
    model = Pedido
    template_name = "pedidos/detail.html"
    context_object_name = "pedido"

class PedidoCompraUpdateView(UpdateView):
    model = Pedido
    form_class = PedidoCompraForm
    template_name = "pedidos/form.html"
    success_url = reverse_lazy("fornecedores:pedido_lista")

class PedidoCompraDeleteView(DeleteView):
    model = Pedido
    template_name = "pedidos/confirm_delete.html"
    success_url = reverse_lazy("fornecedores:pedido_lista")

# Status actions
class AprovarPedidoView(View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        pedido.status = "APROVADO"
        pedido.save()
        messages.success(request, "Pedido aprovado.")
        return redirect("fornecedores:pedido_detail", pk=pk)

class EnviarPedidoView(View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        pedido.status = "ENVIADO"
        pedido.save()
        messages.success(request, "Pedido enviado.")
        return redirect("fornecedores:pedido_detail", pk=pk)

class CancelarPedidoView(View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        pedido.status = "CANCELADO"
        pedido.save()
        messages.success(request, "Pedido cancelado.")
        return redirect("fornecedores:pedido_detail", pk=pk)

class ReceberPedidoView(View):
    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        pedido.status = "RECEBIDO"
        pedido.save()
        messages.success(request, "Pedido recebido.")
        return redirect("fornecedores:pedido_detail", pk=pk)

# Documentos
class ImprimirPedidoView(DetailView):
    model = Pedido
    template_name = "pedidos/imprimir.html"

class PedidoPDFView(DetailView):
    model = Pedido
    template_name = "pedidos/pdf.html"  # depois integre com WeasyPrint ou ReportLab

class PedidoXMLView(DetailView):
    model = Pedido
    template_name = "pedidos/xml.html"  # gere XML no template ou Response

# =====================================
# CONTRATOS CRUD E STATUS
# =====================================
class ContratoListView(ListView):
    model = ContratoFornecedor
    template_name = "contratos/lista.html"
    context_object_name = "contratos"

class ContratoCreateView(CreateView):
    model = ContratoFornecedor
    form_class = ContratoForm
    template_name = "contratos/form.html"
    success_url = reverse_lazy("fornecedores:contrato_lista")

class ContratoDetailView(DetailView):
    model = ContratoFornecedor
    template_name = "contratos/detail.html"
    context_object_name = "contrato"

class ContratoUpdateView(UpdateView):
    model = ContratoFornecedor
    form_class = ContratoForm
    template_name = "contratos/form.html"
    success_url = reverse_lazy("fornecedores:contrato_lista")

class RenovarContratoView(View):
    def post(self, request, pk):
        contrato = get_object_or_404(ContratoFornecedor, pk=pk)
        contrato.renovar()
        messages.success(request, "Contrato renovado.")
        return redirect("fornecedores:contrato_detail", pk=pk)

class EncerrarContratoView(View):
    def post(self, request, pk):
        contrato = get_object_or_404(ContratoFornecedor, pk=pk)
        contrato.encerrar()
        messages.success(request, "Contrato encerrado.")
        return redirect("fornecedores:contrato_detail", pk=pk)

# =====================================
# AVALIAÇÕES E QUALIFICAÇÃO
# =====================================
class AvaliacaoListView(ListView):
    model = AvaliacaoFornecedor
    template_name = "avaliacoes/lista.html"
    context_object_name = "avaliacoes"

class AvaliacaoCreateView(CreateView):
    model = AvaliacaoFornecedor
    form_class = AvaliacaoForm
    template_name = "avaliacoes/form.html"

    def form_valid(self, form):
        fornecedor = get_object_or_404(Fornecedor, pk=self.kwargs['fornecedor_pk'])
        form.instance.fornecedor = fornecedor
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("fornecedores:detail", kwargs={"pk": self.kwargs["fornecedor_pk"]})

class QualificacaoFornecedorView(TemplateView):
    template_name = "avaliacoes/qualificacao.html"

class RankingFornecedorView(TemplateView):
    template_name = "avaliacoes/ranking.html"

# =====================================
# COTAÇÕES CRUD
# =====================================
class CotacaoListView(ListView):
    model = CotacaoFornecedor
    template_name = "cotacoes/lista.html"
    context_object_name = "cotacoes"

class CotacaoCreateView(CreateView):
    model = CotacaoFornecedor
    form_class = CotacaoForm
    template_name = "cotacoes/form.html"
    success_url = reverse_lazy("fornecedores:cotacao_lista")

class CotacaoDetailView(DetailView):
    model = CotacaoFornecedor
    template_name = "cotacoes/detail.html"

class CompararCotacaoView(DetailView):
    model = CotacaoFornecedor
    template_name = "cotacoes/comparar.html"

# =====================================
# RELATÓRIOS
# =====================================
class FornecedorRelatoriosView(TemplateView):
    template_name = "relatorios/fornecedores.html"

class RelatorioComprasView(TemplateView):
    template_name = "relatorios/compras.html"

class RelatorioPerformanceView(TemplateView):
    template_name = "relatorios/performance.html"

class RelatorioPagamentosView(TemplateView):
    template_name = "relatorios/pagamentos.html"

# =====================================
# IMPORTAÇÃO E EXPORTAÇÃO
# =====================================


# =====================================
# AJAX
# =====================================
class BuscarFornecedorAjaxView(View):
    def get(self, request):
        term = request.GET.get("q", "")
        resultados = list(Fornecedor.objects.filter(nome__icontains=term).values("id", "nome"))
        return JsonResponse(resultados, safe=False)

class ValidarNifView(View):
    def get(self, request):
        nif = request.GET.get("nif", "")
        valido = True  # lógica de validação
        return JsonResponse({"valido": valido})


class CalcularPrazoEntregaView(View):
    def get(self, request):
        dias = 5  # placeholder cálculo
        return JsonResponse({"prazo_dias": dias})

# =====================================
# COMUNICAÇÃO
# =====================================
class EnviarEmailView(View):
    def post(self, request, pk):
        # lógica de envio
        messages.success(request, "Email enviado.")
        return redirect("fornecedores:detail", pk=pk)

class EnviarWhatsAppView(View):
    def post(self, request, pk):
        # lógica de envio
        messages.success(request, "WhatsApp enviado.")
        return redirect("fornecedores:detail", pk=pk)

class ComunicacaoListView(ListView):
    model = Fornecedor
    template_name = "comunicacoes/lista.html"

# =====================================
# API REST
# =====================================
class BuscarProdutosFornecedorAPIView(APIView):
    def get(self, request):
        fornecedor_id = request.GET.get("fornecedor")
        produtos = []  # obter produtos do fornecedor
        serializer = ProdutoSerializer(produtos, many=True)
        return Response(serializer.data)

class CalcularFreteAPIView(APIView):
    def get(self, request):
        frete = 10.0  # placeholder
        return Response({"frete": frete})



##################################################
import csv
import json
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.views import View
from django.views.generic import ListView
from django.core.serializers.json import DjangoJSONEncoder

# Módulos para REST API (assumindo Django REST Framework)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# Modelos do seu sistema
from .models import Fornecedor, ContatoFornecedor, AvaliacaoFornecedor, Pedido, ItemPedido
# Assumindo a existência de um Serializer para Produto
# from apps.produtos.serializers import ProdutoSerializer 
# Assumindo a existência do modelo Produto
# from apps.produtos.models import Produto 


# =====================================
# IMPORTAÇÃO E EXPORTAÇÃO (EFICIÊNCIA DE DADOS)
# =====================================

class ImportarFornecedoresView(View):
    """
    Processa a importação de fornecedores via arquivo (CSV/Excel).
    A lógica real de parse e validação deve ser implementada aqui.
    """
    def post(self, request):
        if 'arquivo_fornecedores' not in request.FILES:
            messages.error(request, "Nenhum arquivo de importação foi selecionado.")
            return redirect("fornecedores:lista")
        
        arquivo = request.FILES['arquivo_fornecedores']
        
        # Validação básica de tipo de arquivo (Simplificado)
        if not arquivo.name.endswith(('.csv', '.xlsx')):
            messages.error(request, "Formato de arquivo inválido. Use CSV ou XLSX.")
            return redirect("fornecedores:lista")
        
        # Placeholder da Lógica de Importação Real
        # Deve usar uma biblioteca como 'pandas' ou 'openpyxl' para XLSX, ou 'csv' para CSV
        
        # Exemplo Simples para CSV:
        if arquivo.name.endswith('.csv'):
            try:
                # Lê o arquivo e ignora o cabeçalho
                reader = csv.DictReader(arquivo.read().decode('utf-8').splitlines())
                novos_fornecedores = 0
                for row in reader:
                    # Lógica para criar ou atualizar Fornecedor
                    # Fornecedor.objects.update_or_create(nif_bi=row['NIF'], defaults={'razao_social': row['RazaoSocial'], ...})
                    novos_fornecedores += 1 # Apenas para contagem
                
                if novos_fornecedores > 0:
                    messages.success(request, f"{novos_fornecedores} fornecedores importados/atualizados com sucesso.")
                else:
                    messages.warning(request, "O arquivo foi processado, mas nenhum novo fornecedor foi encontrado/criado.")
            except Exception as e:
                messages.error(request, f"Erro crítico na importação: {e}")
        
        # A URL de retorno deve ser a lista de fornecedores.
        return redirect("fornecedores:lista")

class ExportarFornecedoresView(View):
    """
    Exporta a lista completa de fornecedores para um arquivo CSV.
    """
    def get(self, request):
        # Nome do arquivo de exportação
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="fornecedores_export_{date.today()}.csv"'

        writer = csv.writer(response)
        
        # Cabeçalho do CSV
        writer.writerow([
            'Código', 'Razão Social', 'NIF/BI', 'Categoria', 'Telefone', 'Email Principal', 'Status Ativo', 'Nota Média'
        ])

        # Dados
        fornecedores = Fornecedor.objects.filter(empresa=self.request.user.empresa).select_related('condicao_pagamento_padrao')
        for f in fornecedores:
            writer.writerow([
                f.codigo_fornecedor,
                f.razao_social,
                f.nif_bi,
                f.get_categoria_display(),
                f.telefone_principal,
                f.email_principal,
                'Ativo' if f.ativo else 'Inativo',
                f.nota_avaliacao if f.nota_avaliacao is not None else 'N/A'
            ])

        return response


# =====================================
# AJAX E UTILITÁRIOS (INTERATIVIDADE)
# =====================================

class BuscarFornecedorAjaxView(View):
    """
    Retorna uma lista de fornecedores em JSON para uso em campos de autocomplete (Select2/TomSelect).
    """
    def get(self, request):
        term = request.GET.get("q", "")
        # Usando 'razao_social' e 'nome_fantasia' para uma busca mais abrangente
        resultados = Fornecedor.objects.filter(
            razao_social__icontains=term,
            empresa=self.request.user.empresa
        ).annotate(
            nome=F('razao_social') 
        ).values("id", "nome", "nif_bi")[:10] # Limitar a 10 resultados para performance
        
        # Formata o resultado para o padrão que o Select2 geralmente espera
        data = [{'id': item['id'], 'text': f"{item['nome']} (NIF: {item['nif_bi']})" } for item in resultados]
        
        return JsonResponse({'results': data}, safe=False)

class ValidarNifView(View):
    """
    Validação de formato e unicidade do NIF/BI (via AJAX).
    """
    def get(self, request):
        nif = request.GET.get("nif", "").strip()
        
        if not nif:
            return JsonResponse({"valido": False, "mensagem": "NIF/BI é obrigatório."}, status=400)
        
        valido = True
        mensagem = "NIF/BI válido."
        
        # 1. Validação de Formato (Simplificada)
        if len(nif) not in [10, 14]: # 10 digitos para NIF, 14 para BI (ex. 008693558LA042)
            valido = False
            mensagem = "Formato inválido. NIF (10 digitos) ou BI (14 caracteres esperado)."
        
        # 2. Validação de Unicidade (Crítica)
        if valido and Fornecedor.objects.filter(nif_bi=nif).exists():
            valido = False
            mensagem = f"NIF/BI {nif} já está registrado no sistema."
            
        return JsonResponse({"valido": valido, "mensagem": mensagem})


class CalcularPrazoEntregaView(View):
    """
    Calcula dinamicamente o prazo de entrega esperado (Data Prevista) com base na política do Fornecedor.
    """
    def get(self, request):
        fornecedor_id = request.GET.get("fornecedor_id")
        
        try:
            fornecedor = Fornecedor.objects.get(pk=fornecedor_id)
            dias_prazo = fornecedor.prazo_entrega_dias
            
            # Cálculo da data: hoje + prazo (desconsiderando feriados/fins de semana para simplificar)
            data_prevista = date.today() + timedelta(days=dias_prazo)
            
            return JsonResponse({
                "prazo_dias": dias_prazo,
                "data_prevista": data_prevista.strftime('%Y-%m-%d') # Formato ISO para JS
            })
        except Fornecedor.DoesNotExist:
            return JsonResponse({"prazo_dias": 7, "data_prevista": (date.today() + timedelta(days=7)).strftime('%Y-%m-%d'), "mensagem": "Fornecedor não encontrado. Usando prazo padrão."}, status=404)


# =====================================
# COMUNICAÇÃO (FLUXO DE TRABALHO)
# =====================================

class EnviarEmailView(View):
    """
    Envia email para o contato principal (ou comercial/financeiro) do fornecedor.
    """
    def post(self, request, pk):
        fornecedor = get_object_or_404(Fornecedor, pk=pk)
        
        # Obter dados do formulário POST (assunto, corpo, destinatário)
        assunto = request.POST.get('assunto', 'Comunicação Importante')
        corpo = request.POST.get('corpo', 'Prezado fornecedor, ...')
        
        destinatario = fornecedor.email_principal
        if not destinatario:
             messages.error(request, "Email principal do fornecedor não cadastrado.")
             return redirect("fornecedores:detail", pk=pk)
        
        # Placeholder da Lógica de Envio de Email Real (exige django.core.mail.send_mail)
        # from django.core.mail import send_mail
        # send_mail(assunto, corpo, 'seu_email@empresa.com', [destinatario], fail_silently=False)
        
        messages.success(request, f"Email '{assunto}' enviado com sucesso para {destinatario}.")
        return redirect("fornecedores:detail", pk=pk)

class EnviarWhatsAppView(View):
    """
    Simula o envio de mensagem via API do WhatsApp.
    O uso prático normalmente requer integração com Twilio ou outra API de mensagens.
    """
    def post(self, request, pk):
        fornecedor = get_object_or_404(Fornecedor, pk=pk)
        
        telefone_whatsapp = fornecedor.whatsapp
        if not telefone_whatsapp:
             messages.error(request, "Número de WhatsApp do fornecedor não cadastrado.")
             return redirect("fornecedores:detail", pk=pk)
        
        # Placeholder: Construção de link para API Web (pode ser substituído por chamada API)
        mensagem = request.POST.get('mensagem', 'Prezado fornecedor, favor verificar o pedido em anexo.')
        mensagem_encoded = mensagem.replace(' ', '%20')
        link_whatsapp = f"https://api.whatsapp.com/send?phone={telefone_whatsapp}&text={mensagem_encoded}"
        
        # Em produção, você faria uma requisição POST à API do WhatsApp/Twilio aqui.
        
        messages.success(request, f"Link de WhatsApp gerado para {fornecedor.nome_exibicao}. Clique para enviar.")
        
        # Redirecionar para o link do WhatsApp (mais prático em sistemas web)
        return redirect(link_whatsapp) 

class ComunicacaoListView(ListView):
    """
    Lista de histórico de comunicações (Emails, WhatsApps, etc.).
    A lógica desta View exigiria um modelo `HistoricoComunicacao`. Aqui, apenas retornamos a lista de fornecedores.
    """
    model = Fornecedor
    template_name = "comunicacoes/lista.html"
    context_object_name = "fornecedores"


# =====================================
# API REST (INTEGRAÇÃO COM OUTROS MÓDULOS/SISTEMAS)
# =====================================



class BuscarProdutosFornecedorAPIView(APIView):
    """
    API para buscar a lista de produtos fornecidos por um determinado fornecedor.
    Usado por módulos de Compras/Estoque.
    """
    def get(self, request):
        fornecedor_id = request.GET.get("fornecedor")
        
        if not fornecedor_id:
            return Response({"detail": "O parâmetro 'fornecedor' é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Lógica: Obter produtos que o fornecedor fornece (exigiria um modelo ProdutoFornecedor)
            # produtos = Produto.objects.filter(fornecedor__id=fornecedor_id)
            
            # SIMULAÇÃO
            if fornecedor_id == "1":
                produtos = [{"id": 101, "nome": "Paracetamol 500mg", "preco_base": 1.50}]
            elif fornecedor_id == "2":
                produtos = [{"id": 201, "nome": "Band-Aid", "preco_base": 0.50}]
            else:
                produtos = []
            
            # O ProdutoSerializer serializaria os objetos Produto em formato JSON
            # serializer = ProdutoSerializer(produtos, many=True)
            # return Response(serializer.data)
            
            return Response(produtos, status=status.HTTP_200_OK) # Retornando a simulação

        except Exception as e:
            return Response({"detail": f"Erro interno: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CalcularFreteAPIView(APIView):
    """
    API para calcular frete e custo de envio em tempo real, baseando-se no fornecedor e localização.
    """
    def get(self, request):
        fornecedor_id = request.GET.get("fornecedor")
        cep_destino = request.GET.get("cep_destino")
        valor_total = request.GET.get("valor_total", 0) # Para verificar se é elegível para frete grátis
        
        try:
            valor_total = Decimal(valor_total)
        except:
            return Response({"detail": "O parâmetro 'valor_total' deve ser um número."}, status=status.HTTP_400_BAD_REQUEST)

        # SIMULAÇÃO de Lógica Complexa de Frete
        frete = Decimal('10.00') # Custo base
        prazo_dias = 3
        
        if valor_total >= 500:
            frete = Decimal('0.00') # Frete grátis
            
        if frete > 0:
            frete += valor_total * Decimal('0.02') # 2% do valor como seguro/custo
        
        if cep_destino and cep_destino.startswith('01'): # Simula CEP de capital
             prazo_dias = 1
            
        return Response({
            "frete": frete.quantize(Decimal('0.01')),
            "prazo_dias": prazo_dias,
            "transportadora": "Transportadora XYZ"
        }, status=status.HTTP_200_OK)

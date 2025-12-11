# apps/estoque/views.py
from django.forms import ValidationError
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, View
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import timedelta
from django.db.models import F
from apps.core.views import BaseMPAView
from apps.estoque.api.serializers import MovimentacaoEstoqueSerializer
from apps.produtos.forms import ProdutoForm
from .models import (
    MovimentacaoEstoque, Inventario, LocalizacaoEstoque
)
from django.contrib.auth.mixins import AccessMixin
from .forms import (
    MovimentacaoEstoqueForm, InventarioForm, LocalizacaoEstoqueForm
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib import messages
from django.utils import timezone
from apps.estoque.models import (
    TipoMovimentacao, MovimentacaoEstoque, Inventario, ItemInventario,
    AlertaEstoque, LocalizacaoEstoque
)
from apps.produtos.models import Produto
from apps.estoque.forms import MovimentacaoEstoqueForm, InventarioForm, LocalizacaoEstoqueForm
from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework import status
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from .models import Inventario
from .forms import InventarioForm




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


# =============================
# DASHBOARD
# =============================


class EstoqueDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'estoque/estoque.html'

    def get_empresa(self):
        """ Método seguro para obter a empresa do utilizador logado. """
        user = self.request.user
        if hasattr(user, 'funcionario') and user.funcionario.empresa:
            return user.funcionario.empresa
        
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()

        if not empresa:
            messages.warning(self.request, "Utilizador não associado a nenhuma empresa.")
            context['movimentacoes_recentes'] = []
            context['alertas_ativos'] = []
            context['add_product_form'] = ProdutoForm() 
        
            return context


        context['movimentacoes_recentes'] = MovimentacaoEstoque.objects.filter(
            produto__empresa=empresa
        ).select_related('produto', 'usuario').order_by('-created_at')[:10]

        context['alertas_ativos'] = AlertaEstoque.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('-created_at')
        
        context['title'] = "Dashboard de Estoque" # Adicionado título para consistência
        return context


# =============================
# LISTAS
# =============================
class EstoqueView(BaseMPAView):
    template_name = 'estoque/estoque.html'
    module_name = 'estoque'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        hoje = timezone.now().date()
        proximos_30_dias = hoje + timedelta(days=30)
        
        # Produtos com estoque baixo (Esta query já estava correta)
        produtos_estoque_baixo = Produto.objects.filter(
            ativo=True,
            estoque_atual__lte=F('estoque_minimo')
        )
        
        # --- INÍCIO DA CORREÇÃO ---
        # Produtos vencendo: A query agora atravessa a relação para o modelo Lote.
        produtos_vencendo = Produto.objects.filter(
            ativo=True,
            # Use 'lotes__data_validade' para aceder ao campo no modelo Lote.
            lotes__data_validade__lte=proximos_30_dias, # Lotes que vencem nos próximos 30 dias.
            lotes__data_validade__gt=hoje              # Lotes que ainda não venceram.
        ).distinct() # Use .distinct() para garantir que cada produto apareça apenas uma vez.
        # --- FIM DA CORREÇÃO ---
        
        # Stats
        # A sua lógica original aqui está funcional, mas pode ser otimizada.
        # Mantendo a sua lógica original por enquanto:
        estoque_stats = {
            'total': sum(
                (p.estoque_atual or 0) * float(p.preco_venda or 0)
                for p in Produto.objects.filter(ativo=True)
            ),
            'estoque_baixo': produtos_estoque_baixo.count(),
            'vencendo': produtos_vencendo.count(), # A contagem agora reflete a query correta.
        }
        
        context.update({
            'estoque_stats': estoque_stats,
            'produtos_estoque_baixo': produtos_estoque_baixo,
            'produtos_vencendo': produtos_vencendo,
        })
        
        return context


from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect

from .models import MovimentacaoEstoque
from .forms import MovimentacaoEstoqueForm


# --- MIXIN DE PERMISSÃO (BOA PRÁTICA) ---
class MovimentacaoPermissionMixin(LoginRequiredMixin):
    """
    Mixin para garantir que o utilizador só acede a movimentações da sua empresa.
    Evita a repetição de código.
    """
    model = MovimentacaoEstoque

    def get_empresa(self):
        """ Método seguro para obter a empresa do utilizador logado. """
        user = self.request.user
        if hasattr(user, 'funcionario') and user.funcionario and user.funcionario.empresa:
            return user.funcionario.empresa
        return None

    def get_queryset(self):
        """ Filtra o queryset base para a empresa do utilizador. """
        empresa = self.get_empresa()
        if not empresa:
            return self.model.objects.none() # Retorna um queryset vazio se não houver empresa
        
        # --- CORREÇÃO PRINCIPAL APLICADA AQUI ---
        # Filtra através da relação com o produto.
        return self.model.objects.filter(produto__empresa=empresa).select_related('produto', 'usuario')

# --- VIEWS CRUD ---

class MovimentacaoListView(MovimentacaoPermissionMixin, ListView):
    template_name = 'estoque/movimentacao_lista.html'
    context_object_name = 'movimentacoes'
    paginate_by = 25

    def get_queryset(self):
        # Chama o queryset já filtrado pela empresa e adiciona a ordenação.
        queryset = super().get_queryset()

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Histórico de Movimentações de Estoque"
        return context

class MovimentacaoCreateView(LoginRequiredMixin, CreateView):
    model = MovimentacaoEstoque
    form_class = MovimentacaoEstoqueForm
    template_name = 'estoque/movimentacao_form.html'
    success_url = reverse_lazy('estoque:movimentacao_lista')

    def get_empresa(self):
        """ Método seguro para obter a empresa. """
        user = self.request.user
        if hasattr(user, 'funcionario') and user.funcionario and user.funcionario.empresa:
            return user.funcionario.empresa
        return None

    def get_form_kwargs(self):
        """ Passa a empresa para o formulário. """
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs
    
    def form_valid(self, form):
        # --- MELHORIA DE CÓDIGO APLICADA ---
        # Prepara o objeto sem o salvar ainda.
        movimentacao = form.save(commit=False)
        # Associa o utilizador logado.
        movimentacao.usuario = self.request.user
        # O campo 'empresa' não existe no modelo, não precisa ser definido aqui.
        # A associação é feita através do 'produto' selecionado no formulário.
        
        messages.success(self.request, "Movimentação criada com sucesso.")
        
        # Deixa a CreateView original tratar do save() e do redirecionamento.
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Registar Nova Movimentação"
        return context

class MovimentacaoDetailView(MovimentacaoPermissionMixin, DetailView):
    template_name = 'estoque/movimentacao_detail.html'
    context_object_name = 'movimentacao'
    # O queryset já é filtrado pela empresa graças ao MovimentacaoPermissionMixin

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Detalhes da Movimentação #{self.object.id}"
        return context


class MovimentacaoUpdateView(LoginRequiredMixin, UpdateView):
    model = MovimentacaoEstoque
    form_class = MovimentacaoEstoqueForm
    template_name = 'estoque/movimentacao_form.html'
    success_url = reverse_lazy('estoque:movimentacao_lista')

    def form_valid(self, form):
        movimentacao = form.save(commit=False)
        movimentacao.usuario = self.request.user  # mantém atualizado quem editou
        movimentacao.save()
        messages.success(self.request, "Movimentação atualizada com sucesso.")
        return redirect(self.success_url)

    def get_form_kwargs(self):
        """
        Passa a empresa para o formulário para filtrar o campo 'produto'.
        """
        kwargs = super().get_form_kwargs()
        if hasattr(self.request.user, 'funcionario'):
            kwargs['empresa'] = self.request.user.funcionario.empresa
        return kwargs

    def get_context_data(self, **kwargs):
        """ Adiciona o título à página. """
        context = super().get_context_data(**kwargs)
        context['title'] = "Editar Movimentação"
        return context

#######################################


class EstornarMovimentacaoView(LoginRequiredMixin, TemplateView):
    template_name = 'estoque/movimentacao_estornar.html'

    def post(self, request, pk):
        movimentacao = get_object_or_404(MovimentacaoEstoque, pk=pk, empresa=request.user.empresa)
        try:
            movimentacao.cancelar_movimentacao(motivo="Estornada pelo usuário")
            messages.success(request, "Movimentação estornada com sucesso.")
        except Exception as e:
            messages.error(request, f"Erro ao estornar movimentação: {e}")
        return redirect('estoque:lista')


# =============================
# TIPOS ESPECÍFICOS DE MOVIMENTAÇÃO
# =============================

# apps/estoque/views.py
# ... outras importações
from django.views import View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.produtos.models import Produto
from .models import MovimentacaoEstoque, TipoMovimentacao

class EntradaDiretaProdutoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            produto = get_object_or_404(Produto, pk=pk)
            quantidade = int(request.POST.get('quantidade', 0))

            if quantidade <= 0:
                messages.error(request, "A quantidade deve ser maior que zero.")
                return redirect('produtos:lista')

            with transaction.atomic():
                tipo_entrada = TipoMovimentacao.objects.get(codigo='ENTRADA')
                MovimentacaoEstoque.objects.create(
                    produto=produto,
                    quantidade=quantidade,
                    tipo_movimentacao=tipo_entrada,
                    usuario=request.user
                )
                messages.success(request, f"{quantidade} unidades de '{produto.nome_produto}' adicionadas.")

        except Exception as e:
            messages.error(request, f"Erro ao adicionar estoque: {e}")

        return redirect('produtos:lista')
    

class EntradaEstoqueView(MovimentacaoCreateView):
    def get_initial(self):
        return {'tipo_movimentacao': TipoMovimentacao.objects.get(codigo='ENTRADA')}


class SaidaEstoqueView(MovimentacaoCreateView):
    def get_initial(self):
        return {'tipo_movimentacao': TipoMovimentacao.objects.get(codigo='SAIDA')}


class AjusteEstoqueView(MovimentacaoCreateView):
    def get_initial(self):
        return {'tipo_movimentacao': TipoMovimentacao.objects.get(codigo='AJUSTE')}


class PerdaEstoqueView(MovimentacaoCreateView):
    def get_initial(self):
        return {'tipo_movimentacao': TipoMovimentacao.objects.get(codigo='PERDA')}


# =============================
# LOCALIZAÇÃO
# =============================
class LocalizacaoListView(LoginRequiredMixin, ListView):
    template_name = 'estoque/localizacao_lista.html'
    model = LocalizacaoEstoque
    context_object_name = 'localizacoes'

    def get_queryset(self):
        return LocalizacaoEstoque.objects.all()


class LocalizacaoCreateView(LoginRequiredMixin, CreateView):
    model = LocalizacaoEstoque
    form_class = LocalizacaoEstoqueForm
    template_name = 'estoque/localizacao_form.html'
    success_url = reverse_lazy('estoque:localizacao_lista')

    def form_valid(self, form):
        messages.success(self.request, "Localização criada com sucesso.")
        return super().form_valid(form)


class LocalizacaoUpdateView(LoginRequiredMixin, UpdateView):
    model = LocalizacaoEstoque
    form_class = LocalizacaoEstoqueForm
    template_name = 'estoque/localizacao_form.html'
    success_url = reverse_lazy('estoque:localizacao_lista')

    def form_valid(self, form):
        messages.success(self.request, "Localização atualizada com sucesso.")
        return super().form_valid(form)


# =============================
# INVENTÁRIOS
# =============================

# --- CRUD PARA INVENTÁRIO ---

class InventarioBaseView(LoginRequiredMixin):
    """ View base para garantir que as operações são feitas na empresa correta. """
    model = Inventario
    
    def get_queryset(self):
        empresa = self.request.user.funcionario.empresa
        return Inventario.objects.filter(empresa=empresa)

class InventarioListView(InventarioBaseView, ListView):
    template_name = 'estoque/inventario_list.html'
    context_object_name = 'inventarios'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Inventários de Estoque"
        return context



class InventarioCreateView(LoginRequiredMixin, CreateView):
    model = Inventario
    form_class = InventarioForm
    template_name = 'estoque/inventario_form.html'
    
    def get_success_url(self):
        """
        Redireciona para a página de detalhes do inventário recém-criado.
        Este método agora irá funcionar porque self.object será definido.
        """
        return reverse_lazy('estoque:inventario_detail', kwargs={'pk': self.object.pk})

    def get_empresa(self):
        """ Método seguro para obter a empresa do utilizador logado. """
        user = self.request.user
        if hasattr(user, 'funcionario') and user.funcionario and user.funcionario.empresa:
            return user.funcionario.empresa
        return None

    def dispatch(self, request, *args, **kwargs):
        """ Garante que o utilizador tem uma empresa antes de prosseguir. """
        if not self.get_empresa():
            messages.error(request, "O seu utilizador não está associado a nenhuma empresa.")
            return redirect('estoque:inventario_lista')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """ Passa a empresa para o formulário. """
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        """
        Define os campos automáticos e deixa a CreateView tratar do resto.
        """
        # --- A CORREÇÃO ESTÁ AQUI ---
        
        # 1. Define os campos automáticos na instância do formulário, antes de guardar.
        form.instance.empresa = self.get_empresa()
        form.instance.responsavel_planejamento = self.request.user
        
        # 2. Adiciona a mensagem de sucesso ANTES de chamar o super().
        messages.success(self.request, f"Inventário '{form.instance.titulo}' planeado com sucesso. Agora pode iniciá-lo.")
        
        # 3. Chama o form_valid original da CreateView. Ele irá:
        #    - Salvar o objeto (e definir self.object para nós)
        #    - Chamar form.save_m2m() automaticamente
        #    - Retornar o HttpResponseRedirect para a get_success_url
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Planear Novo Inventário"
        return context


class InventarioDetailView(InventarioBaseView, DetailView):
    template_name = 'estoque/inventario_detail.html'
    context_object_name = 'inventario'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inventario = self.get_object()
        context['title'] = f"Detalhes do Inventário: {inventario.numero_inventario}"
        context['itens_inventario'] = ItemInventario.objects.filter(inventario=inventario)
        return context

class IniciarInventarioView(LoginRequiredMixin, View):
    def post(self, request, pk):
        inventario = get_object_or_404(Inventario, pk=pk, empresa=request.user.funcionario.empresa)
        try:
            inventario.iniciar_inventario()
            messages.success(request, f"Inventário '{inventario.numero_inventario}' iniciado com sucesso! {inventario.total_produtos_planejados} itens foram gerados para contagem.")
        except ValidationError as e:
            messages.error(request, e.message)
        return redirect('estoque:inventario_detail', pk=pk)

# Exemplo para FinalizarInventarioView
from django.db import transaction

class FinalizarInventarioView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    def post(self, request, pk):
        inventario = get_object_or_404(
            Inventario.objects.select_for_update(), 
            pk=pk, empresa=request.user.funcionario.empresa
        )
        try:
            with transaction.atomic():
                inventario.concluir_inventario()
            messages.success(
                request,
                f"Inventário '{inventario.numero_inventario}' concluído com sucesso! Ajustes gerados."
            )
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
        return redirect('estoque:inventario_detail', pk=pk)



# ============================
# DASHBOARD E LISTAS
# ============================

class EstoqueListView(ListView):
    model = MovimentacaoEstoque
    template_name = "estoque/lista.html"
    context_object_name = "movimentacoes"
    paginate_by = 20


# ============================
# TRANSFERÊNCIAS
# ============================
class TransferenciaListView(ListView):
    model = MovimentacaoEstoque
    template_name = "estoque/transferencias_lista.html"
    context_object_name = "transferencias"

class TransferenciaCreateView(CreateView):
    model = MovimentacaoEstoque
    form_class = MovimentacaoEstoqueForm
    template_name = "estoque/transferencia_form.html"
    success_url = reverse_lazy("estoque:transferencia_lista")

class TransferenciaDetailView(DetailView):
    model = MovimentacaoEstoque
    template_name = "estoque/transferencia_detail.html"
    context_object_name = "transferencia"

class AprovarTransferenciaView(View):
    def post(self, request, pk):
        transferencia = get_object_or_404(MovimentacaoEstoque, pk=pk)
        transferencia.status = "aprovada"
        transferencia.save()
        return redirect("estoque:transferencia_lista")

class EnviarTransferenciaView(View):
    def post(self, request, pk):
        transferencia = get_object_or_404(MovimentacaoEstoque, pk=pk)
        transferencia.status = "enviada"
        transferencia.save()
        return redirect("estoque:transferencia_lista")

class ReceberTransferenciaView(View):
    def post(self, request, pk):
        transferencia = get_object_or_404(MovimentacaoEstoque, pk=pk)
        transferencia.status = "recebida"
        transferencia.save()
        return redirect("estoque:transferencia_lista")

class CancelarTransferenciaView(View):
    def post(self, request, pk):
        transferencia = get_object_or_404(MovimentacaoEstoque, pk=pk)
        transferencia.status = "cancelada"
        transferencia.save()
        return redirect("estoque:transferencia_lista")

# ============================
# INVENTÁRIOS
# ============================



class GerarAjustesInventarioView(View):
    def post(self, request, pk):
        inventario = get_object_or_404(Inventario, pk=pk)
        # lógica para gerar ajustes
        return redirect("estoque:inventario_detail", pk=pk)


# ============================
# API REST EXEMPLO
# ============================

class VencimentosView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/vencimentos.html"


# =====================================
# VENCIMENTOS
# =====================================
class ProximosVencimentosView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/proximos_vencimentos.html"

class VencidosView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/vencidos.html"

class DescarteView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/descarte.html"

# =====================================
# ALERTAS E REPOSIÇÃO
# =====================================
class AlertasEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/alertas.html"

class EstoqueMinimoView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/estoque_minimo.html"

class SugestaoCompraView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/sugestao_compra.html"

class RupturaEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/ruptura.html"

# =====================================
# LOCALIZAÇÃO E ENDEREÇAMENTO
# =====================================


class EnderecamentoView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/enderecamento.html"

# =====================================
# RELATÓRIOS
# =====================================
class EstoqueRelatoriosView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/relatorios.html"

class RelatorioPosicaoEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/relatorio_posicao.html"

class RelatorioMovimentacaoView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/relatorio_movimentacao.html"

class RelatorioABCView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/relatorio_abc.html"

class RelatorioGiroView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/relatorio_giro.html"

# =====================================
# CÓDIGO DE BARRAS E ETIQUETAS
# =====================================
class CodigoBarrasView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/codigo_barras.html"

class EtiquetasView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/etiquetas.html"

class ImprimirEtiquetasView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/imprimir_etiquetas.html"

# =====================================
# LEITURA POR SCANNER
# =====================================
class ScannerView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/scanner.html"

class ConferenciaView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/conferencia.html"

class ColetaView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/coleta.html"

# =====================================
# IMPORTAÇÃO E EXPORTAÇÃO
# =====================================
class ImportarEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/importar.html"

class ExportarEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/exportar.html"

# =====================================
# AJAX E UTILITÁRIOS
# =====================================
class ConsultarEstoqueAjaxView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        # lógica de consulta
        return Response({"status": "ok"})

class ReservarEstoqueView(LoginRequiredMixin, APIView):
    def post(self, request, *args, **kwargs):
        # lógica de reserva
        return Response({"status": "ok"})

class LiberarReservaView(LoginRequiredMixin, APIView):
    def post(self, request, *args, **kwargs):
        # lógica de liberação
        return Response({"status": "ok"})

class SugerirLocalizacaoView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        # lógica de sugestão
        return Response({"status": "ok"})

# =====================================
# CONFIGURAÇÕES
# =====================================
class ConfiguracoesEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/configuracoes.html"

class ParametrosEstoqueView(LoginRequiredMixin, TemplateView):
    template_name = "estoque/parametros.html"

# =====================================
# API Personalizada
# =====================================
class SaldoAtualAPIView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        return Response({"saldo": 0})

class HistoricoMovimentacaoAPIView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        return Response({"historico": []})

class ValidarLoteAPIView(LoginRequiredMixin, APIView):
    def post(self, request, *args, **kwargs):
        return Response({"valido": True})



from django.views.generic import CreateView
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

class AdicionarEstoqueView(LoginRequiredMixin, CreateView):
    model = MovimentacaoEstoque
    fields = ["quantidade", "motivo"]
    template_name = "estoque/adicionar_estoque.html"

    def form_valid(self, form):
        produto = get_object_or_404(Produto, pk=self.kwargs["produto_id"])
        movimento = form.save(commit=False)
        movimento.produto = produto
        movimento.tipo = "entrada"
        movimento.save()
        produto.estoque_atual += movimento.quantidade
        produto.save(update_fields=["estoque_atual"])
        messages.success(self.request, "✅ Estoque atualizado com sucesso!")
        return redirect("produtos:listar")



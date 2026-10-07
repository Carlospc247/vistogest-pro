from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView
from .models import Compra
from django.contrib.auth.mixins import AccessMixin
from django.urls import reverse_lazy



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
                return redirect(reverse_lazy('core_tenants:dashboard'))

        return super().dispatch(request, *args, **kwargs)


# Lista todas as compras com filtros simples
class CompraListView(ListView):
    model = Compra
    template_name = "compras/compra_list.html"  # Crie esta pasta/template
    context_object_name = "compras"
    paginate_by = 25
    ordering = ['-data']

    def get_queryset(self):
        queryset = super().get_queryset()
        fornecedor = self.request.GET.get('fornecedor')
        if fornecedor:
            queryset = queryset.filter(fornecedor__nome__icontains=fornecedor)
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        if data_inicio:
            queryset = queryset.filter(data__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data__date__lte=data_fim)
        return queryset

# Detalhes de uma compra específica
class CompraDetailView(DetailView):
    model = Compra
    template_name = "compras/compra_detail.html"  # Crie esta pasta/template
    context_object_name = "compra"


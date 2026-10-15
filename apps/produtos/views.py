# apps/produtos/views.py
import io
from pyexpat.errors import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
    TemplateView, FormView, View
)
from datetime import date, timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.db.models import Q
from datetime import date, datetime, timedelta
import json
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from openpyxl import Workbook
import pandas as pd
from apps.analytics import models
from apps.core_tenants.views import BaseMPAView
from apps.servicos.models import Servico
from .models import (
    Categoria, Fabricante,
    Produto, Lote, HistoricoPreco
)
from django.db.models import Q
from .forms import ImportarProdutosForm, LoteForm, ProdutoForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from .models import Categoria
from .forms import CategoriaForm
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from .models import Produto
from apps.empresas.models import Empresa
from django.db import models
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.produtos.models import Produto
from django.contrib.auth.mixins import AccessMixin
import logging
import pandas as pd
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.fornecedores.models import Fornecedor
import openpyxl
from openpyxl import Workbook
import uuid
import unicodedata
from django.db import transaction
import csv
from apps.fiscal.models import TaxaIVAAGT

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Fabricante
from .forms import FabricanteForm
import csv
import io
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

import pandas as pd
import requests
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.views import View
from django.views.generic import FormView
from django_tenants.utils import get_public_schema_name
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation













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



# =============================================================================
# MIXIN: garante que a view corre dentro de um tenant (nunca no schema public)
# =============================================================================
class TenantRequeridoMixin:
    """
    Substitui o antigo get_empresa(). O tenant vem do middleware do django_tenants.
    No schema public (ou sem tenant) as tabelas de produtos nem existem, por isso
    a view é bloqueada.
    """
    tenant = None

    def dispatch(self, request, *args, **kwargs):
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return HttpResponseBadRequest(
                "Tenant não encontrado: aceda através do domínio da empresa."
            )
        self.tenant = tenant
        return super().dispatch(request, *args, **kwargs)

    @property
    def nome_tenant(self):
        return (
            getattr(self.tenant, 'nome', None)
            or getattr(self.tenant, 'name', None)
            or self.tenant.schema_name
        )


@login_required
def dashboard_view(request):
    """View do dashboard com notificações de estoque e validade"""
    hoje = date.today()
    data_limite = hoje + timedelta(days=30)
    
    # Lotes vencendo
    lotes_vencendo = Lote.objects.filter(
        validade__gte=hoje,
        validade__lte=data_limite
    ).select_related('produto').order_by('validade')
    
    # Produtos com estoque baixo
    produtos_ativos = Produto.objects.filter(ativo=True)
    produtos_estoque_baixo = [p for p in produtos_ativos if p.estoque_baixo]
    
    # Construir notificações
    lista_notificacoes = []
    
    for lote in lotes_vencendo:
        lista_notificacoes.append({
            'mensagem': f"Lote {lote.numero_lote} de {lote.produto.nome_produto} vence em {lote.validade.strftime('%d/%m/%Y')}",
            'detalhe': f"{lote.quantidade} unidades restantes",
            'css_class': 'bg-yellow-400'
        })

    for produto in produtos_estoque_baixo:
        lista_notificacoes.append({
            'mensagem': f"Estoque baixo: {produto.nome_produto}",
            'detalhe': f"Apenas {produto.estoque_atual} unidades",
            'css_class': 'bg-red-500'
        })
    
    context = {
        'total_notificacoes': len(lista_notificacoes),
        'lista_notificacoes': lista_notificacoes,
    }

    return render(request, 'core/dashboard.html', context)


from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from .models import Produto
import json




import math
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods



@login_required
@require_http_methods(["GET"])
def buscar_produtos_api(request):
    try:
        busca = request.GET.get('search', '').strip()
        categoria_id = request.GET.get('categoria', '').strip()
        status = request.GET.get('status', '').strip()
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 50))
        
        # Tenant/empresa atual definido pelo domínio da requisição
        empresa_atual = getattr(request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return JsonResponse({
                'success': False,
                'message': 'Empresa não encontrada'
            }, status=400)

        queryset = Produto.objects.filter().select_related('categoria', 'fornecedor', 'fabricante')

        if status == 'ativo':
            queryset = queryset.filter(ativo=True)
        elif status == 'inativo':
            queryset = queryset.filter(ativo=False)
        elif status == 'estoque_baixo':
            queryset = queryset.filter(estoque_atual__lte=F('estoque_minimo'))


        if categoria_id and categoria_id != 'todos':
            queryset = queryset.filter(categoria_id=categoria_id)

        if busca:
            queryset = queryset.filter(
                Q(codigo_barras__icontains=busca) |
                Q(codigo_interno__icontains=busca) |
                Q(nome_produto__icontains=busca)
            )

        total_produtos = queryset.count()  # total antes de fatiar
        start = (page - 1) * per_page
        end = start + per_page
        produtos_page = queryset[start:end]

        produtos_data = []
        for produto in produtos_page:  # <<<<<<<<<< usar produtos_page aqui
            produtos_data.append({
                'id': produto.id,
                'codigo_interno': produto.codigo_interno,
                'codigo_barras': produto.codigo_barras,
                'nome_produto': produto.nome_produto,
                'categoria': produto.categoria.nome if produto.categoria else '',
                'categoria_id': produto.categoria.id if produto.categoria else None,
                'fornecedor': str(produto.fornecedor) if produto.fornecedor else '',
                'fabricante': str(produto.fabricante) if produto.fabricante else '',
                'estoque_atual': produto.estoque_atual,
                'estoque_minimo': produto.estoque_minimo,
                'desconto_percentual': float(produto.desconto_percentual or 0),
                'preco_custo': float(produto.preco_custo or 0),
                'preco_venda': float(produto.preco_venda or 0),
                'margem_lucro': float(produto.margem_lucro or 0),
                'foto_url': produto.foto.url if produto.foto else None,
                'valor_estoque': float(produto.valor_estoque or 0),
                'estoque_baixo': produto.estoque_atual <= produto.estoque_minimo,
                'disponivel': produto.estoque_atual > 0,
                'iva_percentual': getattr(produto, 'iva_percentual', 0)
            })

        return JsonResponse({
            'success': True,
            'produtos': produtos_data,
            'total_encontrados': total_produtos,
            'page': page,
            'per_page': per_page,
            'total_paginas': math.ceil(total_produtos / per_page)
        })   

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro interno: {str(e)}'
        }, status=500)
       


class ProdutosView(LoginRequiredMixin, ListView):
    template_name = 'produtos/produto_list.html'
    model = Produto
    context_object_name = 'produtos'
    paginate_by = 200

    def get_queryset(self):
        queryset = Produto.objects.all().select_related('categoria')

        search = self.request.GET.get('search', '')
        categoria_filter = self.request.GET.get('categoria', '')
        status_filter = self.request.GET.get('status', '')

        if search:
            queryset = queryset.filter(
                Q(nome_produto__icontains=search) |
                Q(codigo_barras__icontains=search)
            )

        if categoria_filter:
            queryset = queryset.filter(
                categoria_id=categoria_filter
            )

        if status_filter == 'ativo':
            queryset = queryset.filter(ativo=True)
        elif status_filter == 'inativo':
            queryset = queryset.filter(ativo=False)
        elif status_filter == 'estoque_baixo':
            queryset = queryset.filter(
                estoque_atual__lte=F('estoque_minimo')
            )

        return queryset.order_by('nome_produto')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        todas_categorias = Categoria.objects.all().order_by('nome')
        servicos = Servico.objects.all()
        todos_produtos = Produto.objects.all()

        context['produtos_stats'] = {
            'total': todos_produtos.count(),
            'ativos': todos_produtos.filter(ativo=True).count(),
            'categorias': todas_categorias.count(),
            'servicos': servicos.count(),
        }

        context['categorias'] = todas_categorias.filter(ativa=True)

        return context

class CriarProdutoView(LoginRequiredMixin, CreateView):
    model = Produto
    form_class = ProdutoForm
    template_name = 'produtos/produto_form.html'
    success_url = reverse_lazy('produtos:produto_list')
    acao_requerida = 'editar_produtos'

    def get_tenant(self):
        """Obtém o tenant atual da requisição."""
        tenant = getattr(self.request, 'tenant', None)

        if not tenant or getattr(
            tenant,
            'schema_name',
            'public'
        ) == 'public':
            return None

        return tenant

    def dispatch(self, request, *args, **kwargs):
        """Garante que a requisição está dentro de um tenant."""
        if not self.get_tenant():
            messages.error(
                request,
                "Não foi possível identificar a empresa desta sessão."
            )
            return redirect('core_tenants:dashboard')

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        produto = form.save()

        messages.success(
            self.request,
            f"Produto '{produto.nome_produto}' criado com sucesso!"
        )

        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Adicionar Novo Produto"
        return context
        


class EditarProdutoView(LoginRequiredMixin, UpdateView):
    model = Produto
    form_class = ProdutoForm
    template_name = 'produtos/produto_form.html'
    success_url = reverse_lazy('produtos:produto_list')
    pk_url_kwarg = 'produto_id'
    acao_requerida = 'editar_produtos'

    def get_queryset(self):
        """
        O tenant/schema atual já garante o isolamento dos produtos.
        """
        return Produto.objects.all()

    def form_valid(self, form):
        """Adiciona uma mensagem de sucesso antes de redirecionar."""
        messages.success(
            self.request,
            f"Produto '{form.instance.nome_produto}' atualizado com sucesso!"
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Editar Produto: {self.object.nome_produto}"
        return context
    

class DeletarProdutoView(LoginRequiredMixin, View):
    acao_requerida = 'editar_produtos'
    def post(self, request, produto_id):
        try:
            empresa = self.get_empresa(request)
            from apps.produtos.models import Produto
            produto = Produto.objects.get(id=produto_id, empresa=empresa)
            
            nome = produto.nome_produto
            produto.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Produto "{nome}" removido com sucesso'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    def get_empresa(self, request):
        if hasattr(request.user, 'usuario') and request.user.usuario.empresa:
            return request.user.usuario.empresa
        elif hasattr(request.user, 'profile') and request.user.profile.empresa:
            return request.user.profile.empresa
        else:
            from apps.empresas.models import Empresa
            return Empresa.objects.first()


class DeletarTodosProdutosLotesView(LoginRequiredMixin, View):
    """
    Remove TODOS os produtos e TODOS os lotes.
    Uso: Ação drástica de limpeza.
    """
    def post(self, request):
        try:
            empresa = self._get_empresa(request)
            from apps.produtos.models import Produto
            
            # Como on_delete=CASCADE no Lote, apagar produtos apaga lotes
            count, _ = Produto.objects.filter(empresa=empresa).delete()
            
            return JsonResponse({
                'success': True,
                'message': f'{count} registos (produtos e dependências) removidos permanentemente.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    def _get_empresa(self, request):
        # Helper simples
        if hasattr(request.user, 'usuario') and request.user.usuario.empresa:
            return request.user.usuario.empresa
        return None


class DeletarTodosProdutosManterLotesView(LoginRequiredMixin, View):
    """
    Remove (Desativa) TODOS os produtos, mantendo os lotes no banco.
    Nota: Como Lote tem FK(Produto, on_delete=CASCADE), não podemos apagar o produto fisicamente
    sem apagar o lote. Portanto, esta view faz um SOFT DELETE (ativo=False).
    """
    def post(self, request):
        try:
            empresa = self._get_empresa(request)
            from apps.produtos.models import Produto
            
            # Soft Delete
            updated = Produto.objects.filter(ativo=True).update(ativo=False)
            
            return JsonResponse({
                'success': True,
                'message': f'{updated} produtos foram desativados. Os lotes permanecem inalterados.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    def _get_empresa(self, request):
        if hasattr(request.user, 'usuario') and request.user.usuario.empresa:
            return request.user.usuario.empresa
        return None


class ToggleProdutoView(LoginRequiredMixin, View):
    acao_requerida = 'editar_produtos'
    def post(self, request, produto_id):
        try:
            empresa = self.get_empresa(request)
            from apps.produtos.models import Produto
            produto = Produto.objects.get(id=produto_id, empresa=empresa)
            
            produto.ativo = not produto.ativo
            produto.save()
            
            return JsonResponse({
                'success': True,
                'ativo': produto.ativo,
                'message': f'Produto {"ativado" if produto.ativo else "desativado"} com sucesso'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    def get_empresa(self, request):
        if hasattr(request.user, 'usuario') and request.user.usuario.empresa:
            return request.user.usuario.empresa
        elif hasattr(request.user, 'profile') and request.user.profile.empresa:
            return request.user.profile.empresa
        else:
            from apps.empresas.models import Empresa
            return Empresa.objects.first()


class CategoriaBaseView(LoginRequiredMixin):
    """
    View base para operações sobre categorias.
    O isolamento é garantido pelo schema do tenant atual.
    """
    model = Categoria

    def get_tenant(self):
        """Obtém o tenant atual da requisição."""
        tenant = getattr(self.request, 'tenant', None)

        if not tenant or getattr(
            tenant,
            'schema_name',
            'public'
        ) == 'public':
            return None

        return tenant

    def dispatch(self, request, *args, **kwargs):
        """Garante que a requisição está dentro de um tenant válido."""
        if not self.get_tenant():
            messages.error(
                request,
                "Não foi possível identificar a empresa desta sessão."
            )
            return redirect('core_tenants:dashboard')

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """
        O schema do tenant já garante o isolamento das categorias.
        """
        return Categoria.objects.all()
    

class CategoriaListView(CategoriaBaseView, ListView):
    template_name = 'produtos/categoria_list.html'
    context_object_name = 'categorias'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Categorias de Produtos"
        return context



class CategoriaCreateView(CategoriaBaseView, CreateView):
    model = Categoria
    # --- PONTO CRÍTICO DA CORREÇÃO ---
    form_class = CategoriaForm
    
    template_name = 'produtos/categoria_form.html'
    success_url = reverse_lazy('produtos:categoria_list')

    def get_form_kwargs(self):
        # Este método é essencial para passar a 'empresa' para o formulário
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        # A lógica aqui está correta, associa a empresa antes de salvar
        form.instance.empresa = self.get_empresa()
        messages.success(self.request, "Categoria criada com sucesso!")
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Adicionar Nova Categoria"
        return context       



class CategoriaUpdateView(CategoriaBaseView, UpdateView):
    form_class = CategoriaForm
    template_name = 'produtos/categoria_form.html'
    success_url = reverse_lazy('produtos:categoria_list')

    def get_form_kwargs(self):
        """ Passa a empresa para o formulário. """
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Categoria atualizada com sucesso!")
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Editar Categoria: {self.object.nome}"
        return context

class CategoriaDeleteView(CategoriaBaseView, DeleteView):
    template_name = 'produtos/categoria_confirm_delete.html'
    success_url = reverse_lazy('produtos:categoria_list')
    
    def post(self, request, *args, **kwargs):
        # O método post é o correto para adicionar a mensagem antes de apagar
        self.object = self.get_object()
        messages.success(self.request, f"Categoria '{self.object.nome}' eliminada com sucesso!")
        return self.delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Eliminar Categoria: {self.object.nome}"
        return context   



#######################################



# ===============================
# LOTE VIEWS
# ===============================

class LoteListView(LoginRequiredMixin, ListView):
    model = Lote
    template_name = "produtos/lote_list.html"
    context_object_name = "lotes"
    paginate_by = 200  # Define a paginação aqui

    def get_queryset(self):
        """
        Este método agora constrói a consulta ao banco de dados de forma dinâmica,
        aplicando os filtros e a ordenação recebidos do formulário.
        """
        # Começa com todos os lotes (respeitando permissões, se aplicável)
        queryset = Lote.objects.select_related('produto').all()

        # Obtém os parâmetros do URL (ex: ?search=paracetamol&status=vencendo)
        search_query = self.request.GET.get('search', '').strip()
        status_filter = self.request.GET.get('status', '')
        sort_by = self.request.GET.get('sort', '-data_validade') # Padrão: validade mais longe

        # 1. Aplicar filtro de pesquisa
        if search_query:
            queryset = queryset.filter(
                Q(produto__nome_produto__icontains=search_query) |
                Q(numero_lote__icontains=search_query)
            )

        # 2. Aplicar filtro de status de validade
        hoje = date.today()
        if status_filter == 'vencido':
            queryset = queryset.filter(data_validade__lt=hoje)
        elif status_filter == 'vencendo':
            data_limite = hoje + timedelta(days=30)
            queryset = queryset.filter(data_validade__gte=hoje, data_validade__lte=data_limite)

        # 3. Aplicar ordenação
        # Validar as opções de ordenação para segurança
        valid_sort_options = ['data_validade', '-data_validade', 'quantidade_atual', '-quantidade_atual']
        if sort_by in valid_sort_options:
            queryset = queryset.order_by(sort_by)

        return queryset

    def get_context_data(self, **kwargs):
        """ Adiciona os valores dos filtros ao contexto para manter o estado no template. """
        context = super().get_context_data(**kwargs)
        # Passa os valores atuais dos filtros de volta para o template
        context['search_query'] = self.request.GET.get('search', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_sort'] = self.request.GET.get('sort', '-data_validade')
        context['add_product_form'] = ProdutoForm() 
        
        
        return context


class LoteDetailView(LoginRequiredMixin, DetailView):
    model = Lote
    template_name = "produtos/lote_detail.html"






from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .models import Lote
from .forms import LoteForm, ProdutoForm # Garanta que os forms estão importados

# --- BASE VIEW PARA LOTES (BOA PRÁTICA) ---

class LoteBaseView(LoginRequiredMixin):
    """ View base para Lotes, garante o modelo e o filtro por empresa. """
    model = Lote

    def get_queryset(self):
        # Garante que qualquer view que herde disto só aceda a lotes da empresa do utilizador
        """
        Retorna apenas os lotes existentes no tenant atual.
        """
        return Lote.objects.filter()






# --- CRUD COMPLETO PARA LOTES ---

class LoteListView(LoteBaseView, ListView):
    template_name = "produtos/lote_list.html"
    context_object_name = "lotes"
    paginate_by = 20

    def get_queryset(self):
        # Começa com o queryset já filtrado por empresa da LoteBaseView
        queryset = super().get_queryset().select_related('produto')
        
        search_query = self.request.GET.get('search', '').strip()
        status_filter = self.request.GET.get('status', '')
        sort_by = self.request.GET.get('sort', '-data_validade')

        if search_query:
            # CORREÇÃO: Usar 'nome_comercial'
            queryset = queryset.filter(
                Q(produto__nome_comercial__icontains=search_query) |
                Q(numero_lote__icontains=search_query)
            )

        hoje = date.today()
        if status_filter == 'vencido':
            queryset = queryset.filter(data_validade__lt=hoje)
        elif status_filter == 'vencendo':
            data_limite = hoje + timedelta(days=30)
            queryset = queryset.filter(data_validade__gte=hoje, data_validade__lte=data_limite)

        valid_sort_options = ['data_validade', '-data_validade', 'quantidade_atual', '-quantidade_atual']
        if sort_by in valid_sort_options:
            queryset = queryset.order_by(sort_by)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_sort'] = self.request.GET.get('sort', '-data_validade')
        context['add_product_form'] = ProdutoForm() 
        context['title'] = "Gestão de Lotes de Produtos"
        return context

class LoteDetailView(LoteBaseView, DetailView):
    template_name = "produtos/lote_detail.html"
    context_object_name = "lote"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Detalhes do Lote: {self.object.numero_lote}"
        return context

class LoteCreateView(LoteBaseView, CreateView):
    form_class = LoteForm
    template_name = "produtos/lote_form.html"
    success_url = reverse_lazy("produtos:lote_list")

    def form_valid(self, form):
        lote = form.save(commit=False)
        lote.quantidade_atual = form.cleaned_data['quantidade_inicial']
        lote.save()
        messages.success(self.request, f"Lote {lote.numero_lote} adicionado com sucesso!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Adicionar Novo Lote"
        return context

class LoteUpdateView(LoteBaseView, UpdateView):
    form_class = LoteForm
    template_name = "produtos/lote_form.html"
    
    def get_success_url(self):
        return reverse_lazy('produtos:lote_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Lote atualizado com sucesso!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Editar Lote: {self.object.numero_lote}"
        return context

class LoteDeleteView(LoteBaseView, DeleteView):
    template_name = "produtos/lote_confirm_delete.html"
    success_url = reverse_lazy("produtos:lote_list")
    
    def form_valid(self, form):
        messages.success(self.request, f"Lote '{self.object.numero_lote}' eliminado com sucesso!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Eliminar Lote"
        return context
    
# ===============================
# AJAX VIEWS
# ===============================

class BuscarProdutoAjaxView(LoginRequiredMixin, View):
    def get(self, request):
        termo = request.GET.get('q', '').strip()
        
        if len(termo) < 2:
            return JsonResponse({'produtos': []})
        
        produtos = Produto.objects.filter(
            Q(nome_produto__icontains=termo) |
            Q(codigo_barras__icontains=termo) |
            Q(codigo_interno__icontains=termo),
            ativo=True
        ).select_related('categoria', 'fabricante')[:10]
        
        produtos_data = []
        for produto in produtos:
            produtos_data.append({
                'id': produto.id,
                'nome_produto': produto.nome_produto,
                'codigo_barras': produto.codigo_barras,
                'preco_venda': float(produto.preco_venda),
                'fabricante': produto.fabricante.nome if produto.fabricante else '',
                'categoria': produto.categoria.nome if produto.categoria else '',
                'estoque_atual': produto.estoque_atual,
            })
        
        return JsonResponse({'produtos': produtos_data})


class VerificarCodigoView(LoginRequiredMixin, View):
    def get(self, request):
        codigo = request.GET.get('codigo', '').strip()
        existe = Produto.objects.filter(codigo_barras=codigo).exists()
        return JsonResponse({'existe': existe})

# ===============================
# RELATÓRIOS E CONSULTAS
# ===============================

class LotesVencimentoView(LoginRequiredMixin, ListView):
    model = Lote
    template_name = "produtos/lotes_vencimento.html"
    context_object_name = "lotes"

    def get_queryset(self):
        hoje = timezone.now().date()
        dias = int(self.request.GET.get('dias', 30))
        data_limite = hoje + timedelta(days=dias)
        
        return Lote.objects.filter(
            validade__gte=hoje,
            validade__lte=data_limite,
            quantidade__gt=0
        ).select_related('produto').order_by('validade')

class ProdutosEstoqueBaixoView(LoginRequiredMixin, ListView):
    model = Produto
    template_name = "produtos/estoque_baixo.html"
    context_object_name = "produtos"

    def get_queryset(self):
        produtos = Produto.objects.filter(ativo=True, estoque_minimo__gt=0)
        produtos_baixo = []
        
        for produto in produtos:
            if produto.estoque_baixo:
                produtos_baixo.append(produto)
        
        return produtos_baixo


# ===============================
# AÇÕES ESPECIAIS
# ===============================

class AtivarProdutoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        produto.ativo = True
        produto.save()
        return redirect("produtos:produto_detail", pk=pk)

class DesativarProdutoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        produto.ativo = False
        produto.save()
        return redirect("produtos:produto_detail", pk=pk)


@login_required
@require_http_methods(["GET"])
def listar_categorias_api(request):
    """
    API para listar categorias
    """
    try:
        empresa_atual = getattr(request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return JsonResponse({
                'success': False,
                'message': 'Empresa não encontrada'
            }, status=400)
        
        from .models import Categoria
        categorias = Categoria.objects.filter(ativo=True)
        
        categorias_data = []
        for categoria in categorias:
            categorias_data.append({
                'id': categoria.id,
                'nome': categoria.nome,
                'descricao': getattr(categoria, 'descricao', ''),
            })
        
        return JsonResponse({
            'success': True,
            'categorias': categorias_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro interno: {str(e)}'
        }, status=500)



# Lista de fabricantes
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import Fabricante

CAMPOS = ['nome', 'nif', 'origem', 'cidade', 'provincia', 'telefone', 'email', 'ativo']
LISTA = reverse_lazy('produtos:fabricante_lista')


class FabricanteListView(LoginRequiredMixin, ListView):
    model = Fabricante
    template_name = 'produtos/fabricante_list.html'
    context_object_name = 'fabricantes'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().order_by('nome')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(nif__icontains=q))
        return qs


class FabricanteCreateView(LoginRequiredMixin, CreateView):
    model = Fabricante
    fields = CAMPOS
    template_name = 'fornecedores/form_generico.html'
    success_url = LISTA
    extra_context = {'titulo': 'Novo Fabricante'}


class FabricanteUpdateView(LoginRequiredMixin, UpdateView):
    model = Fabricante
    fields = CAMPOS
    template_name = 'fornecedores/form_generico.html'
    success_url = LISTA
    extra_context = {'titulo': 'Editar Fabricante'}


class FabricanteDeleteView(LoginRequiredMixin, DeleteView):
    model = Fabricante
    template_name = 'fornecedores/confirmar_exclusao.html'
    success_url = LISTA

    
logger = logging.getLogger(__name__)


# =============================================================================
# TEMPLATE DE IMPORTAÇÃO
# =============================================================================
class TemplateProdutosView(LoginRequiredMixin, TenantRequeridoMixin, View):
    """
    Gera o modelo .xlsx para ImportarProdutosView.
    Colunas = cabeçalhos da exportação + campos extra aceites pela importação,
    de modo que exportar -> editar -> importar e template -> importar usem o
    mesmo formato.
    """
    # Colunas que só existem na importação (a exportação não as inclui)
    HEADERS_EXTRA = [
        'numero_lote', 'data_validade',
        'estoque_minimo', 'estoque_maximo',
        'margem_lucro', 'desconto_percentual',
        'observacoes',
    ]
    # Único campo estritamente obrigatório na importação
    OBRIGATORIOS = {'nome_produto'}
    # Recomendados (produtos novos ficam incompletos sem eles)
    RECOMENDADOS = {'codigo_barras', 'categoria', 'preco_custo', 'preco_venda'}
    # Colunas que devem ficar como texto (evita 7,89E+12, perda de zeros, datas convertidas)
    COLUNAS_TEXTO = {'codigo_barras', 'codigo_interno', 'numero_lote', 'data_validade'}
    COLUNAS_NUMERICAS = {
        'preco_custo', 'preco_venda', 'Taxa IVA (%)', 'estoque_atual', 'estoque_minimo',
        'estoque_maximo', 'margem_lucro', 'desconto_percentual',
    }
    LINHAS_FORMATADAS = 1000  # linhas pré-formatadas / com validação

    EXEMPLO = {
        'nome_produto': 'Paracetamol 500mg',
        'codigo_barras': '7891234567890',
        'categoria': 'Analgésicos',
        'preco_custo': 105.50,
        'preco_venda': 200.00,
        'Taxa IVA (%)': 14,
        'nome_comercial': 'Paracetamol 500mg',
        'codigo_interno': 'PARA500',
        'fabricante': 'NEWAY FARMÁCIA',
        'fornecedor': 'NEWAY MED',
        'estoque_atual': 100,
        'ativo': 'Ativo',
        'numero_lote': 'LOTE202801',
        'data_validade': '2028-12-31',
        'estoque_minimo': 10,
        'estoque_maximo': 1000,
        'margem_lucro': 100.00,
        'desconto_percentual': 0.00,
        'observacoes': 'Produto de exemplo - apague esta linha antes de importar',
    }

    INSTRUCOES = [
        ("INSTRUÇÕES PARA IMPORTAÇÃO DE PRODUTOS", 'titulo'),
        ("", None),
        ("CAMPO OBRIGATÓRIO (cabeçalho a laranja):", 'secao'),
        ("- nome_produto: nome do produto. Linhas sem nome são ignoradas.", None),
        ("", None),
        ("CAMPOS RECOMENDADOS (cabeçalho a amarelo):", 'secao'),
        ("- codigo_barras: identifica o produto. Se já existir, o produto é ATUALIZADO; se não, é criado.", None),
        ("- categoria: criada automaticamente se não existir.", None),
        ("- preco_custo / preco_venda: números (ex.: 12.50). Se vazios em produto novo, ficam 0.", None),
        ("", None),
        ("CAMPOS OPCIONAIS:", 'secao'),
        ("- Taxa IVA (%): percentagem de IVA (ex.: 14, 7, 0), entre 0 e 100. Vazio = 0% em produto novo. A taxa é criada se não existir.", None),
        ("- nome_comercial: se vazio, usa nome_produto.", None),
        ("- codigo_interno: se vazio em produto novo, é gerado automaticamente (INT-xxxxxxxx).", None),
        ("- fabricante: criado automaticamente se não existir.", None),
        ("- fornecedor: NÃO é criado. Deve existir no sistema (nome fantasia, razão social, código ou NIF/BI). Se não for encontrado, o vínculo é ignorado e o produto é importado sem fornecedor.", None),
        ("- estoque_atual: quantidade em stock (padrão em produto novo: 0).", None),
        ("- estoque_minimo (padrão: 1) e estoque_maximo (padrão: 100).", None),
        ("- margem_lucro e desconto_percentual: em % (padrão: 0).", None),
        ("- observacoes: texto livre.", None),
        ("- ativo: Ativo/Inativo (também aceita 1/0, sim/não, true/false). Padrão: Ativo.", None),
        ("", None),
        ("LOTE E VALIDADE:", 'secao'),
        ("- Para criar/atualizar um lote, preencha numero_lote E data_validade.", None),
        ("- Se estoque_atual estiver preenchido, esse valor passa a ser a quantidade do lote.", None),
        ("- Datas aceites: AAAA-MM-DD (recomendado), DD/MM/AAAA, AAAA/MM/DD, DD-MM-AAAA, DD.MM.AAAA.", None),
        ("- Data de validade inválida faz a linha falhar (as restantes continuam).", None),
        ("", None),
        ("FORMATOS:", 'secao'),
        ("- Decimais: use ponto (12.50). Também são aceites formatos como 1.234,56 e valores com %, Kz ou AKZ.", None),
        ("- Células vazias ou com '-' são tratadas como não preenchidas.", None),
        ("", None),
        ("NOTAS IMPORTANTES:", 'secao'),
        ("- Em produtos EXISTENTES, células vazias NÃO apagam dados: só os campos preenchidos são atualizados.", None),
        ("- O produto é localizado pelo codigo_barras; se vazio, pelo codigo_interno.", None),
        ("- Se ambos estiverem vazios, é criado um produto novo a cada importação (gera duplicados ao reimportar).", None),
        ("- Os dados são importados apenas para a empresa atual (isolamento por tenant).", None),
        ("- Linhas com erro são ignoradas e listadas no resumo; as restantes são importadas.", None),
        ("- Apague a linha de exemplo (linha 2) antes de importar.", None),
        ("- Pode reutilizar o ficheiro de exportação de produtos como base de importação.", None),
    ]

    def get(self, request):
        try:
            headers = list(ExportarProdutosExcelView.HEADERS) + self.HEADERS_EXTRA

            wb = Workbook()
            ws = wb.active
            ws.title = "Produtos"  # tem de ser a 1.ª folha: é a que a importação lê

            bold = Font(bold=True)
            center = Alignment(horizontal="center", vertical="center")
            thin_border = Border(
                left=Side(style="thin"), right=Side(style="thin"),
                top=Side(style="thin"), bottom=Side(style="thin"),
            )
            fill_obrigatorio = PatternFill(start_color="F8B26A", end_color="F8B26A", fill_type="solid")
            fill_recomendado = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")
            fill_opcional = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

            # --- Cabeçalho (linha 1: o importador procura-o nas primeiras 15 linhas) ---
            ws.append(headers)
            for col, nome in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col)
                cell.font = bold
                cell.alignment = center
                cell.border = thin_border
                if nome in self.OBRIGATORIOS:
                    cell.fill = fill_obrigatorio
                elif nome in self.RECOMENDADOS:
                    cell.fill = fill_recomendado
                else:
                    cell.fill = fill_opcional
            ws.freeze_panes = "A2"

            # --- Formatação das colunas (texto / numérico) ---
            ultima = self.LINHAS_FORMATADAS + 1
            for col, nome in enumerate(headers, 1):
                if nome in self.COLUNAS_TEXTO:
                    formato = '@'
                elif nome in self.COLUNAS_NUMERICAS:
                    formato = '#,##0.00'
                else:
                    continue
                for row in range(2, ultima + 1):
                    ws.cell(row=row, column=col).number_format = formato

            # --- Linha de exemplo (mapeada por nome de coluna, nunca por posição) ---
            for col, nome in enumerate(headers, 1):
                valor = self.EXEMPLO.get(nome)
                if valor is not None:
                    ws.cell(row=2, column=col, value=valor)

            # --- Validações ---
            col_ativo = get_column_letter(headers.index('ativo') + 1)
            dv_ativo = DataValidation(
                type="list", formula1='"Ativo,Inativo"', allow_blank=True,
                showErrorMessage=True, errorTitle="Valor inválido",
                error="Use Ativo ou Inativo.",
            )
            dv_ativo.add(f"{col_ativo}2:{col_ativo}{ultima}")
            ws.add_data_validation(dv_ativo)

            col_taxa = get_column_letter(headers.index('Taxa IVA (%)') + 1)
            dv_taxa = DataValidation(
                type="decimal", operator="between", formula1="0", formula2="100",
                allow_blank=True, showErrorMessage=True,
                errorTitle="Taxa inválida", error="A taxa de IVA deve estar entre 0 e 100.",
            )
            dv_taxa.add(f"{col_taxa}2:{col_taxa}{ultima}")
            ws.add_data_validation(dv_taxa)

            # --- Larguras ---
            for col, nome in enumerate(headers, 1):
                exemplo = self.EXEMPLO.get(nome)
                comprimento = max(len(str(nome)), len(str(exemplo)) if exemplo is not None else 0)
                ws.column_dimensions[get_column_letter(col)].width = min(max(comprimento + 2, 12), 40)

            # --- Folha de instruções ---
            ws_instr = wb.create_sheet("Instruções")
            ws_instr.column_dimensions['A'].width = 120
            for row, (texto, tipo) in enumerate(self.INSTRUCOES, 1):
                cell = ws_instr.cell(row=row, column=1, value=texto)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if tipo == 'titulo':
                    cell.font = Font(bold=True, size=14)
                elif tipo == 'secao':
                    cell.font = bold

            # --- Resposta ---
            buffer = io.BytesIO()
            wb.save(buffer)

            nome_ficheiro = slugify(self.nome_tenant) or self.tenant.schema_name
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = (
                f'attachment; filename="template_produtos_{nome_ficheiro}_'
                f'{timezone.now().strftime("%Y%m%d")}.xlsx"'
            )
            return response

        except Exception as exc:
            logger.exception(f"Erro ao gerar template de produtos: {exc}")
            return HttpResponseBadRequest(f'Erro ao gerar template: {exc}')

# =============================================================================
# IMPORTAÇÃO
# =============================================================================
class ImportarProdutosView(LoginRequiredMixin, TenantRequeridoMixin, FormView):
    template_name = 'produtos/importar_produtos.html'
    form_class = ImportarProdutosForm
    success_url = reverse_lazy('produtos:produto_list')
    acao_requerida = 'editar_produtos'

    # Cabeçalhos aceites -> campo interno. Inclui os cabeçalhos da exportação
    # (ex.: "Taxa IVA (%)") para que exportar -> importar funcione.
    COLUNAS = {
        'nome_produto': 'nome', 'produto': 'nome', 'nome': 'nome',
        'descricao': 'nome', 'descrição': 'nome',
        'preco': 'preco_venda', 'preço': 'preco_venda', 'valor': 'preco_venda',
        'preco_custo': 'preco_custo', 'preco_venda': 'preco_venda',
        'taxa': 'taxa', 'iva': 'taxa', 'imposto': 'taxa', 'percentage': 'taxa',
        'taxa iva (%)': 'taxa',
        'categoria': 'categoria', 'grupo': 'categoria',
        'fornecedor': 'fornecedor', 'fabricante': 'fabricante',
        'codigo_barras': 'codigo_barras', 'codigo_interno': 'codigo_interno',
        'nome_comercial': 'nome_comercial',
        'numero_lote': 'numero_lote', 'lote': 'numero_lote',
        'validade': 'data_validade', 'data_validade': 'data_validade',
        'vencimento': 'data_validade',
        'estoque_atual': 'estoque_atual', 'estoque': 'estoque_atual',
        'estoque_minimo': 'estoque_minimo', 'estoque_maximo': 'estoque_maximo',
        'margem_lucro': 'margem_lucro', 'desconto_percentual': 'desconto_percentual',
        'observacoes': 'observacoes', 'ativo': 'ativo',
    }
    VAZIOS = {'', '-', 'nan', 'none', 'null', 'nat', 'n/a'}
    VERDADEIROS = {'1', '1.0', 'true', 'sim', 'yes', 'verdadeiro', 'ativo', 's', 'y'}
    FORMATOS_DATA = ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y', '%d.%m.%Y')
    CAMPOS_NUMERICOS = (
        'preco_custo', 'preco_venda', 'estoque_atual', 'estoque_minimo',
        'estoque_maximo', 'margem_lucro', 'desconto_percentual',
    )

    # ------------------------------
    # Utilidades
    # ------------------------------
    def sanitize_text(self, text):
        if not text:
            return ''
        try:
            text = str(text)
            text = unicodedata.normalize('NFKC', text)
            return text.strip()
        except Exception:
            return str(text).strip()

    def _texto(self, valor):
        """Texto limpo; células vazias / '-' / 'nan' viram ''."""
        texto = self.sanitize_text(valor)
        return '' if texto.lower() in self.VAZIOS else texto

    def _codigo(self, valor):
        """Códigos lidos do Excel podem vir como '123.0'."""
        texto = self._texto(valor)
        return texto[:-2] if re.fullmatch(r'\d+\.0', texto) else texto

    def _decimal(self, valor):
        """Decimal finito, ou None se vazio/inválido. Aceita '1.234,56', '1,234.56', '14%'."""
        texto = self._texto(valor)
        if not texto:
            return None
        texto = re.sub(r'[^\d,.\-+]', '', texto)  # remove %, Kz, AKZ, espaços...
        if not texto:
            return None
        if ',' in texto and '.' in texto:
            if texto.rfind(',') > texto.rfind('.'):
                texto = texto.replace('.', '').replace(',', '.')
            else:
                texto = texto.replace(',', '')
        elif ',' in texto:
            texto = texto.replace(',', '.')
        elif texto.count('.') > 1:
            texto = texto.replace('.', '')
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            return None
        return numero if numero.is_finite() else None

    def _taxa(self, valor):
        """Taxa IVA normalizada (0.00–100.00) ou None se inválida."""
        numero = self._decimal(valor)
        if numero is None:
            return None
        try:
            numero = numero.quantize(Decimal('0.01'))
        except InvalidOperation:
            return None
        return numero if Decimal('0') <= numero <= Decimal('100') else None

    def _data(self, valor):
        if hasattr(valor, 'date') and callable(valor.date):
            return valor.date()
        texto = self._texto(valor)
        if not texto:
            return None
        texto = texto.split(' ')[0].split('T')[0]  # remove hora ("2026-01-31 00:00:00")
        for formato in self.FORMATOS_DATA:
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue
        return None

    # ------------------------------
    # Leitura do ficheiro
    # ------------------------------
    def _aplicar_cabecalho(self, bruto):
        """
        Excel lido sem cabeçalho: procura a linha de cabeçalhos nas primeiras 15
        linhas. Necessário porque a exportação coloca os totais nas linhas 1-2.
        """
        if bruto.empty:
            return bruto
        indice = 0
        for i in range(min(len(bruto), 15)):
            celulas = [self._texto(c).lower() for c in bruto.iloc[i].tolist()]
            if any(self.COLUNAS.get(c) == 'nome' for c in celulas):
                indice = i
                break
        cabecalho = [self._texto(c).lower() for c in bruto.iloc[indice].tolist()]
        df = bruto.iloc[indice + 1:].reset_index(drop=True)
        df.columns = cabecalho
        return df

    def _carregar_dataframe(self, arquivo):
        conteudo = arquivo.read()
        nome_arquivo = (getattr(arquivo, 'name', '') or '').lower()

        # dtype=str evita que códigos de barras virem float (7.89E+12) ou percam zeros
        if nome_arquivo.endswith(('.xlsx', '.xls')):
            bruto = pd.read_excel(io.BytesIO(conteudo), header=None, dtype=str)
            return self._aplicar_cabecalho(bruto)

        try:
            texto = conteudo.decode('utf-8-sig')  # remove BOM, se existir
        except UnicodeDecodeError:
            texto = conteudo.decode('latin1')

        try:
            sep = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=';,\t|').delimiter
        except Exception:
            sep = ';' if texto.count(';') > texto.count(',') else ','
        return pd.read_csv(io.StringIO(texto), sep=sep, on_bad_lines='skip', dtype=str)

    # ------------------------------
    # Pré-carga em bloco (mapas em memória)
    # ------------------------------
    def _nomes_unicos(self, df, coluna, presentes):
        if coluna not in presentes:
            return []
        nomes = {self._texto(v) for v in df[coluna].dropna().unique()}
        return sorted(n for n in nomes if n)

    def _resolver_ou_criar(self, modelo, nomes, **extra):
        """
        Mapa {nome.lower(): objeto}. Comparação case-insensitive (evita duplicar
        'Analgésicos' / 'analgésicos'). O schema do tenant já isola os dados.
        """
        def carregar():
            return {self._texto(o.nome).lower(): o for o in modelo.objects.all()}

        existentes = carregar()
        novos = {}
        for nome in nomes:
            chave = nome.lower()
            if chave not in existentes and chave not in novos:
                novos[chave] = modelo(nome=nome, **extra)
        if novos:
            modelo.objects.bulk_create(list(novos.values()))
            existentes = carregar()
        return existentes

    def _mapa_taxas(self, df, presentes):
        chaves = {Decimal('0.00')}  # produtos novos sem taxa ficam com 0% (comportamento original)
        if 'taxa' in presentes:
            for valor in df['taxa'].dropna().unique():
                if self._texto(valor):
                    chave = self._taxa(valor)
                    if chave is not None:
                        chaves.add(chave)

        taxa_map = {t.tax_percentage: t for t in TaxaIVAAGT.objects.filter(tax_percentage__in=chaves)}
        novas = [
            TaxaIVAAGT(
                nome=f"IVA {valor}%",
                tax_type='IVA',
                tax_code='NOR',
                tax_percentage=valor,
                exemption_reason=None if valor > 0 else 'M99',
                ativo=True,
            )
            for valor in sorted(chaves) if valor not in taxa_map
        ]
        if novas:
            TaxaIVAAGT.objects.bulk_create(novas)
            taxa_map = {t.tax_percentage: t for t in TaxaIVAAGT.objects.filter(tax_percentage__in=chaves)}
        return taxa_map

    def _mapa_fornecedores(self):
        """Fornecedores nunca são criados automaticamente; só vinculados.
        Aceita nome fantasia, razão social, código (FOR-00001) ou NIF/BI."""
        mapa = {}
        for f in Fornecedor.objects.all():
            for chave in (f.nome_fantasia, f.razao_social, f.codigo_fornecedor, f.nif_bi):
                chave = self._texto(chave).lower()
                if chave:
                    mapa.setdefault(chave, f)
        return mapa

    # ------------------------------
    # Processamento principal
    # ------------------------------
    def processar_arquivo(self, arquivo):
        """Devolve (criados, atualizados, lista_de_erros)."""
        criados = atualizados = 0
        erros = []

        try:
            try:
                arquivo.seek(0)  # o form pode já ter lido o ficheiro
            except Exception:
                pass

            df = self._carregar_dataframe(arquivo)
            if df.empty:
                logger.warning("O arquivo foi lido mas não contém dados!")
                return 0, 0, []

            df.columns = [str(c).strip().lower() for c in df.columns]
            df = df.rename(columns=lambda c: self.COLUNAS.get(c, c))
            df = df.loc[:, ~df.columns.duplicated()].copy()  # dedup DEPOIS do rename
            presentes = set(df.columns)
            logger.info(f"Colunas mapeadas: {list(df.columns)}")

            if 'nome' not in presentes:
                raise ValueError(
                    "Coluna do nome do produto não encontrada "
                    "(use: nome_produto, nome, produto ou descricao)."
                )

            with transaction.atomic():
                taxa_map = self._mapa_taxas(df, presentes)
                cat_map = self._resolver_ou_criar(
                    Categoria, self._nomes_unicos(df, 'categoria', presentes), ativa=True
                )
                fab_map = self._resolver_ou_criar(
                    Fabricante, self._nomes_unicos(df, 'fabricante', presentes), ativo=True
                )
                forn_map = self._mapa_fornecedores() if 'fornecedor' in presentes else {}

                for numero, row in enumerate(df.to_dict('records'), start=1):
                    try:
                        # savepoint por linha: um erro de BD não "envenena" a transação toda
                        with transaction.atomic():
                            resultado = self._importar_linha(
                                row, presentes, taxa_map, cat_map, fab_map, forn_map
                            )
                        if resultado == 'criado':
                            criados += 1
                        elif resultado == 'atualizado':
                            atualizados += 1
                    except Exception as exc:
                        logger.error(f"Erro ao processar linha {numero} ({row}): {exc}")
                        erros.append(f"linha {numero}: {exc}")

        except Exception as exc:
            logger.exception(f"Erro geral ao processar arquivo: {exc}")
            raise ValueError(f"Erro ao processar arquivo: {exc}")

        return criados, atualizados, erros

    def _importar_linha(self, row, presentes, taxa_map, cat_map, fab_map, forn_map):
        def val(coluna):
            valor = row.get(coluna)
            try:
                return valor if pd.notna(valor) else None
            except (TypeError, ValueError):
                return valor

        def texto(coluna):
            return self._texto(val(coluna)) if coluna in presentes else ''

        nome = texto('nome')
        if not nome:
            return None

        # Só entram em `dados` os campos realmente presentes e preenchidos no ficheiro,
        # para que uma planilha parcial não apague dados de produtos existentes.
        dados = {}

        categoria = texto('categoria')
        if categoria:
            dados['categoria'] = cat_map.get(categoria.lower())

        fabricante = texto('fabricante')
        if fabricante:
            dados['fabricante'] = fab_map.get(fabricante.lower())

        fornecedor = texto('fornecedor')
        if fornecedor:
            obj_fornecedor = forn_map.get(fornecedor.lower())
            if obj_fornecedor:
                dados['fornecedor'] = obj_fornecedor
            else:
                logger.warning(f"Fornecedor '{fornecedor}' não encontrado; vínculo ignorado.")

        taxa_iva = None
        if texto('taxa'):
            chave = self._taxa(val('taxa'))
            if chave is None or chave not in taxa_map:
                raise ValueError(f"Taxa de IVA inválida: '{val('taxa')}'")
            taxa_iva = taxa_map[chave]

        for campo in self.CAMPOS_NUMERICOS:
            if texto(campo):
                numero = self._decimal(val(campo))
                if numero is None:
                    raise ValueError(f"Valor inválido em '{campo}': '{val(campo)}'")
                dados[campo] = numero

        if texto('observacoes'):
            dados['observacoes'] = texto('observacoes')
        if texto('ativo'):
            dados['ativo'] = texto('ativo').lower() in self.VERDADEIROS

        codigo_barras = self._codigo(val('codigo_barras')) if 'codigo_barras' in presentes else ''
        codigo_interno = self._codigo(val('codigo_interno')) if 'codigo_interno' in presentes else ''
        nome_comercial = texto('nome_comercial')

        # --- Localizar produto (o schema do tenant já garante o isolamento) ---
        produto = None
        if codigo_barras:
            produto = Produto.objects.filter(codigo_barras=codigo_barras).first()
        elif codigo_interno:
            produto = Produto.objects.filter(codigo_interno=codigo_interno).first()

        if produto is None:
            novo = {
                'preco_custo': Decimal('0'), 'preco_venda': Decimal('0'),
                'estoque_atual': Decimal('0'), 'estoque_minimo': Decimal('1'),
                'estoque_maximo': Decimal('100'), 'margem_lucro': Decimal('0'),
                'desconto_percentual': Decimal('0'), 'ativo': True,
            }
            novo.update(dados)
            novo.update({
                'nome_produto': nome,
                'nome_comercial': nome_comercial or nome,
                'codigo_interno': codigo_interno or f"INT-{uuid.uuid4().hex[:8]}",
                'taxa_iva': taxa_iva or taxa_map[Decimal('0.00')],
            })
            produto = Produto.objects.create(
                codigo_barras=codigo_barras or f"AUTO-{uuid.uuid4().hex[:10]}",
                **novo,
            )
            resultado = 'criado'
        else:
            dados['nome_produto'] = nome
            if nome_comercial:
                dados['nome_comercial'] = nome_comercial
            if codigo_interno:
                dados['codigo_interno'] = codigo_interno
            if taxa_iva:
                dados['taxa_iva'] = taxa_iva
            for campo, valor in dados.items():
                setattr(produto, campo, valor)
            produto.save()
            resultado = 'atualizado'

        # --- Lote ---
        numero_lote = texto('numero_lote')
        validade_bruta = val('data_validade') if 'data_validade' in presentes else None
        if numero_lote and self._texto(validade_bruta):
            validade = self._data(validade_bruta)
            if validade is None:
                raise ValueError(f"Data de validade inválida: '{validade_bruta}'")

            campos_lote = {
                'data_validade': validade,
                'preco_custo_lote': dados.get('preco_custo', produto.preco_custo),
            }
            if 'estoque_atual' in dados:
                quantidade = int(dados['estoque_atual'])
                campos_lote['quantidade_inicial'] = quantidade
                campos_lote['quantidade_atual'] = quantidade

            lote = Lote.objects.filter(produto=produto, numero_lote=numero_lote).first()
            if lote is None:
                Lote.objects.create(
                    produto=produto,
                    numero_lote=numero_lote,
                    **{'quantidade_inicial': 0, 'quantidade_atual': 0, **campos_lote},
                )
            else:
                for campo, valor in campos_lote.items():
                    setattr(lote, campo, valor)
                lote.save()

        return resultado

    # ------------------------------
    # Execução do formulário
    # ------------------------------
    def form_valid(self, form):
        arquivo = form.cleaned_data.get('arquivo')
        if not arquivo:
            messages.error(self.request, "Nenhum arquivo foi enviado.")
            return self.form_invalid(form)

        try:
            criados, atualizados, erros = self.processar_arquivo(arquivo)
        except Exception as exc:
            logger.exception(f"Erro ao importar produtos: {exc}")
            messages.error(self.request, f"Erro ao importar produtos: {exc}")
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Importação concluída: {criados} produtos criados e {atualizados} atualizados."
        )
        if erros:
            resumo = "; ".join(erros[:5]) + ("..." if len(erros) > 5 else "")
            messages.warning(
                self.request,
                f"{len(erros)} linha(s) foram ignoradas por erro: {resumo}"
            )
        return super().form_valid(form)


# =============================================================================
# EXPORTAÇÃO XLSX
# =============================================================================
class ExportarProdutosExcelView(LoginRequiredMixin, TenantRequeridoMixin, View):
    # Cabeçalhos compatíveis com a importação (ver ImportarProdutosView.COLUNAS)
    HEADERS = [
        'nome_produto', 'codigo_barras', 'categoria', 'preco_custo', 'preco_venda',
        'Taxa IVA (%)',
        'nome_comercial', 'codigo_interno', 'fabricante', 'fornecedor',
        'estoque_atual', 'ativo',
    ]

    def get(self, request):
        produtos = list(
            Produto.objects.select_related('categoria', 'fornecedor', 'fabricante', 'taxa_iva')
            .order_by('nome_produto')
        )

        def to_float(v):
            if v in (None, "", " ", "-"):
                return 0.0
            try:
                return float(str(v).replace(",", "."))
            except (TypeError, ValueError):
                return 0.0

        total_investido = sum(to_float(p.preco_custo) * to_float(p.estoque_atual) for p in produtos)
        total_esperado = sum(to_float(p.preco_venda) * to_float(p.estoque_atual) for p in produtos)

        wb = Workbook()
        ws = wb.active
        ws.title = "Produtos"

        bold = Font(bold=True)
        center = Alignment(horizontal="center", vertical="center")
        left = Alignment(horizontal="left", vertical="center")
        fill_header = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        # Totais: rótulo em A:B (mesclado) e valor em C.
        # (antes o valor ficava em B1 e era DESCARTADO pela mesclagem A1:B1)
        ws.append(["Total Investido (Custo × Estoque):", None, float(total_investido)])
        ws.append(["Total Esperado (Venda × Estoque):", None, float(total_esperado)])
        ws.append([])
        ws.merge_cells("A1:B1")
        ws.merge_cells("A2:B2")
        for ref in ("A1", "A2"):
            ws[ref].font = bold
            ws[ref].alignment = left
        for ref in ("C1", "C2"):
            ws[ref].font = bold
            ws[ref].number_format = '#,##0.00'

        ws.append(self.HEADERS)
        header_row = ws.max_row
        for col_num in range(1, len(self.HEADERS) + 1):
            cell = ws.cell(row=header_row, column=col_num)
            cell.font = bold
            cell.fill = fill_header
            cell.alignment = center
            cell.border = thin_border

        # Vazio em vez de '-' (na reimportação '-' criaria categoria/fabricante "-")
        for p in produtos:
            ws.append([
                p.nome_produto,
                p.codigo_barras,
                p.categoria.nome if p.categoria else '',
                to_float(p.preco_custo),
                to_float(p.preco_venda),
                float(p.taxa_iva.tax_percentage) if p.taxa_iva else 0.00,
                p.nome_comercial,
                p.codigo_interno,
                p.fabricante.nome if p.fabricante else '',
                p.fornecedor.nome_exibicao if p.fornecedor else '',
                to_float(p.estoque_atual),
                'Ativo' if p.ativo else 'Inativo',
            ])

        for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row):
            for cell in row:
                cell.border = thin_border
                if isinstance(cell.value, str) and cell.value.startswith('='):
                    cell.data_type = 's'  # nunca interpretar texto de utilizador como fórmula
                cell.alignment = center if isinstance(cell.value, (int, float)) else left

        # Largura calculada só a partir do cabeçalho/dados (os totais mesclados não distorcem)
        for col_idx in range(1, ws.max_column + 1):
            max_length = 0
            for row in ws.iter_rows(min_row=header_row, max_row=ws.max_row,
                                    min_col=col_idx, max_col=col_idx):
                valor = row[0].value
                max_length = max(max_length, len(str(valor)) if valor is not None else 0)
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_length + 2, 12), 60)

        buffer = io.BytesIO()
        wb.save(buffer)

        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        nome_ficheiro = slugify(self.nome_tenant) or self.tenant.schema_name
        response['Content-Disposition'] = f'attachment; filename="produtos_{nome_ficheiro}.xlsx"'
        return response


# =============================================================================
# EXPORTAÇÃO PDF
# =============================================================================
class ExportarProdutosPDFView(LoginRequiredMixin, TenantRequeridoMixin, View):
    def get(self, request):
        produtos = Produto.objects.select_related('taxa_iva').order_by('nome_produto')
        nome_empresa = self.nome_tenant

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=30,
            title=f"Listagem de Produtos - {nome_empresa}",
        )

        elementos = []
        styles = getSampleStyleSheet()
        estilo_celula = ParagraphStyle('Celula', parent=styles['Normal'], fontSize=9, leading=11)

        # Logotipo do tenant (opcional; nunca deve impedir a geração do PDF)
        try:
            foto = getattr(self.tenant, 'foto', None)
            url_logo = getattr(foto, 'url', None) if foto else None
            if url_logo:
                resp = requests.get(url_logo, timeout=5)
                if resp.status_code == 200:
                    logo_stream = io.BytesIO(resp.content)
                    largura, altura = ImageReader(logo_stream).getSize()
                    logo_stream.seek(0)
                    escala = min(4 * cm / largura, 4 * cm / altura)  # mantém proporção
                    img = Image(logo_stream, width=largura * escala, height=altura * escala)
                    img.hAlign = 'LEFT'
                    elementos.append(img)
                    elementos.append(Spacer(1, 12))
        except Exception as exc:
            logger.warning(f"Logotipo não incluído no PDF: {exc}")

        # escape(): nomes com & ou < quebram o parser XML do Paragraph
        elementos.append(Paragraph(f"<b>Listagem de Produtos – {escape(str(nome_empresa))}</b>", styles["Title"]))
        elementos.append(Paragraph(
            f"<font size=8>Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
            styles["Normal"]
        ))
        elementos.append(Spacer(1, 20))

        tabela_dados = [["Nº", "Produto", "Preço (AKZ)", "Taxa IVA", "Estoque"]]
        for i, p in enumerate(produtos, start=1):
            iva_str = f"{p.taxa_iva.tax_percentage:.2f}%" if p.taxa_iva else "0.00%"
            preco = f"{(p.preco_venda or 0):.2f}"
            tabela_dados.append([
                i,
                Paragraph(escape(p.nome_produto or ''), estilo_celula),  # quebra de linha em nomes longos
                preco,
                iva_str,
                p.estoque_atual,
            ])

        tabela = Table(tabela_dados, colWidths=[1.5*cm, 8*cm, 3*cm, 2.5*cm, 2*cm], repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (1, -1), "LEFT"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elementos.append(tabela)

        pdf.build(elementos)

        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        nome_ficheiro = slugify(nome_empresa) or self.tenant.schema_name
        response["Content-Disposition"] = f'attachment; filename="produtos_{nome_ficheiro}.pdf"'
        return response




# Em apps/servicos/views.py

from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from apps.clientes.models import Cliente
from apps.produtos.views import TenantRequeridoMixin
from .models import Servico, AgendamentoServico
from .forms import ServicoForm, AgendamentoServicoForm
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, request
from django.views.decorators.http import require_http_methods
from .models import NotificacaoAgendamento, ConfiguracaoNotificacao
from .forms import NotificacaoAgendamentoForm, ConfiguracaoNotificacaoForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from .models import NotificacaoAgendamento





# --- VIEW BASE (BOA PRÁTICA) ---
class ServicoPermissionMixin(LoginRequiredMixin):
    def get_queryset(self):
        empresa_atual = getattr(self.request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return self.model.objects.none()

        return self.model.objects.filter(empresa_atual=empresa_atual)

    def get_empresa(self):
        empresa_atual = getattr(self.request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return None

        return empresa_atual


# --- CRUD DO CATÁLOGO DE SERVIÇOS ---

class ServicoDashboard(ServicoPermissionMixin, ListView):
    model = Servico
    template_name = 'servicos/dashboard_servicos.html'
    #context_object_name = 'servicos'


class ServicoListView(ServicoPermissionMixin, ListView):
    model = Servico
    template_name = 'servicos/servico_list.html'
    context_object_name = 'servicos'

class ServicoCreateView(ServicoPermissionMixin, CreateView):
    model = Servico
    form_class = ServicoForm
    template_name = 'servicos/servico_form.html'
    success_url = reverse_lazy('servicos:servico_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs
    
    def form_valid(self, form):
        servico = form.save(commit=False)
        servico.empresa = self.get_empresa()
        servico.usuario_criacao = self.request.user
        # Valores placeholder para campos obrigatórios que não estão no form
        servico.cliente = Cliente.objects.filter(empresa=self.get_empresa()).first() 
        servico.data_agendamento = timezone.now()
        servico.save()
        messages.success(self.request, "Serviço de catálogo criado com sucesso.")
        return redirect(self.success_url)

class ServicoUpdateView(ServicoPermissionMixin, UpdateView):
    model = Servico
    form_class = ServicoForm
    template_name = 'servicos/servico_form.html'
    success_url = reverse_lazy('servicos:servico_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Serviço de catálogo atualizado com sucesso.")
        return super().form_valid(form)

class ServicoDeleteView(ServicoPermissionMixin, DeleteView):
    model = Servico
    template_name = 'servicos/servico_confirm_delete.html'
    success_url = reverse_lazy('servicos:servico_list')

    def form_valid(self, form):
        messages.success(self.request, f"Serviço '{self.object.nome}' eliminado com sucesso.")
        return super().form_valid(form)

# --- CRUD DE AGENDAMENTOS ---
class AgendamentoListView(ServicoPermissionMixin, ListView):
    model = AgendamentoServico
    template_name = 'servicos/agendamento_list.html'
    context_object_name = 'agendamentos'

class AgendamentoCreateView(ServicoPermissionMixin, CreateView):
    model = AgendamentoServico
    form_class = AgendamentoServicoForm
    template_name = 'servicos/agendamento_form.html'
    success_url = reverse_lazy('servicos:agendamento_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        form.instance.empresa = self.get_empresa()
        messages.success(self.request, "Agendamento criado com sucesso.")
        return super().form_valid(form)

class AgendamentoUpdateView(ServicoPermissionMixin, UpdateView):
    model = AgendamentoServico
    form_class = AgendamentoServicoForm
    template_name = 'servicos/agendamento_form.html'
    success_url = reverse_lazy('servicos:agendamento_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Agendamento atualizado com sucesso.")
        return super().form_valid(form)

class AgendamentoDeleteView(ServicoPermissionMixin, DeleteView):
    model = AgendamentoServico
    template_name = 'servicos/agendamento_confirm_delete.html'
    success_url = reverse_lazy('servicos:agendamento_list')

    def form_valid(self, form):
        messages.success(self.request, f"Agendamento para '{self.object.cliente.nome_completo}' eliminado com sucesso.")
        return super().form_valid(form)



from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from .models import AgendamentoServico

@login_required
@require_http_methods(["GET"])
def buscar_agendamento_api(request):
    """
    API para buscar agendamentos.
    Suporta filtragem por cliente, serviço ou funcionário.
    """
    try:
        query = request.GET.get('q', '').strip()
        status = request.GET.get('status', '').strip()

        # Empresa do usuário
        empresa_atual = getattr(request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return JsonResponse({
                'success': False,
                'message': 'Empresa não encontrada'
            }, status=400)

        # Query base
        agendamentos = AgendamentoServico.objects.filter(
            empresa=empresa_atual
        ).select_related('cliente', 'servico', 'funcionario')

        # Filtrar por status
        if status:
            agendamentos = agendamentos.filter(status=status)

        # Filtrar por pesquisa (cliente, serviço, funcionário)
        if query:
            agendamentos = agendamentos.filter(
                Q(cliente__nome_completo__icontains=query) |
                Q(servico__nome__icontains=query) |
                Q(funcionario__nome_completo__icontains=query)
            )

        # Limitar resultados para performance
        agendamentos = agendamentos[:100]

        agendamentos_data = [
            {
                'id': a.id,
                'data_hora': a.data_hora.isoformat(),
                'servico': a.servico.nome if a.servico else '',
                'cliente': a.cliente.nome_completo if a.cliente else '',
                'funcionario': a.funcionario.nome_completo if a.funcionario else '',
                'status': getattr(a, 'status', ''),
            }
            for a in agendamentos
        ]

        return JsonResponse({'success': True, 'agendamentos': agendamentos_data, 'total_encontrados': len(agendamentos_data)})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=500)



from django.views.generic import View, DetailView
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from .models import Servico, AgendamentoServico
from .forms import FinalizarServicoForm


class AgendamentoDetailView(ServicoPermissionMixin, DetailView):
    model = AgendamentoServico
    template_name = 'servicos/agendamento_detail.html'
    context_object_name = 'agendamento'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Agendamento #{self.object.id}"
        # Adiciona o formulário para a ação de finalizar
        context['finalizar_form'] = FinalizarServicoForm()
        return context

# --- VIEWS DE AÇÃO ---

class IniciarServicoView(LoginRequiredMixin, TenantRequeridoMixin, View):
    def post(self, request, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoServico, pk=kwargs['pk'])
        
        # A lógica para criar/obter o Serviço e iniciar
        servico, created = Servico.objects.get_or_create(
            agendamento=agendamento,
            defaults={
                'empresa': agendamento.empresa,
                'nome': agendamento.servico.nome,
                'categoria': agendamento.servico.categoria,
                'cliente': agendamento.cliente,
                'funcionario': agendamento.funcionario,
                'data_agendamento': agendamento.data_hora,
                'duracao_minutos': agendamento.duracao_minutos,
                'preco_servico': agendamento.servico.preco_padrao,
                'usuario_criacao': request.user,
                'status': 'agendado' # Status inicial no modelo Servico
            }
        )

        try:
            servico.iniciar_servico()
            agendamento.status = 'em_andamento'
            agendamento.save()
            messages.success(request, f"Serviço '{servico.numero_servico}' iniciado com sucesso.")
        except ValidationError as e:
            messages.error(request, e.message)
            
        return redirect('servicos:agendamento_detail', pk=agendamento.pk)



class FinalizarServicoView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoServico, pk=kwargs['pk'])
        servico_realizado = getattr(agendamento, 'servico', None)

        if not servico_realizado:
            messages.error(request, "Não é possível finalizar um serviço que não foi iniciado.")
            return redirect('servicos:agendamento_detail', pk=agendamento.pk)

        form = FinalizarServicoForm(request.POST)
        if form.is_valid():
            try:
                servico_realizado.finalizar_servico(
                    resultado=form.cleaned_data['resultado_servico'],
                    recomendacoes=form.cleaned_data['recomendacoes']
                )
                agendamento.status = 'finalizado'
                agendamento.save()
                messages.success(request, "Serviço finalizado com sucesso.")
            except ValidationError as e:
                messages.error(request, e.message)
        else:
            messages.error(request, "Formulário inválido. Por favor, preencha os campos necessários.")
            
        return redirect('servicos:agendamento_detail', pk=agendamento.pk)




from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

@login_required
@require_http_methods(["GET"])
def listar_servicos_api(request):
    """
    API para listar serviços no PDV
    """
    try:
        # Tenant/empresa atual definido pelo domínio da requisição
        empresa_atual = getattr(request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return JsonResponse({
                'success': False,
                'message': 'Empresa não encontrada'
            }, status=400)
        
        servicos = Servico.objects.filter(
            ativo=True
        ).select_related('categoria')
        
        servicos_data = []
        for servico in servicos:
            servicos_data.append({
                'id': servico.id,
                'nome': servico.nome,
                'categoria': servico.categoria.nome if servico.categoria else '',
                'categoria_id': servico.categoria.id if servico.categoria else None,
                'preco': float(servico.preco_padrao),
                'descricao': getattr(servico, 'instrucoes_padrao', ''),
                'disponivel': True  # Serviços geralmente estão sempre disponíveis
            })
        
        return JsonResponse({
            'success': True,
            'servicos': servicos_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro interno: {str(e)}'
        }, status=500)
    

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from .models import Servico

@login_required
@require_http_methods(["GET"])
def buscar_servicos_api(request):
    """
    API para buscar serviços da empresa do usuário.
    Suporta filtragem por categoria e pesquisa por nome.
    """
    try:
        busca = request.GET.get('q', '').strip()
        categoria_id = request.GET.get('categoria', '').strip()
        empresa_atual = getattr(request, 'tenant', None)

        if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
            return JsonResponse({
                'success': False,
                'message': 'Empresa não encontrada'
            }, status=400)
        
        # Query base
        servicos = Servico.objects.filter(
            ativo=True
        ).select_related('categoria')

        # Filtrar por categoria se especificado
        if categoria_id and categoria_id != 'todos':
            servicos = servicos.filter(categoria_id=categoria_id)

        # Filtrar por busca se especificado
        if busca:
            servicos = servicos.filter(nome__icontains=busca)

        # Limitar resultados
        servicos = servicos[:100]

        servicos_data = [
            {
                'id': s.id,
                'nome': s.nome,
                'categoria': s.categoria.nome if s.categoria else '',
                'categoria_id': s.categoria.id if s.categoria else None,
                'preco_padrao': float(s.preco_padrao),
                'desconto_percentual': float(s.desconto_percentual),
                'iva_percentual': float(getattr(s, 'iva_percentual', 0)),
            }
            for s in servicos
        ]

        return JsonResponse({'success': True, 'servicos': servicos_data, 'total_encontrados': len(servicos_data)})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=500)




# -----------------------
# Notificações CRUD
# -----------------------
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .models import NotificacaoAgendamento, ConfiguracaoNotificacao
from .forms import NotificacaoAgendamentoForm, ConfiguracaoNotificacaoForm
from django.db.models import Q


# ------------------------------
# Notificação de Agendamento
# ------------------------------

@login_required
def notificacao_list(request):
    """Listagem inicial de notificações (com busca AJAX)"""
    return render(request, 'servicos/notificacao_list.html')


@login_required
def notificacao_create(request):
    """Criar nova notificação"""

    if request.method == 'POST':
        form = NotificacaoAgendamentoForm(request.POST)

        if form.is_valid():
            notif = form.save(commit=False)

            # Tenant/empresa atual definido pelo domínio da requisição
            empresa = getattr(request, 'tenant', None)

            if not empresa or getattr(empresa, 'schema_name', 'public') == 'public':
                return JsonResponse({
                    'success': False,
                    'message': 'Empresa não encontrada'
                }, status=400)

            notif.empresa = empresa
            notif.save()

            return redirect('servicos:notificacao_list')

    else:
        form = NotificacaoAgendamentoForm()

    return render(
        request,
        'servicos/notificacao_form.html',
        {'form': form}
    )


@login_required
def notificacao_update(request, pk):
    """Editar notificação existente"""
    notif = get_object_or_404(NotificacaoAgendamento, pk=pk)
    if request.method == 'POST':
        form = NotificacaoAgendamentoForm(request.POST, instance=notif)
        if form.is_valid():
            form.save()
            return redirect('servicos:notificacao_list')
    else:
        form = NotificacaoAgendamentoForm(instance=notif)
    return render(request, 'servicos/notificacao_form.html', {'form': form})


@login_required
def notificacao_delete(request, pk):
    notificacao = get_object_or_404(NotificacaoAgendamento, pk=pk)
    
    if request.method == "POST":
        notificacao.delete()
        messages.success(request, "Notificação deletada com sucesso.")
        return redirect(reverse("servicos:notificacao_list"))
    
    # Se quiser uma página de confirmação
    return render(request, "servicos/notificacao_confirm_delete.html", {"notificacao": notificacao})


@login_required
@require_http_methods(["GET"])
def buscar_notificacao_api(request):
    """Busca AJAX para notificações"""
    busca = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    empresa_atual = getattr(request, 'tenant', None)

    if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
        return JsonResponse({
            'success': False,
            'message': 'Empresa não encontrada'
        }, status=400)


    queryset = NotificacaoAgendamento.objects.filter()

    if busca:
        queryset = queryset.filter(
            Q(titulo__icontains=busca) |
            Q(cliente__nome_completo__icontains=busca) |
            Q(mensagem__icontains=busca)
        )

    if status_filter:
        queryset = queryset.filter(status=status_filter)

    queryset = queryset.select_related('cliente', 'agendamento')[:50]

    data = []
    for n in queryset:
        data.append({
            'id': n.id,
            'titulo': n.titulo,
            'cliente': n.cliente.nome_completo,
            'tipo_notificacao': n.get_tipo_notificacao_display(),
            'status': n.get_status_display(),
            'data_agendada_envio': n.data_agendada_envio.strftime("%d/%m/%Y %H:%M"),
        })

    return JsonResponse({'success': True, 'servicos': data, 'total': len(data)})


# ------------------------------
# Configuração de Notificações
# ------------------------------

@login_required
def configuracao_notificacao_update(request):
    """Criar ou editar configuração da empresa"""
    # Tenant/empresa atual definido pelo domínio da requisição
    empresa = getattr(request, 'tenant', None)

    if not empresa or getattr(empresa, 'schema_name', 'public') == 'public':
        return redirect('home')
    
    config, _ = ConfiguracaoNotificacao.objects.get_or_create()

    if request.method == 'POST':
        form = ConfiguracaoNotificacaoForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            return redirect('servicos:configuracao_update')
    else:
        form = ConfiguracaoNotificacaoForm(instance=config)

    return render(request, 'servicos/configuracao_form.html', {'form': form})



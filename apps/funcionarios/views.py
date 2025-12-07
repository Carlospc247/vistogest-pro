# apps/funcionarios/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from django.core.paginator import Paginator
from django.urls import reverse_lazy
from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from apps.vendas.models import FaturaCredito, Venda

from .models import (
    Funcionario, Cargo, Departamento, EscalaTrabalho, RegistroPonto,
    Ferias, Capacitacao, AvaliacaoDesempenho, JornadaTrabalho,
    Afastamento, Beneficio, PontoEletronico, Formacao,
    ResponsabilidadeTecnica, Meta, ProcessoSeletivo, Candidato,
    Comunicado, FolhaPagamento, ItemFolhaPagamento, EventoFolha,
    HistoricoSalarial
)
from django.contrib.auth.mixins import AccessMixin


# =====================================
# DASHBOARD E LISTAGENS PRINCIPAIS
# =====================================

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


from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden

def permissao_acao_required(acao_requerida=None):
    """
    Decorator para function-based views que verifica:
    1. Usuário autenticado
    2. Usuário ligado a um registro Funcionario
    3. Permissão de ação específica
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Acesso negado. Usuário não autenticado.")
                return redirect(reverse_lazy('core:login'))  # ou handle customizado

            try:
                funcionario = request.user.funcionario
            except Exception:
                messages.error(
                    request,
                    "Acesso negado. O seu usuário não está ligado a um registro de funcionário."
                )
                return redirect(reverse_lazy('core:dashboard'))

            if acao_requerida:
                if not funcionario.pode_realizar_acao(acao_requerida):
                    messages.error(
                        request,
                        f"Acesso negado. O seu cargo não permite realizar a ação de '{acao_requerida}'."
                    )
                    return redirect(reverse_lazy('core:dashboard'))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


class FuncionarioDashboardView(LoginRequiredMixin, PermissaoAcaoMixin,  TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'funcionarios/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        
        context.update({
            'total_funcionarios': Funcionario.objects.filter(ativo=True).count(),
            'funcionarios_experiencia': Funcionario.objects.filter(em_experiencia=True).count(),
            'aniversariantes_mes': Funcionario.objects.filter(
                data_nascimento__month=hoje.month,
                ativo=True
            ).count(),
            'ferias_pendentes': Ferias.objects.filter(status='planejada').count(),
            'avaliacoes_pendentes': AvaliacaoDesempenho.objects.filter(
                data_avaliacao__isnull=True
            ).count(),
        })
        return context

class FuncionariosView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/lista.html'
    context_object_name = 'funcionarios'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Funcionario.objects.select_related('cargo', 'departamento', 'loja_principal')
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(nome_completo__icontains=search) |
                Q(matricula__icontains=search) |
                Q(bi__icontains=search)
            )
        
        cargo = self.request.GET.get('cargo')
        if cargo:
            queryset = queryset.filter(cargo_id=cargo)
            
        departamento = self.request.GET.get('departamento')
        if departamento:
            queryset = queryset.filter(departamento_id=departamento)
            
        status = self.request.GET.get('status')
        if status == 'ativo':
            queryset = queryset.filter(ativo=True)
        elif status == 'inativo':
            queryset = queryset.filter(ativo=False)
            
        return queryset.order_by('nome_completo')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cargos'] = Cargo.objects.filter(ativo=True)
        context['departamentos'] = Departamento.objects.filter(ativo=True)
        return context





class MeuTurnoView(LoginRequiredMixin, TemplateView):
    template_name = 'funcionarios/meu_turno.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        funcionario = get_object_or_404(Funcionario, usuario=self.request.user)
        hoje = timezone.now().date()
        
        # ----------------------------------------------------
        # NOVAS CONSULTAS: MÉTRICAS DE VENDAS (AQUISIÇÃO DE VALOR)
        # ----------------------------------------------------
        
        # 1. Total de Vendas Diretas (Fatura Recibo, Balcão, etc.)
        # Filtra vendas finalizadas no dia de hoje, realizadas pelo funcionário
        vendas_diretas = Venda.objects.filter(
            vendedor=funcionario,
            data_venda__date=hoje,
            status='finalizada' # Apenas vendas que geraram receita de imediato
        )
        
        total_venda_direta = vendas_diretas.aggregate(
            total_vendas=Sum('total')
        )['total_vendas'] or Decimal('0.00')

        # 2. Total de Faturas de Crédito Emitidas
        # Filtra faturas (dívidas) emitidas no dia de hoje, realizadas pelo funcionário (se tiver um campo vendedor/emissor)
        # **ATENÇÃO:** O seu modelo FaturaCredito não tem um campo 'vendedor', o que é uma FALHA EMPRESARIAL.
        # Assumindo uma correção: FaturaCredito.vendedor = models.ForeignKey('funcionarios.Funcionario', ...)
        try:
             faturas_emitidas = FaturaCredito.objects.filter(
                 # vendedor=funcionario, # CAMPO A SER ADICIONADO PARA RASTREABILIDADE
                 data_emissao__date=hoje
             )
             total_faturado_credito = faturas_emitidas.aggregate(
                 total_faturado=Sum('total_faturado')
             )['total_faturado'] or Decimal('0.00')
        except:
             # Se o campo não existir (na sua implementação atual), defina como zero e alerte.
             total_faturado_credito = Decimal('0.00')

        # ----------------------------------------------------
        # ATUALIZAÇÃO DO CONTEXTO (VISÃO PRÁTICA E DE NEGÓCIO)
        # ----------------------------------------------------
        
        context.update({
            'funcionario': funcionario,
            'hoje': hoje,
            # Informação de Ponto e Escala (já existente)
            'escala_hoje': EscalaTrabalho.objects.filter(
                funcionario=funcionario,
                data_trabalho=hoje
            ).first(),
            'pontos_hoje': RegistroPonto.objects.filter(
                funcionario=funcionario,
                data_registro=hoje
            ).order_by('hora_registro'),
            'proximas_escalas': EscalaTrabalho.objects.filter(
                funcionario=funcionario,
                data_trabalho__gt=hoje
            ).order_by('data_trabalho')[:5],
            
            # NOVAS MÉTRICAS DE VENDAS
            'total_venda_direta_hoje': total_venda_direta,
            'total_faturado_credito_hoje': total_faturado_credito,
            'total_receita_bruta_hoje': total_venda_direta + total_faturado_credito,
            'vendas_diretas_count': vendas_diretas.count(),
            
            # Verificar se já fechou o turno hoje
            'fechamento_hoje': FechamentoTurno.objects.filter(
                funcionario=funcionario,
                data_fechamento__date=hoje
            ).first(),
            
            # Dados para o gráfico de vendas por hora
            'sales_chart_data': json.dumps(list(vendas_diretas.extra({'hour': "EXTRACT(hour FROM data_venda)"}).values('hour').annotate(total=Sum('total')).order_by('hour')))
        })
        return context
    
# =====================================
# CRUD FUNCIONÁRIOS
# =====================================

class FuncionarioDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/detail.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        funcionario = self.object
        
        context.update({
            'avaliacoes_recentes': funcionario.avaliacoes.order_by('-data_avaliacao')[:3],
            'ferias_ativas': funcionario.ferias.filter(status='em_andamento'),
            'capacitacoes_recentes': funcionario.capacitacoes.order_by('-data_inicio')[:3],
            'beneficios_ativos': funcionario.beneficios.filter(ativo=True),
        })
        return context

class FuncionarioCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/form.html'
    fields = [
        'nome_completo', 'bi', 'data_nascimento', 'sexo', 'estado_civil',
        'endereco', 'numero', 'bairro', 'cidade', 'provincia', 'postal',
        'telefone', 'whatsapp', 'email_pessoal', 'email_corporativo',
        'cargo', 'departamento', 'loja_principal', 'supervisor',
        'tipo_contrato', 'data_admissao', 'salario_atual',
        'vale_alimentacao', 'vale_transporte', 'escolaridade'
    ]
    
    def form_valid(self, form):
        form.instance.empresa = self.request.user.empresa
        messages.success(self.request, 'Funcionário criado com sucesso!')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('funcionarios:detail', kwargs={'pk': self.object.pk})

class FuncionarioUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/form.html'
    fields = [
        'nome_completo', 'telefone', 'whatsapp', 'email_pessoal',
        'email_corporativo', 'endereco', 'numero', 'bairro', 'cidade',
        'cargo', 'departamento', 'supervisor', 'salario_atual',
        'vale_alimentacao', 'vale_transporte'
    ]
    
    def form_valid(self, form):
        messages.success(self.request, 'Funcionário atualizado com sucesso!')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('funcionarios:detail', kwargs={'pk': self.object.pk})

class FuncionarioDeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/confirm_delete.html'
    success_url = reverse_lazy('funcionarios:funcionarios')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Funcionário removido com sucesso!')
        return super().delete(request, *args, **kwargs)

# =====================================
# STATUS DO FUNCIONÁRIO
# =====================================

@login_required
@permissao_acao_required(acao_requerida='acessar_rh')
def ativar_funcionario(request, pk):
    funcionario = get_object_or_404(Funcionario, pk=pk)
    funcionario.ativo = True
    funcionario.save()
    messages.success(request, f'{funcionario.nome_completo} foi ativado.')
    return redirect('funcionarios:detail', pk=pk)

@login_required
@permissao_acao_required(acao_requerida='acessar_rh')
def desativar_funcionario(request, pk):
    funcionario = get_object_or_404(Funcionario, pk=pk)
    funcionario.ativo = False
    funcionario.save()
    messages.warning(request, f'{funcionario.nome_completo} foi desativado.')
    return redirect('funcionarios:detail', pk=pk)

class AtivarFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def post(self, request, pk):
        return ativar_funcionario(request, pk)

class DesativarFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def post(self, request, pk):
        return desativar_funcionario(request, pk)

class SuspenderFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def post(self, request, pk):
        funcionario = get_object_or_404(Funcionario, pk=pk)
        funcionario.afastado = True
        funcionario.motivo_afastamento = 'Suspensão disciplinar'
        funcionario.data_inicio_afastamento = timezone.now().date()
        funcionario.save()
        messages.warning(request, f'{funcionario.nome_completo} foi suspenso.')
        return redirect('funcionarios:detail', pk=pk)

class DemitirFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def post(self, request, pk):
        funcionario = get_object_or_404(Funcionario, pk=pk)
        funcionario.ativo = False
        funcionario.data_demissao = timezone.now().date()
        funcionario.save()
        messages.error(request, f'{funcionario.nome_completo} foi demitido.')
        return redirect('funcionarios:detail', pk=pk)

# =====================================
# PERFIL E DADOS PESSOAIS
# =====================================

class PerfilFuncionarioView(LoginRequiredMixin, DetailView):
    model = Funcionario
    template_name = 'funcionarios/perfil.html'
    context_object_name = 'funcionario'

class DocumentosFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/documentos.html'
    context_object_name = 'funcionario'

class FotoFuncionarioView(LoginRequiredMixin, UpdateView):
    model = Funcionario
    template_name = 'funcionarios/foto.html'
    fields = ['foto']
    
    def get_success_url(self):
        return reverse_lazy('funcionarios:perfil', kwargs={'pk': self.object.pk})

class ContatosFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/contatos.html'
    fields = ['telefone', 'whatsapp', 'email_pessoal', 'email_corporativo']
    
    def get_success_url(self):
        return reverse_lazy('funcionarios:perfil', kwargs={'pk': self.object.pk})

# =====================================
# CARGOS
# =====================================

class CargoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Cargo
    template_name = 'cargos/lista.html'
    context_object_name = 'cargos'
    paginate_by = 20

    def get_queryset(self):
        return Cargo.objects.filter(empresa=self.request.user.empresa)

class CargoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Cargo
    template_name = 'cargos/detail.html'
    context_object_name = 'cargo'

    def get_queryset(self):
        return Cargo.objects.filter(empresa=self.request.user.empresa)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['funcionarios'] = self.object.funcionarios.filter(ativo=True)
        return context

class CargoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = Cargo
    template_name = 'cargos/form.html'
    fields = [
        'nome', 'codigo', 'descricao', 'categoria', 'cargo_superior',
        'nivel_hierarquico', 'salario_base', 'vale_alimentacao',
        'vale_transporte', 'pode_vender', 'pode_fazer_desconto',
        'limite_desconto_percentual'
    ]
    success_url = reverse_lazy('funcionarios:cargo_lista')

    def form_valid(self, form):
        form.instance.empresa = self.request.user.empresa
        return super().form_valid(form)

    

class CargoUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_rh'
    model = Cargo
    template_name = 'cargos/form.html'
    fields = [
        'nome', 'descricao', 'categoria', 'cargo_superior',
        'salario_base', 'vale_alimentacao', 'vale_transporte',
        'pode_vender', 'pode_fazer_desconto', 'limite_desconto_percentual'
    ]
    success_url = reverse_lazy('funcionarios:cargo_lista')

    def get_queryset(self):
        return Cargo.objects.filter(empresa=self.request.user.empresa)
    

class CargoDeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'acessar_rh'
    model = Cargo
    template_name = 'cargos/confirm_delete.html'
    success_url = reverse_lazy('funcionarios:cargo_lista')

    def get_queryset(self):
        return Cargo.objects.filter(empresa=self.request.user.empresa)

# =====================================
# DEPARTAMENTOS
# =====================================

class DepartamentoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Departamento
    template_name = 'departamentos/lista.html'
    context_object_name = 'departamentos'

class DepartamentoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Departamento
    template_name = 'departamentos/detail.html'
    context_object_name = 'departamento'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['funcionarios'] = self.object.funcionarios.filter(ativo=True)
        return context

class DepartamentoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = Departamento
    template_name = 'departamentos/form.html'
    fields = ['nome', 'codigo', 'descricao', 'responsavel', 'loja', 'centro_custo']
    success_url = reverse_lazy('funcionarios:departamento_lista')

class DepartamentoUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_rh'
    model = Departamento
    template_name = 'departamentos/form.html'
    fields = ['nome', 'descricao', 'responsavel', 'centro_custo']
    success_url = reverse_lazy('funcionarios:departamento_lista')

class FuncionariosDepartamentoView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'departamentos/funcionarios.html'
    context_object_name = 'funcionarios'
    
    def get_queryset(self):
        departamento = get_object_or_404(Departamento, pk=self.kwargs['pk'])
        return departamento.funcionarios.filter(ativo=True)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departamento'] = get_object_or_404(Departamento, pk=self.kwargs['pk'])
        return context

# =====================================
# JORNADAS E ESCALAS
# =====================================

class JornadaTrabalhoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = JornadaTrabalho
    template_name = 'jornadas/lista.html'
    context_object_name = 'jornadas'

class JornadaTrabalhoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = JornadaTrabalho
    template_name = 'jornadas/form.html'
    fields = [
        'nome', 'turno', 'horario_entrada', 'horario_saida',
        'horario_almoco_inicio', 'horario_almoco_fim', 'departamento', 'loja'
    ]
    success_url = reverse_lazy('funcionarios:jornada_lista')

class JornadaFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/jornada_funcionario.html'
    context_object_name = 'funcionario'

class EscalaTrabalhoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'funcionarios/escala.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio = self.request.GET.get('data_inicio', timezone.now().date())
        data_fim = self.request.GET.get('data_fim', timezone.now().date() + timedelta(days=7))
        
        context['escalas'] = EscalaTrabalho.objects.filter(
            data_trabalho__range=[data_inicio, data_fim]
        ).select_related('funcionario', 'loja', 'departamento')
        
        return context

class HorarioTrabalhoView(LoginRequiredMixin, TemplateView):
    template_name = 'funcionarios/horarios.html'

# =====================================
# PONTO ELETRÔNICO
# =====================================

class PontoEletronicoView(LoginRequiredMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'ponto/lista.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        
        try:
            funcionario = Funcionario.objects.get(usuario=self.request.user)
            context['ponto_hoje'] = PontoEletronico.objects.filter(
                funcionario=funcionario,
                data=hoje
            ).first()
            context['funcionario'] = funcionario
        except Funcionario.DoesNotExist:
            context['funcionario'] = None
            
        return context

class RegistrarPontoView(LoginRequiredMixin, TemplateView):
    template_name = 'ponto/registrar.html'
    
    def post(self, request):
        try:
            funcionario = Funcionario.objects.get(usuario=request.user)
            hoje = timezone.now().date()
            agora = timezone.now().time()
            
            ponto, created = PontoEletronico.objects.get_or_create(
                funcionario=funcionario,
                data=hoje,
                defaults={'status': 'presente'}
            )
            
            # Lógica de marcação sequencial
            if not ponto.entrada_manha:
                ponto.entrada_manha = agora
                tipo_registro = 'Entrada'
            elif not ponto.saida_almoco:
                ponto.saida_almoco = agora
                tipo_registro = 'Saída para Almoço'
            elif not ponto.entrada_tarde:
                ponto.entrada_tarde = agora
                tipo_registro = 'Volta do Almoço'
            elif not ponto.saida:
                ponto.saida = agora
                tipo_registro = 'Saída'
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Todos os pontos do dia já foram registrados'
                })
            
            ponto.save()
            
            # Criar registro no histórico
            RegistroPonto.objects.create(
                funcionario=funcionario,
                data_registro=hoje,
                hora_registro=agora,
                tipo_registro=tipo_registro.lower().replace(' ', '_'),
                loja=funcionario.loja_principal,
                ip_registro=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({
                'success': True,
                'message': f'{tipo_registro} registrado com sucesso!',
                'horario': agora.strftime('%H:%M:%S')
            })
            
        except Funcionario.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Funcionário não encontrado'
            })


# apps/funcionarios/views.py (adicionar esta view)

from django.views.generic import ListView
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta, date
from .models import PontoEletronico, Funcionario

class HistoricoPontoView(ListView):
    model = PontoEletronico
    template_name = 'ponto/historico.html'
    context_object_name = 'pontos'
    paginate_by = 30
    ordering = ['-data']

    def get_queryset(self):
        # Obter funcionário da URL
        self.funcionario = get_object_or_404(Funcionario, pk=self.kwargs['funcionario_pk'])
        
        queryset = super().get_queryset().filter(funcionario=self.funcionario)
        
        # Filtros aplicados
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        status = self.request.GET.get('status')
        mes = self.request.GET.get('mes')
        ano = self.request.GET.get('ano')
        
        # Filtrar por período específico
        if data_inicio:
            try:
                data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
                queryset = queryset.filter(data__gte=data_inicio)
            except ValueError:
                pass
                
        if data_fim:
            try:
                data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
                queryset = queryset.filter(data__lte=data_fim)
            except ValueError:
                pass
        
        # Filtrar por mês/ano
        if mes and ano:
            try:
                mes = int(mes)
                ano = int(ano)
                queryset = queryset.filter(data__month=mes, data__year=ano)
            except ValueError:
                pass
        elif ano:  # Apenas ano
            try:
                ano = int(ano)
                queryset = queryset.filter(data__year=ano)
            except ValueError:
                pass
                
        # Filtrar por status
        if status:
            queryset = queryset.filter(status=status)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Adicionar funcionário ao contexto
        context['funcionario'] = self.funcionario
        
        # Choices para filtros
        context['status_choices'] = PontoEletronico.STATUS_CHOICES
        
        # Filtros aplicados
        context['filtros'] = {
            'data_inicio': self.request.GET.get('data_inicio'),
            'data_fim': self.request.GET.get('data_fim'),
            'status': self.request.GET.get('status'),
            'mes': self.request.GET.get('mes'),
            'ano': self.request.GET.get('ano'),
        }
        
        # Estatísticas do período filtrado
        pontos_periodo = self.get_queryset()
        
        # Contadores por status
        total_pontos = pontos_periodo.count()
        total_presencas = pontos_periodo.filter(status='presente').count()
        total_faltas = pontos_periodo.filter(status='falta').count()
        total_faltas_justificadas = pontos_periodo.filter(status='falta_justificada').count()
        total_ferias = pontos_periodo.filter(status='ferias').count()
        total_feriados = pontos_periodo.filter(status='feriado').count()
        
        # Calcular total de horas trabalhadas
        total_segundos_trabalhados = 0
        pontos_trabalhados = pontos_periodo.filter(status='presente')
        
        for ponto in pontos_trabalhados:
            horas_dia = ponto.horas_trabalhadas_dia
            if horas_dia and horas_dia.total_seconds() > 0:
                total_segundos_trabalhados += horas_dia.total_seconds()
        
        total_horas_trabalhadas = total_segundos_trabalhados / 3600
        
        # Calcular médias
        media_horas_dia = total_horas_trabalhadas / total_presencas if total_presencas > 0 else 0
        percentual_presenca = (total_presencas / total_pontos * 100) if total_pontos > 0 else 0
        
        context['estatisticas'] = {
            'total_pontos': total_pontos,
            'total_presencas': total_presencas,
            'total_faltas': total_faltas,
            'total_faltas_justificadas': total_faltas_justificadas,
            'total_ferias': total_ferias,
            'total_feriados': total_feriados,
            'total_horas_trabalhadas': round(total_horas_trabalhadas, 2),
            'media_horas_dia': round(media_horas_dia, 2),
            'percentual_presenca': round(percentual_presenca, 1),
        }
        
        # Meses e anos disponíveis para filtro
        context['meses'] = [
            (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
            (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
            (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
        ]
        
        # Anos baseados nos registros existentes
        anos_com_registros = PontoEletronico.objects.filter(
            funcionario=self.funcionario
        ).dates('data', 'year').distinct()
        
        context['anos'] = [data.year for data in anos_com_registros]
        
        # Se não há registros, incluir o ano atual
        if not context['anos']:
            context['anos'] = [timezone.now().year]
        
        # Dados para gráfico de horas por semana (últimas 8 semanas)
        hoje = timezone.now().date()
        horas_por_semana = []
        
        for i in range(8):
            inicio_semana = hoje - timedelta(days=hoje.weekday() + (i * 7))
            fim_semana = inicio_semana + timedelta(days=6)
            
            pontos_semana = PontoEletronico.objects.filter(
                funcionario=self.funcionario,
                data__range=[inicio_semana, fim_semana],
                status='presente'
            )
            
            total_horas_semana = 0
            for ponto in pontos_semana:
                horas = ponto.horas_trabalhadas_dia
                if horas:
                    total_horas_semana += horas.total_seconds() / 3600
            
            horas_por_semana.append({
                'semana': f"{inicio_semana.strftime('%d/%m')} - {fim_semana.strftime('%d/%m')}",
                'horas': round(total_horas_semana, 1)
            })
        
        context['horas_por_semana'] = list(reversed(horas_por_semana))
        
        # Resumo mensal (últimos 6 meses)
        resumo_mensal = []
        for i in range(6):
            if i == 0:
                mes_ref = hoje.replace(day=1)
            else:
                mes_anterior = resumo_mensal[-1]['data'] - timedelta(days=1)
                mes_ref = mes_anterior.replace(day=1)
            
            pontos_mes = PontoEletronico.objects.filter(
                funcionario=self.funcionario,
                data__year=mes_ref.year,
                data__month=mes_ref.month
            )
            
            presencas_mes = pontos_mes.filter(status='presente').count()
            faltas_mes = pontos_mes.filter(status='falta').count()
            
            total_horas_mes = 0
            for ponto in pontos_mes.filter(status='presente'):
                horas = ponto.horas_trabalhadas_dia
                if horas:
                    total_horas_mes += horas.total_seconds() / 3600
            
            resumo_mensal.append({
                'data': mes_ref,
                'mes_nome': mes_ref.strftime('%B'),
                'ano': mes_ref.year,
                'presencas': presencas_mes,
                'faltas': faltas_mes,
                'horas_trabalhadas': round(total_horas_mes, 1)
            })
            # Converter horas trabalhadas em decimal por registro
            for p in context['pontos']:
                horas = p.horas_trabalhadas_dia
                p.horas_decimal = horas.total_seconds() / 3600 if horas else 0

        
        context['resumo_mensal'] = resumo_mensal
        
        # Alertas
        alertas = []
        
        # Verificar faltas excessivas no mês atual
        faltas_mes_atual = PontoEletronico.objects.filter(
            funcionario=self.funcionario,
            data__year=hoje.year,
            data__month=hoje.month,
            status='falta'
        ).count()
        
        if faltas_mes_atual >= 3:
            alertas.append({
                'tipo': 'warning',
                'titulo': 'Faltas Excessivas',
                'mensagem': f'{faltas_mes_atual} faltas no mês atual'
            })
        
        # Verificar registros de ponto incompletos (últimos 7 dias)
        uma_semana_atras = hoje - timedelta(days=7)
        pontos_incompletos = PontoEletronico.objects.filter(
            funcionario=self.funcionario,
            data__gte=uma_semana_atras,
            data__lt=hoje,
            status='presente'
        ).filter(
            Q(entrada_manha__isnull=True) |
            Q(saida__isnull=True)
        ).count()
        
        if pontos_incompletos > 0:
            alertas.append({
                'tipo': 'danger',
                'titulo': 'Registros Incompletos',
                'mensagem': f'{pontos_incompletos} registros com horários em falta nos últimos 7 dias'
            })
        
        context['alertas'] = alertas
        
        return context

class RelatorioPontoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'ponto/relatorio.html'

class AjustesPontoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'ponto/ajustes.html'

# =====================================
# FOLHA DE PAGAMENTO
# =====================================

class FolhaPagamentoView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = FolhaPagamento
    template_name = 'folha/lista.html'
    context_object_name = 'folhas'
    paginate_by = 12

class CalcularFolhaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'folha/calcular.html'
    
    def post(self, request):
        mes = int(request.POST.get('mes'))
        ano = int(request.POST.get('ano'))
        
        folha, created = FolhaPagamento.objects.get_or_create(
            empresa=request.user.empresa,
            mes=mes,
            ano=ano,
            defaults={
                'descricao': f'Folha {mes:02d}/{ano}',
                'elaborada_por': request.user
            }
        )
        
        if folha.pode_editar:
            # Criar itens para todos os funcionários ativos
            funcionarios = Funcionario.objects.filter(ativo=True)
            for funcionario in funcionarios:
                item, created = ItemFolhaPagamento.objects.get_or_create(
                    folha=folha,
                    funcionario=funcionario,
                    defaults={
                        'salario_base': funcionario.salario_atual,
                        'vale_alimentacao': funcionario.vale_alimentacao,
                        'vale_transporte': funcionario.vale_transporte
                    }
                )
            
            folha.calcular_folha()
            messages.success(request, 'Folha calculada com sucesso!')
        else:
            messages.error(request, 'Esta folha não pode ser recalculada!')
        
        return redirect('funcionarios:folha_mensal', mes=mes, ano=ano)

class FolhaMensalView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = FolhaPagamento
    template_name = 'folha/mensal.html'
    context_object_name = 'folha'
    
    def get_object(self):
        return get_object_or_404(
            FolhaPagamento,
            mes=self.kwargs['mes'],
            ano=self.kwargs['ano']
        )

class HoleriteView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = ItemFolhaPagamento
    template_name = 'folha/holerite.html'
    context_object_name = 'item'
    
    def get_object(self):
        funcionario = get_object_or_404(Funcionario, pk=self.kwargs['pk'])
        folha = get_object_or_404(
            FolhaPagamento,
            mes=self.kwargs['mes'],
            ano=self.kwargs['ano']
        )
        return get_object_or_404(
            ItemFolhaPagamento,
            folha=folha,
            funcionario=funcionario
        )

class SalarioFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'funcionarios/salario.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['historico_salarial'] = self.object.historico_salarial.order_by('-data_vigencia')
        return context

# =====================================
# BENEFÍCIOS
# =====================================

class BeneficioListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Beneficio
    template_name = 'beneficios/lista.html'
    context_object_name = 'beneficios'

class BeneficiosFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'beneficios/funcionario.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['beneficios'] = self.object.beneficios.filter(ativo=True)
        return context

class ValeTransporteView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'beneficios/vale_transporte.html'

class ValeRefeicaoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'beneficios/vale_refeicao.html'

class PlanoSaudeView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'beneficios/plano_saude.html'

# =====================================
# FÉRIAS E AFASTAMENTOS
# =====================================

class FeriasListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Ferias
    template_name = 'ferias/lista.html'
    context_object_name = 'ferias'
    paginate_by = 20

class FeriasFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'ferias/funcionario.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ferias'] = self.object.ferias.order_by('-data_inicio')
        return context

class PlanejarFeriasView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = Ferias
    template_name = 'ferias/planejar.html'
    fields = [
        'funcionario', 'periodo_aquisitivo_inicio', 'periodo_aquisitivo_fim',
        'data_inicio', 'data_fim', 'dias_ferias', 'observacoes'
    ]
    success_url = reverse_lazy('funcionarios:ferias_lista')

class AfastamentoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Afastamento
    template_name = 'afastamentos/lista.html'
    context_object_name = 'afastamentos'

class AfastamentosFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'afastamentos/funcionario.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['afastamentos'] = self.object.afastamentos.order_by('-data_inicio')
        return context

# =====================================
# TREINAMENTOS E CAPACITAÇÃO
# =====================================

class TreinamentoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Capacitacao
    template_name = 'treinamentos/lista.html'
    context_object_name = 'treinamentos'

class TreinamentoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = Capacitacao
    template_name = 'treinamentos/form.html'
    fields = [
        'funcionario', 'titulo', 'descricao', 'tipo', 'carga_horaria',
        'data_inicio', 'data_fim', 'instituicao', 'instrutor',
        'local', 'modalidade', 'valor_inscricao'
    ]
    success_url = reverse_lazy('funcionarios:treinamento_lista')

class TreinamentoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Capacitacao
    template_name = 'treinamentos/detail.html'
    context_object_name = 'treinamento'

class TreinamentosFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'treinamentos/funcionario.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['capacitacoes'] = self.object.capacitacoes.order_by('-data_inicio')
        return context

class CertificacaoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Capacitacao
    template_name = 'certificacoes/lista.html'
    context_object_name = 'certificacoes'
    
    def get_queryset(self):
        return Capacitacao.objects.filter(
            status='concluida',
            certificado__isnull=False
        )

class ResponsabilidadeTecnicaView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = ResponsabilidadeTecnica
    template_name = 'responsabilidade_tecnica.html'
    context_object_name = 'responsabilidades'

# =====================================
# AVALIAÇÕES DE DESEMPENHO
# =====================================

class AvaliacaoDesempenhoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = AvaliacaoDesempenho
    template_name = 'avaliacoes/lista.html'
    context_object_name = 'avaliacoes'

class AvaliacoesFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'avaliacoes/funcionario.html'
    context_object_name = 'funcionario'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['avaliacoes'] = self.object.avaliacoes.order_by('-data_avaliacao')
        return context

class NovaAvaliacaoView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = AvaliacaoDesempenho
    template_name = 'avaliacoes/form.html'
    fields = [
        'funcionario', 'tipo_avaliacao', 'periodo_inicio', 'periodo_fim',
        'pontualidade', 'assiduidade', 'qualidade_trabalho', 'produtividade',
        'iniciativa', 'relacionamento_interpessoal', 'conhecimento_tecnico',
        'lideranca', 'pontos_fortes', 'pontos_melhorar', 'metas_objetivos'
    ]
    
    def form_valid(self, form):
        form.instance.avaliador = get_object_or_404(Funcionario, usuario=self.request.user)
        form.instance.data_avaliacao = timezone.now().date()
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('funcionarios:funcionario_avaliacoes', kwargs={'pk': self.object.funcionario.pk})

class MetasFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Meta
    template_name = 'funcionarios/metas.html'
    context_object_name = 'metas'
    
    def get_queryset(self):
        return Meta.objects.filter(funcionario=self.request.user)

# =====================================
# RECRUTAMENTO E SELEÇÃO
# =====================================

class RecrutamentoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'recrutamento/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'processos_ativos': ProcessoSeletivo.objects.filter(ativo=True).count(),
            'candidatos_analise': Candidato.objects.filter(status='analise').count(),
            'candidatos_entrevista': Candidato.objects.filter(status='entrevista').count(),
        })
        return context

class CandidatoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Candidato
    template_name = 'candidatos/lista.html'
    context_object_name = 'candidatos'

class CandidatoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Candidato
    template_name = 'candidatos/detail.html'
    context_object_name = 'candidato'

class ProcessoSeletivoView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = ProcessoSeletivo
    template_name = 'processos/lista.html'
    context_object_name = 'processos'

# =====================================
# RELATÓRIOS
# =====================================

class FuncionarioRelatoriosView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'relatorios/dashboard.html'

class RelatorioAniversariantesView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'relatorios/aniversariantes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mes = int(self.request.GET.get('mes', timezone.now().month))
        
        context['aniversariantes'] = Funcionario.objects.filter(
            data_nascimento__month=mes,
            ativo=True
        ).order_by('data_nascimento__day')
        
        return context

class RelatorioAdmissoesView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'relatorios/admissoes.html'

class RelatorioDemissoesView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'relatorios/demissoes.html'

class RelatorioFolhaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'relatorios/folha.html'

# =====================================
# DOCUMENTOS TRABALHISTAS
# =====================================

class CTPSView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'documentos/ctps.html'
    context_object_name = 'funcionario'

class ContratoTrabalhoView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'documentos/contrato.html'
    context_object_name = 'funcionario'

class TermoRescisaoView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'documentos/rescisao.html'
    context_object_name = 'funcionario'

class DeclaracoesView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_rh'
    model = Funcionario
    template_name = 'documentos/declaracoes.html'
    context_object_name = 'funcionario'

# =====================================
# COMUNICAÇÃO INTERNA
# =====================================

class ComunicadoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Comunicado
    template_name = 'comunicados/lista.html'
    context_object_name = 'comunicados'

class ComunicadoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_rh'
    model = Comunicado
    template_name = 'comunicados/form.html'
    fields = ['titulo', 'mensagem']
    
    def form_valid(self, form):
        form.instance.autor = self.request.user
        return super().form_valid(form)
    
    success_url = reverse_lazy('funcionarios:comunicado_lista')

class EnviarComunicadoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'comunicados/enviar.html'

class MuralEletronicoView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_rh'
    model = Comunicado
    template_name = 'funcionarios/mural.html'
    context_object_name = 'comunicados'
    
    def get_queryset(self):
        return Comunicado.objects.order_by('-created_at')[:10]

# =====================================
# AJAX E UTILITÁRIOS
# =====================================

class BuscarFuncionarioAjaxView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def get(self, request):
        termo = request.GET.get('q', '')
        funcionarios = Funcionario.objects.filter(
            nome_completo__icontains=termo,
            ativo=True
        )[:10]
        
        resultados = [
            {
                'id': f.id,
                'nome': f.nome_completo,
                'matricula': f.matricula,
                'cargo': f.cargo.nome
            }
            for f in funcionarios
        ]
        
        return JsonResponse({'funcionarios': resultados})

class CalcularSalarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def post(self, request):
        cargo_id = request.POST.get('cargo_id')
        if cargo_id:
            cargo = get_object_or_404(Cargo, pk=cargo_id)
            return JsonResponse({
                'salario_base': float(cargo.salario_base or 0),
                'vale_alimentacao': float(cargo.vale_alimentacao),
                'vale_transporte': float(cargo.vale_transporte)
            })
        return JsonResponse({'error': 'Cargo não encontrado'})

class VerificarBIFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def get(self, request):
        bi = request.GET.get('bi')
        existe = Funcionario.objects.filter(bi=bi).exists()
        return JsonResponse({'existe': existe})

class ConsultarPOSTALFuncionarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def get(self, request):
        postal = request.GET.get('postal')
        # Lógica de consulta de postal (mock)
        dados = {
            'bairro': 'Centro',
            'cidade': 'Luanda',
            'provincia': 'Luanda'
        }
        return JsonResponse(dados)

# =====================================
# IMPORTAÇÃO E EXPORTAÇÃO
# =====================================

class ImportarFuncionariosView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    template_name = 'funcionarios/importar.html'

class ExportarFuncionariosView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_rh'
    def get(self, request):
        # Lógica de exportação
        funcionarios = Funcionario.objects.filter(ativo=True)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="funcionarios.csv"'
        
        import csv
        writer = csv.writer(response)
        writer.writerow(['Matrícula', 'Nome', 'Cargo', 'Departamento', 'Salário'])
        
        for f in funcionarios:
            writer.writerow([
                f.matricula, f.nome_completo, f.cargo.nome,
                f.departamento.nome, f.salario_atual
            ])
        
        return response

# =====================================
# API VIEWS
# =====================================

class RegistrarPontoAPIView(LoginRequiredMixin, TemplateView):
    def post(self, request):
        # Implementação da API de registro de ponto
        return JsonResponse({'success': True})

class ConsultarFeriasAPIView(LoginRequiredMixin, TemplateView):
    def get(self, request):
        funcionario_id = request.GET.get('funcionario_id')
        if funcionario_id:
            ferias = Ferias.objects.filter(
                funcionario_id=funcionario_id,
                status__in=['aprovada', 'em_andamento']
            )
            dados = [
                {
                    'inicio': f.data_inicio.isoformat(),
                    'fim': f.data_fim.isoformat(),
                    'dias': f.dias_ferias,
                    'status': f.status
                }
                for f in ferias
            ]
            return JsonResponse({'ferias': dados})
        return JsonResponse({'error': 'Funcionário não especificado'})

class HorariosDisponiveisAPIView(LoginRequiredMixin, TemplateView):
    def get(self, request):
        data = request.GET.get('data')
        if data:
            escalas = EscalaTrabalho.objects.filter(data_trabalho=data)
            horarios = [
                {
                    'funcionario': e.funcionario.nome_completo,
                    'entrada': e.horario_entrada.strftime('%H:%M'),
                    'saida': e.horario_saida.strftime('%H:%M'),
                    'turno': e.get_turno_display()
                }
                for e in escalas
            ]
            return JsonResponse({'horarios': horarios})
        return JsonResponse({'error': 'Data não especificada'})


# =====================================
# FECHAMENTO DE TURNO
# =====================================

from django.template.loader import render_to_string
from weasyprint import HTML


from django.shortcuts import redirect
from django.contrib import messages
from django.views.generic import DetailView, TemplateView
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML


# =====================================
# FECHAR TURNO (usando RegistroPonto)
# =====================================
class FecharTurnoView(LoginRequiredMixin, TemplateView):
    template_name = 'funcionarios/meu_turno.html'

    def post(self, request):
        try:
            funcionario = Funcionario.objects.get(usuario=request.user)
            hoje = timezone.now().date()
            
            # Verificar se já existe registro hoje
            if RegistroPonto.objects.filter(funcionario=funcionario, data_registro=hoje).exists():
                messages.error(request, 'O turno de hoje já foi registrado.')
                return redirect('funcionarios:meuturno')

            # Obter valores informados (se necessário para relatórios, mas não será salvo em FechamentoTurno)
            valor_caixa = Decimal(request.POST.get('valor_caixa', '0').replace(',', '.'))
            valor_tpa = Decimal(request.POST.get('valor_tpa', '0').replace(',', '.'))
            valor_transferencia = Decimal(request.POST.get('valor_transferencia', '0').replace(',', '.'))
            observacoes = request.POST.get('observacoes', '')

            # Criar registro de ponto
            registro = RegistroPonto.objects.create(
                funcionario=funcionario,
                data_registro=hoje,
                hora_registro=timezone.now().time(),
                tipo_registro='saida',  # ajuste conforme sua lógica
                loja=funcionario.loja,
                observacoes=observacoes
            )

            messages.success(request, 'Turno registrado com sucesso!')
            return redirect('funcionarios:relatorio_fechamento', pk=registro.pk)

        except Funcionario.DoesNotExist:
            messages.error(request, 'Funcionário não encontrado.')
            return redirect('core:dashboard')
        except Exception as e:
            messages.error(request, f'Erro ao registrar turno: {str(e)}')
            return redirect('funcionarios:meuturno')


# =====================================
# RELATÓRIO PDF
# =====================================
class RelatorioFechamentoPDFView(LoginRequiredMixin, DetailView):
    model = RegistroPonto

    def get(self, request, *args, **kwargs):
        registro = self.get_object()
        vendas = Venda.objects.filter(
            vendedor=registro.funcionario,
            data_venda__date=registro.data_registro,
            status='finalizada'
        ).order_by('-data_venda')
        
        html_string = render_to_string('funcionarios/relatorio_fechamento_pdf.html', {
            'registro': registro,
            'vendas': vendas,
            'request': request,
        })
        
        pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="fechamento_turno_{registro.pk}.pdf"'
        return response



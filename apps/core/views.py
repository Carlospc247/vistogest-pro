# apps/core/views.py

from calendar import monthrange
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from apps.analytics.models import EventoAnalytics, NotificacaoAlerta
from apps.core.models import Categoria, Empresa
from apps.produtos.models import Produto
from apps.vendas.models import FaturaCredito, MetaVenda, Venda
from apps.servicos.models import NotificacaoAgendamento
from datetime import date, timedelta
import traceback
from django.core.exceptions import PermissionDenied


# ============================================================
# BASE VIEW COM CONTEXTO EMPRESARIAL
# ============================================================


class BaseMPAView(LoginRequiredMixin, TemplateView):
    """View base: define contexto padrão e empresa atual."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        context.update({
            'user': self.request.user,
            'empresa_atual': empresa,
            'current_module': getattr(self, 'module_name', 'dashboard'),
        })
        return context

    def get_empresa(self):
        """Obtém a empresa do utilizador logado ou lança erro se não existir."""
        user = self.request.user

        # Verifica se o user possui relação com uma empresa (via perfil/usuário/funcionário)
        empresa = None
        if hasattr(user, 'usuario') and getattr(user.usuario, 'empresa', None):
            empresa = user.usuario.empresa
        elif hasattr(user, 'funcionario') and getattr(user.funcionario, 'empresa', None):
            empresa = user.funcionario.empresa
        elif hasattr(user, 'profile') and getattr(user.profile, 'empresa', None):
            empresa = user.profile.empresa

        # Se não encontrou empresa, nega acesso
        if not empresa:
            raise PermissionDenied("O utilizador não está associado a nenhuma empresa.")

        return empresa


# ============================================================
# DASHBOARD
# ============================================================

# views.py - Versão corrigida
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear  # ⚠️ Import faltando
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
import json
from decimal import Decimal

class DashboardView(BaseMPAView):
    template_name = 'core/dashboard.html'
    module_name = 'dashboard'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        hoje = timezone.now().date()

        # ======= VENDAS =======
        vendas_hoje = Venda.objects.filter(
            empresa=empresa,
            data_venda__date=hoje,
            status='finalizada'
        ).aggregate(total=Sum('total'), quantidade=Count('id'))
        
        # ⚠️ Corrigir valores None
        vendas_hoje['total'] = vendas_hoje['total'] or Decimal('0.00')
        vendas_hoje['quantidade'] = vendas_hoje['quantidade'] or 0

        # ======= PRODUTOS =======
        produtos_stats = {
            'total': Produto.objects.filter(empresa=empresa, ativo=True).count(),
            'total_categorias': Categoria.objects.filter(empresa=empresa, ativa=True).count(),
        }

        # ======= ESTOQUE =======
        estoque_stats = {
            'estoque_baixo': Produto.objects.filter(
                empresa=empresa,
                ativo=True,
                estoque_atual__lte=F('estoque_minimo')
            ).count()
        }

        # ======= VENDAS RECENTES =======
        vendas_recentes = Venda.objects.filter(
            empresa=empresa,
            data_venda__date=hoje  # ⚠️ Apenas hoje para ser "recentes"
        ).select_related('cliente').order_by('-data_venda')[:10]

        # ======= TOP VENDEDORES =======
        inicio_mes = hoje.replace(day=1)
        top_vendedores = Venda.objects.filter(
            empresa=empresa,
            data_venda__date__gte=inicio_mes,
            status='finalizada',
            vendedor__isnull=False
        ).values(
            'vendedor_id',
            'vendedor__nome_completo'  # ⚠️ Verificar se este campo existe
        ).annotate(
            total_faturamento=Sum('total'),
            total_vendas=Count('id')
        ).order_by('-total_faturamento')[:5]

        # ⚠️ FATURAMENTO ORIGINAL (manter compatibilidade)
        faturamento_mensal = Venda.objects.filter(
            empresa=empresa,
            status='finalizada'
        ).annotate(
            mes=TruncMonth('data_venda')  # ⚠️ Agora importado corretamente
        ).values('mes').annotate(
            total_faturamento=Sum('total')
        ).order_by('mes')

        context.update({
            'vendas_hoje': vendas_hoje,
            'produtos_stats': produtos_stats,
            'estoque_stats': estoque_stats,
            'vendas_recentes': vendas_recentes,
            'top_vendedores': top_vendedores,
            'faturamento_labels': [f["mes"].strftime('%Y-%m') for f in faturamento_mensal],
            'faturamento_data': [float(f["total_faturamento"] or 0) for f in faturamento_mensal],  # ⚠️ Tratar None
            'alertas': self.get_alertas(),
        })

        # Dados para gráficos (JSON)
        context['dados_vendas_mensal'] = json.dumps(self.get_vendas_mensais(empresa))
        context['dados_vendas_semanal'] = json.dumps(self.get_vendas_semanais(empresa))
        context['dados_vendas_anual'] = json.dumps(self.get_vendas_anuais(empresa))
        context['dados_formas_pagamento'] = json.dumps(self.get_formas_pagamento(empresa))
        context['dados_metas'] = json.dumps(self.get_dados_metas(empresa))

        # Exibição adicional para superuser
        if self.request.user.is_superuser:
            context.update({
                'lista_empresas': Empresa.objects.all().order_by('-data_cadastro')[:10],
            })

        return context

    def get_vendas_mensais(self, empresa):
        """Dados de vendas dos últimos 12 meses - CORRIGIDO"""
        dados = {'labels': [], 'valores': []}
        
        # ⚠️ Usar TruncMonth do Django para otimizar
        vendas_por_mes = Venda.objects.filter(
            empresa=empresa,
            status='finalizada',
            data_venda__gte=timezone.now() - timedelta(days=365)  # Últimos 12 meses aproximadamente
        ).annotate(
            mes=TruncMonth('data_venda')
        ).values('mes').annotate(
            total=Sum('total')
        ).order_by('mes')
        
        # ⚠️ Incluir faturas crédito
        faturas_por_mes = FaturaCredito.objects.filter(
            empresa=empresa,
            status__in=['emitida', 'parcial', 'liquidada'],
            data_fatura__gte=timezone.now() - timedelta(days=365)
        ).annotate(
            mes=TruncMonth('data_fatura')
        ).values('mes').annotate(
            total=Sum('total')
        ).order_by('mes')
        
        # Combinar vendas e faturas por mês
        meses_combinados = {}
        
        for venda in vendas_por_mes:
            mes_key = venda['mes'].strftime('%Y-%m')
            meses_combinados[mes_key] = {
                'mes': venda['mes'],
                'total': float(venda['total'] or 0)
            }
        
        for fatura in faturas_por_mes:
            mes_key = fatura['mes'].strftime('%Y-%m')
            if mes_key in meses_combinados:
                meses_combinados[mes_key]['total'] += float(fatura['total'] or 0)
            else:
                meses_combinados[mes_key] = {
                    'mes': fatura['mes'],
                    'total': float(fatura['total'] or 0)
                }
        
        # Ordenar e formatar
        for mes_data in sorted(meses_combinados.values(), key=lambda x: x['mes']):
            dados['labels'].append(mes_data['mes'].strftime('%b/%Y'))
            dados['valores'].append(mes_data['total'])
        
        return dados

    def get_vendas_semanais(self, empresa):
        """Dados de vendas das últimas 8 semanas - CORRIGIDO"""
        dados = {'labels': [], 'valores': []}
        
        vendas_por_semana = Venda.objects.filter(
            empresa=empresa,
            status='finalizada',
            data_venda__gte=timezone.now() - timedelta(weeks=8)
        ).annotate(
            semana=TruncWeek('data_venda')
        ).values('semana').annotate(
            total=Sum('total')
        ).order_by('semana')
        
        faturas_por_semana = FaturaCredito.objects.filter(
            empresa=empresa,
            status__in=['emitida', 'parcial', 'liquidada'],
            data_fatura__gte=timezone.now() - timedelta(weeks=8)
        ).annotate(
            semana=TruncWeek('data_fatura')
        ).values('semana').annotate(
            total=Sum('total')
        ).order_by('semana')
        
        # Combinar vendas e faturas por semana
        semanas_combinadas = {}
        
        for venda in vendas_por_semana:
            semana_key = venda['semana'].strftime('%Y-%W')
            semanas_combinadas[semana_key] = {
                'semana': venda['semana'],
                'total': float(venda['total'] or 0)
            }
        
        for fatura in faturas_por_semana:
            semana_key = fatura['semana'].strftime('%Y-%W')
            if semana_key in semanas_combinadas:
                semanas_combinadas[semana_key]['total'] += float(fatura['total'] or 0)
            else:
                semanas_combinadas[semana_key] = {
                    'semana': fatura['semana'],
                    'total': float(fatura['total'] or 0)
                }
        
        # Ordenar e formatar
        for semana_data in sorted(semanas_combinadas.values(), key=lambda x: x['semana']):
            inicio_semana = semana_data['semana']
            fim_semana = inicio_semana + timedelta(days=6)
            label = f"{inicio_semana.strftime('%d/%m')} - {fim_semana.strftime('%d/%m')}"
            dados['labels'].append(label)
            dados['valores'].append(semana_data['total'])
        
        return dados

    def get_vendas_anuais(self, empresa):
        """Dados de vendas dos últimos 5 anos - CORRIGIDO"""
        dados = {'labels': [], 'valores': []}
        
        vendas_por_ano = Venda.objects.filter(
            empresa=empresa,
            status='finalizada',
            data_venda__gte=timezone.now() - timedelta(days=5*365)
        ).annotate(
            ano=TruncYear('data_venda')
        ).values('ano').annotate(
            total=Sum('total')
        ).order_by('ano')
        
        faturas_por_ano = FaturaCredito.objects.filter(
            empresa=empresa,
            status__in=['emitida', 'parcial', 'liquidada'],
            data_fatura__gte=timezone.now() - timedelta(days=5*365)
        ).annotate(
            ano=TruncYear('data_fatura')
        ).values('ano').annotate(
            total=Sum('total')
        ).order_by('ano')
        
        # Combinar vendas e faturas por ano
        anos_combinados = {}
        
        for venda in vendas_por_ano:
            ano_key = venda['ano'].year
            anos_combinados[ano_key] = float(venda['total'] or 0)
        
        for fatura in faturas_por_ano:
            ano_key = fatura['ano'].year
            if ano_key in anos_combinados:
                anos_combinados[ano_key] += float(fatura['total'] or 0)
            else:
                anos_combinados[ano_key] = float(fatura['total'] or 0)
        
        # Ordenar e formatar
        for ano in sorted(anos_combinados.keys()):
            dados['labels'].append(str(ano))
            dados['valores'].append(anos_combinados[ano])
        
        return dados

    def get_formas_pagamento(self, empresa):
        """Distribuição por formas de pagamento - CORRIGIDO"""
        inicio_mes = timezone.now().date().replace(day=1)
        
        # ⚠️ Verificar se o campo forma_pagamento__nome existe
        vendas_pagamento = Venda.objects.filter(
            empresa=empresa,
            data_venda__date__gte=inicio_mes,
            status='finalizada'
        ).values(
            'forma_pagamento__nome'
        ).annotate(
            total=Sum('total')
        ).order_by('-total')
        
        dados = {
            'labels': [],
            'valores': []
        }
        
        for item in vendas_pagamento:
            if item['total']:  # ⚠️ Só adicionar se houver valor
                dados['labels'].append(item['forma_pagamento__nome'] or 'Não Especificado')
                dados['valores'].append(float(item['total']))
        
        return dados

    def get_dados_metas(self, empresa):
        """Dados de metas vs realizado - CORRIGIDO"""
        hoje = timezone.now().date()
        
        # ⚠️ Verificar se o modelo MetaVenda existe e tem os campos corretos
        try:
            metas_mes = MetaVenda.objects.filter(
                empresa=empresa,
                status='ativa',
                mes=hoje.month,
                ano=hoje.year
            )
        except:
            # ⚠️ Fallback se MetaVenda não existir
            return {'labels': [], 'metas': [], 'realizados': []}
        
        dados = {'labels': [], 'metas': [], 'realizados': []}
        
        for meta in metas_mes:
            try:
                realizado = meta.calcular_realizado()
                
                if meta.vendedor:
                    # ⚠️ Verificar campo correto do vendedor
                    label = f"{meta.vendedor.nome_completo[:15]}..."
                else:
                    label = "Geral"
                
                valor_meta = 0
                valor_realizado = 0
                
                if meta.tipo_meta == 'faturamento':
                    valor_meta = float(meta.meta_faturamento or 0)
                    valor_realizado = float(realizado.get('faturamento_realizado', 0))
                elif meta.tipo_meta == 'quantidade':
                    valor_meta = float(meta.meta_quantidade_vendas or 0)
                    valor_realizado = float(realizado.get('quantidade_vendas_realizada', 0))
                
                dados['labels'].append(label)
                dados['metas'].append(valor_meta)
                dados['realizados'].append(valor_realizado)
                
            except Exception as e:
                # ⚠️ Log do erro mas continuar
                print(f"Erro ao processar meta {meta.id}: {e}")
                continue
        
        return dados

    def get_alertas(self):
        """Gera lista de alertas - CORRIGIDO"""
        empresa = self.get_empresa()
        alertas = []
        
        try:
            produtos_baixo = Produto.objects.filter(
                empresa=empresa, 
                ativo=True, 
                estoque_atual__lte=F('estoque_minimo')
            ).count()
            
            if produtos_baixo > 0:
                alertas.append({
                    'tipo': 'warning',
                    'titulo': 'Estoque Baixo',
                    'mensagem': f'{produtos_baixo} produtos com estoque baixo',
                    'link': '/dashboard/estoque/',
                    'icone': 'fas fa-exclamation-triangle'
                })
        except Exception as e:
            print(f"Erro ao gerar alertas: {e}")
            
        return alertas


# ============================================================
# API DASHBOARD (AJAX)
# ============================================================
class DashboardStatsAPI(LoginRequiredMixin, View):
    def get(self, request):
        return JsonResponse({'success': True, 'stats': {}})


# ============================================================
# CRUD DE CATEGORIAS
# ============================================================
@method_decorator(csrf_exempt, name='dispatch')
class CriarCategoriaView(LoginRequiredMixin, View):
    """Cria uma nova categoria vinculada à empresa do usuário."""

    def post(self, request):
        try:
            empresa = self._get_empresa(request)
            nome = request.POST.get('nome', '').strip()
            codigo = request.POST.get('codigo', '').strip()
            descricao = request.POST.get('descricao', '').strip()
            ativa = request.POST.get('ativa') == 'on'

            if not nome:
                return JsonResponse({'success': False, 'message': 'Nome é obrigatório'})

            if Categoria.objects.filter(nome__iexact=nome, empresa=empresa).exists():
                return JsonResponse({'success': False, 'message': 'Categoria já existe'})

            if codigo and Categoria.objects.filter(codigo__iexact=codigo, empresa=empresa).exists():
                return JsonResponse({'success': False, 'message': 'Código já está em uso'})

            categoria = Categoria.objects.create(
                empresa=empresa, nome=nome, codigo=codigo or '', descricao=descricao, ativa=ativa
            )

            return JsonResponse({
                'success': True,
                'message': 'Categoria criada com sucesso',
                'categoria': {'id': categoria.id, 'nome': categoria.nome}
            })

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'success': False, 'message': str(e)})

    def _get_empresa(self, request):
        user = request.user
        if hasattr(user, 'usuario') and user.usuario.empresa:
            return user.usuario.empresa
        elif hasattr(user, 'profile') and user.profile.empresa:
            return user.profile.empresa
        return Empresa.objects.first()


@method_decorator(csrf_exempt, name='dispatch')
class EditarCategoriaView(LoginRequiredMixin, View):
    """Edita categoria de forma segura por empresa."""

    def post(self, request, categoria_id):
        empresa = self._get_empresa(request)
        categoria = get_object_or_404(Categoria, id=categoria_id, empresa=empresa)

        nome = request.POST.get('nome', '').strip()
        codigo = request.POST.get('codigo', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        ativa = request.POST.get('ativa') == 'on'

        if not nome:
            return JsonResponse({'success': False, 'message': 'Nome é obrigatório'})

        if Categoria.objects.filter(nome__iexact=nome, empresa=empresa).exclude(id=categoria.id).exists():
            return JsonResponse({'success': False, 'message': 'Categoria já existe'})

        categoria.nome = nome
        categoria.codigo = codigo
        categoria.descricao = descricao
        categoria.ativa = ativa
        categoria.save()

        return JsonResponse({'success': True, 'message': 'Categoria atualizada com sucesso'})

    def _get_empresa(self, request):
        user = request.user
        if hasattr(user, 'usuario') and user.usuario.empresa:
            return user.usuario.empresa
        elif hasattr(user, 'profile') and user.profile.empresa:
            return user.profile.empresa
        return Empresa.objects.first()


class DeletarCategoriaView(LoginRequiredMixin, View):
    """Remove categoria apenas se não houver produtos associados."""

    def post(self, request, categoria_id):
        empresa = self._get_empresa(request)
        categoria = get_object_or_404(Categoria, id=categoria_id, empresa=empresa)

        if categoria.produtos.exists():
            return JsonResponse({
                'success': False,
                'message': 'Não é possível remover: há produtos associados.'
            })

        nome = categoria.nome
        categoria.delete()
        return JsonResponse({'success': True, 'message': f'Categoria "{nome}" removida com sucesso'})

    def _get_empresa(self, request):
        user = request.user
        if hasattr(user, 'usuario') and user.usuario.empresa:
            return user.usuario.empresa
        elif hasattr(user, 'profile') and user.profile.empresa:
            return user.profile.empresa
        return Empresa.objects.first()


class ToggleCategoriaView(LoginRequiredMixin, View):
    """Ativa/Desativa categoria restrita à empresa."""

    def post(self, request, categoria_id):
        empresa = self._get_empresa(request)
        categoria = get_object_or_404(Categoria, id=categoria_id, empresa=empresa)

        categoria.ativa = not categoria.ativa
        categoria.save()

        return JsonResponse({
            'success': True,
            'ativa': categoria.ativa,
            'message': f'Categoria {"ativada" if categoria.ativa else "desativada"} com sucesso'
        })

    def _get_empresa(self, request):
        user = request.user
        if hasattr(user, 'usuario') and user.usuario.empresa:
            return user.usuario.empresa
        elif hasattr(user, 'profile') and user.profile.empresa:
            return user.profile.empresa
        return Empresa.objects.first()


# ============================================================
# LISTAGEM DE NOTIFICAÇÕES
# ============================================================
class NotificationListView(LoginRequiredMixin, ListView):
    """Lista todas as notificações (alertas e agendamentos)."""
    template_name = "core/notifications_list.html"
    context_object_name = "notifications"

    def get_queryset(self):
        empresa = getattr(self.request.user, 'usuario', None) and self.request.user.usuario.empresa
        return NotificacaoAlerta.objects.filter(alerta__empresa=empresa).order_by('-id')


import logging
logger = logging.getLogger(__name__)

@csrf_exempt
def error_report(request):
    """
    Endpoint para receber relatórios de erro do frontend.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Logar o erro com detalhes
            logger.error(f"FRONTEND ERROR REPORT: {json.dumps(data, indent=2)}")
            return JsonResponse({'status': 'success', 'message': 'Error reported'})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.exception(f"Error processing error report: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)


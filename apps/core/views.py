# apps/core/views.py
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear  # ⚠️ Import faltando
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
import json
from decimal import Decimal
from django.urls import reverse_lazy
import json
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.contrib import messages
# Importações dos seus modelos (SOTARQ)
from apps.core.models import AuditoriaAcesso
from apps.core.signals import get_client_ip
from apps.vendas.models import NotaCredito, Venda, FaturaCredito, MetaVenda
from apps.produtos.models import Produto
from apps.empresas.models import Categoria, Empresa
from apps.analytics.models import AuditoriaInvestimento
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import IPConhecido, AuditoriaAcesso, VerificacaoSeguranca
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib import messages
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
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
from apps.analytics.models import AuditoriaInvestimento, EventoAnalytics, NotificacaoAlerta
from apps.empresas.models import Categoria, Empresa
from apps.produtos.models import Produto
from apps.vendas.models import FaturaCredito, MetaVenda, Venda
from apps.servicos.models import NotificacaoAgendamento
from datetime import date, timedelta
import traceback
from django.core.exceptions import PermissionDenied
from django.contrib.auth import logout
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.db import connection
from django.db import connection
from django_tenants.utils import schema_context
from apps.licenca.models import ComissaoBypass




# ============================================================
# BASE VIEW COM CONTEXTO EMPRESARIAL
# ============================================================





class BaseMPAView(TemplateView):
    """
    RIGOR SOTARQ: Base para todas as views MPA. 
    Nota: O LoginRequiredMixin é aplicado nas classes filhas ou aqui.
    """
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
        """Obtém a empresa do utilizador logado com rigor multi-tenant."""
        user = self.request.user
        if not user.is_authenticated:
            return None

        # Busca hierárquica de vínculo empresarial
        empresa = getattr(user, 'empresa', None)
        
        if not empresa and hasattr(user, 'usuario'):
            empresa = getattr(user.usuario, 'empresa', None)
        
        if not empresa and hasattr(user, 'funcionario'):
            empresa = getattr(user.funcionario, 'empresa', None)

        if not empresa and not user.is_superuser:
            raise PermissionDenied("O utilizador não está associado a nenhuma empresa.")

        return empresa






class PlanoBypassView(LoginRequiredMixin, BaseMPAView):
    template_name = 'core/plano_bypass.html'
    module_name = 'plano_bypass' # 👈 Importante para o CSS do botão | Para garantir que ninguém descubra a URL e tente acessá-la (mesmo sem o botão)
    
    def dispatch(self, request, *args, **kwargs):
        # RIGOR SOTARQ: Só o Admin Supremo ou quem tem permissão explícita entra
        if not request.user.is_superuser and not request.user.has_perm('core.pode_ver_bypass'):
            raise PermissionDenied("Acesso restrito ao Administrador do Ecossistema.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresas_elite = Empresa.objects.filter(plano__nome__iexact='Elite Bypass')
        relatorio_geral = []
        total_global_comissao = Decimal('0.00')
        total_faturado_geral = Decimal('0.00')

        for emp in empresas_elite:
            with schema_context(emp.schema_name):
                # 🛡️ RIGOR SOTARQ: Soma faturamento real e subtrai Notas de Crédito (Devoluções)
                vendas = Venda.objects.filter(status='finalizada').aggregate(t=Sum('total'))['t'] or Decimal('0')
                faturas = FaturaCredito.objects.filter(status='liquidada').aggregate(t=Sum('total'))['t'] or Decimal('0')
                devolucoes = NotaCredito.objects.filter(status='emitida').aggregate(t=Sum('total'))['t'] or Decimal('0')
                
                faturamento_liquido = (vendas + faturas) - devolucoes
                comissao = faturamento_liquido * Decimal('0.02')
                
                relatorio_geral.append({
                    'empresa': emp,
                    'faturamento': faturamento_liquido,
                    'nossa_parte': comissao,
                })
                total_global_comissao += comissao
                total_faturado_geral += faturamento_liquido

        context.update({
            'relatorio': relatorio_geral,
            'total_global': total_global_comissao,
            'total_faturado_geral': total_faturado_geral,
        })
        return context

# ============================================================
# DASHBOARD
# ============================================================

# Adicione estes imports no topo do apps/core/views.py

# --- VIEWS DE AUTENTICAÇÃO (Restauração SOTARQ) ---

def logout_view(request):
    """Lógica de encerramento de sessão com limpeza de logs."""
    logout(request)
    messages.success(request, "Sessão encerrada com sucesso. Até breve!")
    return redirect('core:login')



class DashboardView(LoginRequiredMixin, BaseMPAView):
    """
    DASHBOARD ESTRUTURAL: Unifica métricas de vendas, lucro e ativos.
    CORREÇÃO MRO: LoginRequiredMixin vem antes da BaseMPAView.
    """
    template_name = 'core/dashboard.html'
    module_name = 'dashboard'

    def get_vendas_filtradas(self, user, empresa):
        """Filtro de Compliance: Investidores vêem apenas seus ativos."""
        # Se estivermos no schema public, retornamos queryset vazio para evitar o crash
        from django.db import connection
        if connection.schema_name == 'public':
            return Venda.objects.none()
        
        qs = Venda.objects.filter(empresa=empresa, status='finalizada')
        try:
            vinculo = AuditoriaInvestimento.objects.get(usuario=user)
            if not user.is_superuser and not vinculo.pode_auditar_tudo:
                qs = qs.filter(
                    Q(itens__produto__lotes__in=vinculo.lotes_vinculados.all()) |
                    Q(itens__produto__fabricante__in=vinculo.fabricantes_vinculados.all())
                ).distinct()
        except AuditoriaInvestimento.DoesNotExist:
            pass
        return qs

    def get_lucro_investidor(self, vendas_qs):
        """Cálculo de lucro bruto via F() expressions."""
        lucro_data = vendas_qs.aggregate(
            total_lucro=Sum(
                (F('itens__preco_unitario') - F('itens__produto__preco_custo')) * F('itens__quantidade')
            )
        )
        return lucro_data['total_lucro'] or Decimal('0.00')

    # --- MÉTODOS DE GRÁFICOS ---

    def get_vendas_mensais(self, vendas_qs):
        vendas_por_mes = vendas_qs.filter(
            data_venda__gte=timezone.now() - timedelta(days=365)
        ).annotate(mes=TruncMonth('data_venda')).values('mes').annotate(
            faturamento=Sum('total'),
            lucro=Sum((F('itens__preco_unitario') - F('itens__produto__preco_custo')) * F('itens__quantidade'))
        ).order_by('mes')
        
        return {
            'labels': [item['mes'].strftime('%b/%Y') for item in vendas_por_mes],
            'faturamento': [float(item['faturamento'] or 0) for item in vendas_por_mes],
            'lucro': [float(item['lucro'] or 0) for item in vendas_por_mes]
        }

    def get_vendas_semanais(self, vendas_qs):
        vendas_por_semana = vendas_qs.filter(
            data_venda__gte=timezone.now() - timedelta(weeks=8)
        ).annotate(semana=TruncWeek('data_venda')).values('semana').annotate(
            faturamento=Sum('total'),
            lucro=Sum((F('itens__preco_unitario') - F('itens__produto__preco_custo')) * F('itens__quantidade'))
        ).order_by('semana')
        
        return {
            'labels': [item['semana'].strftime('%d/%m') for item in vendas_por_semana],
            'faturamento': [float(item['faturamento'] or 0) for item in vendas_por_semana],
            'lucro': [float(item['lucro'] or 0) for item in vendas_por_semana]
        }

    def get_formas_pagamento(self, vendas_qs):
        inicio_mes = timezone.now().date().replace(day=1)
        vendas_pagamento = vendas_qs.filter(
            data_venda__date__gte=inicio_mes
        ).values('forma_pagamento__nome').annotate(total=Sum('total')).order_by('-total')
        
        dados = {'labels': [], 'valores': []}
        for item in vendas_pagamento:
            if item['total']:
                dados['labels'].append(item['forma_pagamento__nome'] or 'Outros')
                dados['valores'].append(float(item['total']))
        return dados

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db import connection
        
        # RIGOR SOTARQ: Bloqueio de segurança para Schema Public
        if connection.schema_name == 'public':
            context.update({
                'vendas_hoje': {'total': Decimal('0.00'), 'quantidade': 0},
                'lucro_total': Decimal('0.00'),
                'produtos_stats': {'total': 0, 'total_categorias': 0},
                'estoque_stats': {'estoque_baixo': 0},
                'vendas_recentes': [],
                'dados_vendas_mensal': json.dumps({'labels': [], 'faturamento': [], 'lucro': []}),
                'dados_vendas_semanal': json.dumps({'labels': [], 'faturamento': [], 'lucro': []}),
                'dados_formas_pagamento': json.dumps({'labels': [], 'valores': []}),
            })
            return context

        # --- LÓGICA PARA TENANTS (CLIENTES REAIS) ---
        empresa = context['empresa_atual']
        user = self.request.user
        hoje = timezone.now().date()

        vendas_qs = self.get_vendas_filtradas(user, empresa)
        
        # Resumo Financeiro
        v_hoje = vendas_qs.filter(data_venda__date=hoje).aggregate(t=Sum('total'), q=Count('id'))
        
        # Estatísticas de Estoque (Blindadas contra AuditoriaInvestimento)
        produtos_base = Produto.objects.filter(empresa=empresa, ativo=True)
        try:
            # Import dinâmico para evitar falhas de carregamento no boot
            from apps.analytics.models import AuditoriaInvestimento
            vinculo = AuditoriaInvestimento.objects.get(usuario=user)
            if not user.is_superuser and not vinculo.pode_auditar_tudo:
                produtos_base = produtos_base.filter(
                    Q(lotes__in=vinculo.lotes_vinculados.all()) |
                    Q(fabricante__in=vinculo.fabricantes_vinculados.all())
                ).distinct()
        except (ImportError, Exception):
            pass

        context.update({
            'vendas_hoje': {'total': v_hoje['t'] or Decimal('0.00'), 'quantidade': v_hoje['q'] or 0},
            'lucro_total': self.get_lucro_investidor(vendas_qs),
            'produtos_stats': {
                'total': produtos_base.count(),
                'total_categorias': Categoria.objects.filter(empresa=empresa, ativa=True).count(),
            },
            'estoque_stats': {
                'estoque_baixo': produtos_base.filter(estoque_atual__lte=F('estoque_minimo')).count()
            },
            'vendas_recentes': vendas_qs.select_related('cliente').order_by('-data_venda')[:10],
            'dados_vendas_mensal': json.dumps(self.get_vendas_mensais(vendas_qs)),
            'dados_vendas_semanal': json.dumps(self.get_vendas_semanais(vendas_qs)),
            'dados_formas_pagamento': json.dumps(self.get_formas_pagamento(vendas_qs)),
        })
        return context



class SecurityHistoryView(LoginRequiredMixin, BaseMPAView):
    """
    RIGOR SOTARQ: Exibe o histórico de segurança e acessos do utilizador.
    """
    template_name = 'core/security_history.html'
    module_name = 'security'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pegamos os últimos 20 acessos para não sobrecarregar a página
        context['logs'] = AuditoriaAcesso.objects.filter(
            usuario=self.request.user
        ).order_by('-timestamp')[:20]
        return context
    


@receiver(user_logged_in)
def verificar_seguranca_ip(sender, request, user, **kwargs):
    ip_atual = get_client_ip(request)
    
    # 1. Registrar a auditoria (já existente)
    AuditoriaAcesso.objects.create(
        usuario=user,
        acao='LOGIN',
        ip_address=ip_atual,
        user_agent=request.META.get('HTTP_USER_AGENT')
    )

    # 2. Verificar se o IP é novo
    ip_existe = IPConhecido.objects.filter(usuario=user, ip_address=ip_atual).exists()

    if not ip_existe:
        # Registrar como novo IP conhecido para o futuro
        IPConhecido.objects.create(usuario=user, ip_address=ip_atual)
        
        # Enviar e-mail de alerta (Apenas se não for o primeiro login da história do user)
        if AuditoriaAcesso.objects.filter(usuario=user, acao='LOGIN').count() > 1:
            enviar_alerta_ip_novo(user, ip_atual, request.META.get('HTTP_USER_AGENT'))

def enviar_alerta_ip_novo(user, ip, ua):
    context = {
        'user': user,
        'ip': ip,
        'ua': ua,
        'sistema': 'VistoGEST'
    }
    html_content = render_to_string('emails/alerta_seguranca_ip.html', context)
    
    send_mail(
        subject="Alerta de Segurança: Novo acesso detectado",
        message=f"Um novo acesso foi realizado na sua conta VistoGEST a partir do IP {ip}.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_content
    )



class TerminarOutrasSessoesView(LoginRequiredMixin, View):
    """
    RIGOR SOTARQ: Invalida todas as sessões do utilizador, exceto a atual.
    """
    def post(self, request):
        chave_sessao_atual = request.session.session_key
        # Busca todas as sessões ativas no banco
        sessoes = Session.objects.filter(expire_date__gte=timezone.now())
        
        contagem_removida = 0
        for sessao in sessoes:
            dados = sessao.get_decoded()
            # Verifica se a sessão pertence ao utilizador logado e não é a atual
            if dados.get('_auth_user_id') == str(request.user.id):
                if sessao.session_key != chave_sessao_atual:
                    sessao.delete()
                    contagem_removida += 1
        
        messages.success(request, f"Sucesso! {contagem_removida} dispositivos remotos foram desconectados.")
        return redirect('core:security_history')



# ============================================================
# SEGURANÇA: VERIFICAÇÃO DE DISPOSITIVO (2FA POR IP)
# ============================================================

class VerifyIPView(LoginRequiredMixin, View):
    """
    RIGOR SOTARQ: Desafia o utilizador com um token de 6 dígitos
    sempre que um novo IP é detetado.
    """
    template_name = 'registration/verify_ip.html'

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')


    def get(self, request):
        from django.db import connection
        from django.contrib.auth import logout
        
        user = request.user
        ip_atual = self.get_client_ip(request)
        agora = timezone.now()

        # 1. RIGOR SOTARQ: Blindagem de Isolamento Tenant
        # Superusers podem transitar, mas usuários comuns ficam presos à sua empresa
        if not user.is_superuser:
            if not user.empresa or user.empresa != request.tenant:
                if settings.DEBUG:
                    print(f"⚠️ BLOQUEIO DE SEGURANÇA: Usuário {user.email} tentou invadir o schema {connection.schema_name}")
                logout(request)
                messages.error(request, "Acesso negado: Este utilizador não pertence a esta empresa.")
                return redirect('core:login')

        # 2. AUDITORIA NO TERMINAL (Apenas em Debug)
        if settings.DEBUG:
            print("\n" + "!"*60)
            print(f"🕵️ AUDITORIA DE ACESSO 2FA")
            print(f"🏢 SCHEMA: {connection.schema_name}")
            print(f"👤 USUÁRIO: {user.email}")
            print(f"🌐 IP: {ip_atual}")
            print("!"*60 + "\n")

        # 3. RECUPERAR OU CRIAR VERIFICAÇÃO
        verificacao, created = VerificacaoSeguranca.objects.get_or_create(
            usuario=user, 
            ip_address=ip_atual,
            foi_verificado=False,
            defaults={'expira_em': agora + timezone.timedelta(minutes=10)}
        )

        # 4. LÓGICA DE REENVIO COM RATE LIMIT (Trava de 60 segundos)
        if request.GET.get('action') == 'resend':
            segundos_desde_ultimo = (agora - verificacao.criado_em).total_seconds()
            
            if segundos_desde_ultimo < 60:
                segundos_restantes = int(60 - segundos_desde_ultimo)
                messages.warning(
                    request, 
                    f"Aguarde mais {segundos_restantes} segundos antes de solicitar um novo código."
                )
                return render(request, self.template_name, {'email': user.email})
            
            # Se autorizado, gera novo token
            messages.info(request, "Um novo código foi gerado e enviado para o seu e-mail.")
            verificacao.criado_em = agora 
            verificacao.save() # Força atualização do timestamp para resetar a trava

        # 5. DISPARO DO TOKEN
        token = verificacao.gerar_token()
        self.enviar_email_token(user, token, ip_atual)
        
        return render(request, self.template_name, {'email': user.email})


    def post(self, request):
        token_inserido = request.POST.get('token')
        ip_atual = self.get_client_ip(request)
        
        verificacao = VerificacaoSeguranca.objects.filter(
            usuario=request.user, 
            ip_address=ip_atual,
            foi_verificado=False
        ).last()

        if verificacao and verificacao.esta_valido() and verificacao.token == token_inserido:
            verificacao.foi_verificado = True
            verificacao.save()
            
            # Autoriza o IP permanentemente
            IPConhecido.objects.get_or_create(usuario=request.user, ip_address=ip_atual)
            
            messages.success(request, "Dispositivo autorizado com sucesso!")
            return redirect('core:dashboard')
        
        messages.error(request, "Código inválido ou expirado. Um novo código foi enviado para o seu e-mail.")
        return self.get(request)

    def enviar_email_token(self, user, token, ip):
        """Envia o e-mail de 2FA com Rigor Visual e Segurança Multi-ambiente."""
        
        # ✅ RIGOR SOTARQ: Debug visível apenas no Windows/Dev
        if settings.DEBUG:
            print("\n" + "="*50)
            print(f"🛠️ [SOTARQ DEBUG] 2FA PARA: {user.email}")
            print(f"🔑 TOKEN: {token}")
            print(f"🌐 IP: {ip}")
            print("="*50 + "\n")

        assunto = f"Código de Verificação: {token} | VistoGEST"
        contexto = {
            'user': user,
            'token': token,
            'ip': ip,
            'expire': 10
        }
        
        html_message = render_to_string('emails/token_2fa_email.html', contexto)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=assunto,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
      

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
            user = request.user
            empresa = getattr(user, 'empresa', Empresa.objects.first()) # Fallback seguro
            nome = request.POST.get('nome', '').strip()
            
            if not nome:
                return JsonResponse({'success': False, 'message': 'Nome é obrigatório'})
            
            categoria = Categoria.objects.create(
                empresa=empresa, 
                nome=nome, 
                codigo=request.POST.get('codigo', ''),
                descricao=request.POST.get('descricao', ''),
                ativa=request.POST.get('ativa') == 'on'
            )
            return JsonResponse({'success': True, 'message': 'Criada com sucesso'})
        except Exception as e:
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
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.error(f"FRONTEND ERROR: {json.dumps(data, indent=2)}")
            return JsonResponse({'status': 'success'})
        except:
            return JsonResponse({'status': 'error'}, status=400)
    return JsonResponse({'status': 'error'}, status=405)


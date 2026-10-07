# apps/core_tenants/views.py
"""
Views de tenant (schemas de empresa). Mapeadas 1:1 a partir de
apps/core/views.py conforme PLANO_CORE_TENANT.md, secção 3.1.

Namespace de URL: 'core_tenants' (NÃO 'core' — decisão final confirmada
pelo dono do sistema, substituindo a ideia anterior de manter app_name='core'
em core_tenants/urls.py).
"""
from datetime import timedelta
from decimal import Decimal
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import connection
from django.db.models import F, Q, Count, Sum
from django.db.models.functions import TruncWeek, TruncMonth
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.models import AuditoriaAcesso, IPConhecido, VerificacaoSeguranca
from apps.analytics.models import AuditoriaInvestimento, NotificacaoAlerta
from apps.produtos.models import Categoria, Produto
from apps.servicos.models import NotificacaoAgendamento
from apps.vendas.models import Venda

logger = logging.getLogger('core_tenants.security')


# ============================================================
# BASE VIEW COM CONTEXTO EMPRESARIAL (tenant)
# ============================================================

class BaseMPAView(TemplateView):
    """
    RIGOR SOTARQ: base para todas as views MPA de tenant.
    Alinhada ao padrão django_tenants (isolamento físico via schema PostgreSQL).
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        context.update({
            'user': self.request.user,
            'current_module': getattr(self, 'module_name', 'dashboard'),
            'empresa_atual': empresa,
        })
        return context

    def get_empresa(self):
        """Retorna o Tenant (Empresa) activo associado ao schema da requisição actual."""
        tenant = getattr(self.request, 'tenant', None) or getattr(connection, 'tenant', None)

        if not tenant or getattr(tenant, 'schema_name', 'public') == 'public':
            if getattr(self, 'exigir_empresa', False):
                raise PermissionDenied("Acção permitida apenas no contexto de uma empresa/tenant activo.")
            return None

        return tenant


# ============================================================
# DASHBOARD
# ============================================================


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
        
        qs = Venda.objects.filter(status='finalizada')
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
        produtos_base = Produto.objects.filter(ativo=True)
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
                'total_categorias': Categoria.objects.filter(ativa=True).count(),
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



class DashboardStatsAPI(LoginRequiredMixin, View):
    """AJAX de estatísticas do dashboard (stub — preencher quando necessário)."""

    def get(self, request):
        return JsonResponse({'success': True, 'stats': {}})


# ============================================================
# SEGURANÇA — histórico, sessões, 2FA por IP
# ============================================================

class SecurityHistoryView(LoginRequiredMixin, BaseMPAView):
    """RIGOR SOTARQ: exibe o histórico de segurança e acessos do utilizador."""
    template_name = 'core/security_history.html'
    module_name = 'security'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['logs'] = AuditoriaAcesso.objects.filter(
            usuario=self.request.user
        ).order_by('-timestamp')[:20]
        return context


class TerminarOutrasSessoesView(LoginRequiredMixin, View):
    """RIGOR SOTARQ: invalida todas as sessões do utilizador, excepto a actual."""

    def post(self, request):
        chave_sessao_atual = request.session.session_key
        sessoes = Session.objects.filter(expire_date__gte=timezone.now())

        contagem_removida = 0
        for sessao in sessoes:
            dados = sessao.get_decoded()
            if dados.get('_auth_user_id') == str(request.user.id):
                if sessao.session_key != chave_sessao_atual:
                    sessao.delete()
                    contagem_removida += 1

        messages.success(request, f"Sucesso! {contagem_removida} dispositivos remotos foram desconectados.")
        return redirect('core_tenants:security_history')


class VerifyIPView(LoginRequiredMixin, View):
    """
    RIGOR SOTARQ: desafia o utilizador com um token de 6 dígitos sempre que
    um novo IP é detectado. É uma view de TENANT — o login em si (schema
    public) continua em apps.core.views.CustomLoginView.
    """
    template_name = 'registration/verify_ip.html'

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

    def get(self, request):
        user = request.user
        ip_atual = self.get_client_ip(request)
        agora = timezone.now()

        # Blindagem de isolamento físico: utilizadores comuns não podem
        # validar 2FA no schema public (área global, sem tenant).
        if not user.is_superuser:
            if getattr(connection, 'schema_name', 'public') == 'public':
                if settings.DEBUG:
                    print(f"⚠️ BLOQUEIO DE SEGURANÇA: Utilizador {user.email} tentou aceder à validação 2FA no schema public")
                logout(request)
                messages.error(request, "Acesso negado: Esta operação deve ser realizada no domínio da sua empresa.")
                return redirect('core:login')

        if settings.DEBUG:
            print("\n" + "!" * 60)
            print("🕵️ AUDITORIA DE ACESSO 2FA")
            print(f"🏢 SCHEMA ATIVO: {connection.schema_name}")
            print(f"👤 UTILIZADOR: {user.email}")
            print(f"🌐 IP: {ip_atual}")
            print("!" * 60 + "\n")

        verificacao, created = VerificacaoSeguranca.objects.get_or_create(
            usuario=user,
            ip_address=ip_atual,
            foi_verificado=False,
            defaults={'expira_em': agora + timezone.timedelta(minutes=10)}
        )

        if request.GET.get('action') == 'resend':
            segundos_desde_ultimo = (agora - verificacao.criado_em).total_seconds()

            if segundos_desde_ultimo < 60:
                segundos_restantes = int(60 - segundos_desde_ultimo)
                messages.warning(
                    request,
                    f"Aguarde mais {segundos_restantes} segundos antes de solicitar um novo código."
                )
                return render(request, self.template_name, {'email': user.email})

            messages.info(request, "Um novo código foi gerado e enviado para o seu e-mail.")
            verificacao.criado_em = agora
            verificacao.save()

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

            IPConhecido.objects.get_or_create(usuario=request.user, ip_address=ip_atual)

            messages.success(request, "Dispositivo autorizado com sucesso!")
            return redirect('core_tenants:dashboard')

        messages.error(request, "Código inválido ou expirado. Um novo código foi enviado para o seu e-mail.")
        return self.get(request)

    def enviar_email_token(self, user, token, ip):
        """Envia o e-mail de 2FA."""
        if settings.DEBUG:
            print("\n" + "=" * 50)
            print(f"🛠️ [SOTARQ DEBUG] 2FA PARA: {user.email}")
            print(f"🔑 TOKEN: {token}")
            print(f"🌐 IP: {ip}")
            print("=" * 50 + "\n")

        assunto = f"Código de Verificação: {token} | VistoGEST"
        contexto = {'user': user, 'token': token, 'ip': ip, 'expire': 10}

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
# NOTIFICAÇÕES
# ============================================================

class NotificationListView(LoginRequiredMixin, ListView):
    """Lista todas as notificações do utilizador autenticado."""
    template_name = "core/notifications_list.html"
    context_object_name = "notifications"

    def get_queryset(self):
        return (
            NotificacaoAlerta.objects
            .filter(usuario=self.request.user)
            .select_related('alerta')
            .order_by('-alerta__created_at')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = (
            NotificacaoAlerta.objects
            .filter(usuario=self.request.user, lida=False)
            .count()
        )
        return ctx


class NotificacaoMarcarLidaView(LoginRequiredMixin, View):
    """AJAX — marca uma NotificacaoAlerta como lida."""

    def post(self, request, pk):
        try:
            notif = NotificacaoAlerta.objects.get(pk=pk, usuario=request.user)
            if not notif.lida:
                notif.lida = True
                notif.lida_em = timezone.now()
                notif.save(update_fields=['lida', 'lida_em'])
            return JsonResponse({'ok': True})
        except NotificacaoAlerta.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'not found'}, status=404)


class NotificacaoMarcarTodasLidasView(LoginRequiredMixin, View):
    """AJAX — marca todas as notificações do utilizador como lidas."""

    def post(self, request):
        agora = timezone.now()
        updated = (
            NotificacaoAlerta.objects
            .filter(usuario=request.user, lida=False)
            .update(lida=True, lida_em=agora)
        )
        return JsonResponse({'ok': True, 'updated': updated})


class NotificacaoCountAjaxView(LoginRequiredMixin, View):
    """
    AJAX polling — devolve o count de notificações não lidas para o utilizador.

    Combina três fontes:
      1. NotificacaoAlerta (analytics) — alertas inteligentes por utilizador
      2. NotificacaoAgendamento (servicos) — agendamentos pendentes
      3. AlertaProdutoExpiracao (produtos) — produtos a expirar não enviados

    Só tem sentido no schema de tenant (onde existem os modelos acima) —
    daí viver em core_tenants e não em core.
    """

    def get(self, request):
        from apps.produtos.models import AlertaProdutoExpiracao

        count = 0
        notifs = []

        try:
            analytics_notifs = (
                NotificacaoAlerta.objects
                .filter(usuario=request.user, lida=False)
                .select_related('alerta')[:10]
            )
            for n in analytics_notifs:
                alerta = n.alerta
                if alerta:
                    notifs.append({
                        'id': n.pk,
                        'title': alerta.titulo,
                        'message': alerta.mensagem[:80],
                        'url': f'/analytics/alertas/{alerta.pk}/',
                        'icon': _icon_for_alerta(alerta.tipo),
                        'type': _color_for_prioridade(alerta.prioridade),
                        'created_at': alerta.created_at.isoformat(),
                        'source': 'alerta',
                    })
            count += analytics_notifs.count()
        except Exception:
            pass

        try:
            agend_notifs = (
                NotificacaoAgendamento.objects
                .filter(status='pendente')
                .order_by('-data_agendada_envio')[:5]
            )
            for n in agend_notifs:
                notifs.append({
                    'id': None,
                    'title': f"{n.get_tipo_notificacao_display()} — {n.cliente.nome_completo}",
                    'message': (n.mensagem or '')[:80],
                    'url': f'/notificacoes/{n.id}/editar/',
                    'icon': 'bell',
                    'type': 'blue',
                    'created_at': n.created_at.isoformat(),
                    'source': 'agendamento',
                })
            count += agend_notifs.count()
        except Exception:
            pass

        try:
            alertas_exp = (
                AlertaProdutoExpiracao.objects
                .filter(enviado=False)
                .order_by('-created_at')[:5]
            )
            for a in alertas_exp:
                dias = (a.lote.data_validade - timezone.now().date()).days
                notifs.append({
                    'id': None,
                    'title': 'Produto prestes a expirar',
                    'message': f"{a.lote.produto.nome_comercial} vence em {dias} dias",
                    'url': f'/produtos/lotes/{a.lote.id}/',
                    'icon': 'exclamation-triangle',
                    'type': 'red',
                    'created_at': a.created_at.isoformat(),
                    'source': 'expiracao',
                })
            count += alertas_exp.count()
        except Exception:
            pass

        notifs.sort(key=lambda x: x['created_at'], reverse=True)

        return JsonResponse({
            'count': count,
            'notifications': notifs[:5],
        })


def _icon_for_alerta(tipo):
    return {
        'estoque_baixo': 'boxes',
        'vendas_baixas': 'chart-line',
        'erro_sistema': 'exclamation-circle',
        'performance': 'tachometer-alt',
        'seguranca': 'shield-alt',
        'financeiro': 'money-bill-wave',
    }.get(tipo, 'info-circle')


def _color_for_prioridade(prioridade):
    return {
        'baixa': 'green',
        'media': 'yellow',
        'alta': 'orange',
        'critica': 'red',
    }.get(prioridade, 'blue')
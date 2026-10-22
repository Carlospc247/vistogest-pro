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
from apps.vendas.models import ItemVenda, Venda
from apps.vendas.dashboard_data import dados_analise_vendas, lucro_total


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
    Dashboard executivo: vendas, lucro e ativos.
    Regras de consistência:
      - Todos os valores monetários saem de `vendas_qs`, que nunca faz JOIN
        com itens (o filtro de investidor usa pk__in com subquery).
      - Lucro do cartão e do gráfico usam a mesma fórmula (dashboard_data).
      - Datas em hora local (timezone.localdate), não em UTC.
      - O contexto envia dicts Python; o template serializa com json_script.
    """
    template_name = 'core/dashboard.html'
    module_name = 'dashboard'

    # ------------------------------------------------------------------
    # Filtros de compliance (investidores)
    # ------------------------------------------------------------------

    def _vinculo_restrito(self, user):
        """Devolve o vínculo de auditoria se o utilizador estiver limitado
        aos seus ativos; None se tiver acesso total."""
        if user.is_superuser:
            return None
        from apps.analytics.models import AuditoriaInvestimento
        vinculo = AuditoriaInvestimento.objects.filter(usuario=user).first()
        if vinculo is None or vinculo.pode_auditar_tudo:
            return None
        return vinculo

    def get_vendas_filtradas(self, user, empresa=None):
        """Queryset de vendas finalizadas, SEM joins (seguro para Sum/Count)."""
        if connection.schema_name == 'public':
            return Venda.objects.none()

        base = Venda.objects.filter(status='finalizada')
        vinculo = self._vinculo_restrito(user)
        if vinculo is None:
            return base

        ids = (ItemVenda.objects
               .filter(venda__status='finalizada')
               .filter(Q(produto__lotes__in=vinculo.lotes_vinculados.all()) |
                       Q(produto__fabricante__in=vinculo.fabricantes_vinculados.all()))
               .values('venda_id'))
        return base.filter(pk__in=ids)

    def get_produtos_base(self, user):
        base = Produto.objects.filter(ativo=True)
        vinculo = self._vinculo_restrito(user)
        if vinculo is None:
            return base

        ids = (Produto.objects
               .filter(Q(lotes__in=vinculo.lotes_vinculados.all()) |
                       Q(fabricante__in=vinculo.fabricantes_vinculados.all()))
               .values('pk'))
        return base.filter(pk__in=ids)

    # ------------------------------------------------------------------
    # Métricas
    # ------------------------------------------------------------------

    def get_lucro_investidor(self, vendas_qs):
        return lucro_total(vendas_qs)

    def get_formas_pagamento(self, vendas_qs):
        inicio_mes = timezone.localdate().replace(day=1)
        qs = (vendas_qs
              .filter(data_venda__date__gte=inicio_mes)
              .values('forma_pagamento__nome')
              .annotate(total=Sum('total'))
              .order_by('-total'))

        dados = {'labels': [], 'valores': []}
        for item in qs:
            if item['total']:
                dados['labels'].append(item['forma_pagamento__nome'] or 'Outros')
                dados['valores'].append(float(item['total']))
        return dados

    def get_metas(self, vendas_qs, hoje):
        """Metas de faturamento activas hoje vs realizado (sem JOIN com itens)."""
        from apps.vendas.models import MetaVenda

        metas = (MetaVenda.objects
                 .filter(status='ativa', meta_faturamento__isnull=False,
                         data_inicio__lte=hoje, data_fim__gte=hoje)
                 .order_by('data_inicio')[:6])

        dados = {'labels': [], 'metas': [], 'realizados': []}
        for m in metas:
            qs = vendas_qs.filter(data_venda__date__gte=m.data_inicio,
                                  data_venda__date__lte=m.data_fim)
            if m.vendedor_id:
                qs = qs.filter(vendedor_id=m.vendedor_id)
            realizado = qs.aggregate(t=Sum('total'))['t'] or Decimal('0.00')

            dados['labels'].append(m.nome)
            dados['metas'].append(float(m.meta_faturamento))
            dados['realizados'].append(float(realizado))
        return dados

    def get_top_vendedores(self, vendas_qs):
        inicio_mes = timezone.localdate().replace(day=1)
        return list(
            vendas_qs
            .filter(data_venda__date__gte=inicio_mes, vendedor__isnull=False)
            .values('vendedor__nome_completo')
            .annotate(total_vendas=Count('id'), total_faturamento=Sum('total'))
            .order_by('-total_faturamento')[:5]
        )

    # ------------------------------------------------------------------
    # Contexto
    # ------------------------------------------------------------------

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Schema public: tudo vazio, mas com a estrutura completa
        if connection.schema_name == 'public':
            context.update({
                'vendas_hoje': {'total': Decimal('0.00'), 'quantidade': 0},
                'lucro_total': Decimal('0.00'),
                'produtos_stats': {'total': 0, 'total_categorias': 0},
                'estoque_stats': {'estoque_baixo': 0},
                'vendas_recentes': [],
                'top_vendedores': [],
                'dados_vendas': dados_analise_vendas(Venda.objects.none()),
                'dados_formas_pagamento': {'labels': [], 'valores': []},
                'dados_metas': {'labels': [], 'metas': [], 'realizados': []},
            })
            return context

        user = self.request.user
        hoje = timezone.localdate()

        vendas_qs = self.get_vendas_filtradas(user, context.get('empresa_atual'))
        produtos_base = self.get_produtos_base(user)

        v_hoje = vendas_qs.filter(data_venda__date=hoje).aggregate(
            t=Sum('total'), q=Count('id'))

        context.update({
            'vendas_hoje': {
                'total': v_hoje['t'] or Decimal('0.00'),
                'quantidade': v_hoje['q'] or 0,
            },
            'lucro_total': self.get_lucro_investidor(vendas_qs),
            'produtos_stats': {
                'total': produtos_base.count(),
                'total_categorias': Categoria.objects.filter(ativa=True).count(),
            },
            'estoque_stats': {
                'estoque_baixo': produtos_base.filter(
                    estoque_atual__lte=F('estoque_minimo')).count(),
            },
            'vendas_recentes': (vendas_qs.select_related('cliente')
                                .order_by('-data_venda')[:10]),
            'top_vendedores': self.get_top_vendedores(vendas_qs),
            'dados_vendas': dados_analise_vendas(vendas_qs),
            'dados_formas_pagamento': self.get_formas_pagamento(vendas_qs),
            'dados_metas': self.get_metas(vendas_qs, hoje),
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
    template_name = "core_tenants/notifications_list.html"
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


import logging
from django.db import connection, transaction

log = logging.getLogger('core_tenants.notifications')


class NotificacaoCountAjaxView(LoginRequiredMixin, View):
    """Polling de notificações (alertas + agendamentos + expiração)."""

    def handle_no_permission(self):
        return JsonResponse({'count': 0, 'notifications': [], 'auth': False}, status=401)

    def get(self, request):
        if connection.schema_name == 'public':
            return JsonResponse({'count': 0, 'notifications': []})

        from apps.produtos.models import AlertaProdutoExpiracao

        count, notifs = 0, []

        try:
            with transaction.atomic():
                qs = (NotificacaoAlerta.objects
                      .filter(usuario=request.user, lida=False)
                      .select_related('alerta'))
                count += qs.count()
                for n in qs.order_by('-alerta__created_at')[:5]:
                    a = n.alerta
                    if a:
                        notifs.append({
                            'id': n.pk, 'title': a.titulo, 'message': a.mensagem[:80],
                            'url': f'/analytics/alertas/{a.pk}/',
                            'icon': _icon_for_alerta(a.tipo),
                            'type': _color_for_prioridade(a.prioridade),
                            'created_at': a.created_at.isoformat(), 'source': 'alerta',
                        })
        except Exception:
            log.exception('Falha na fonte: alertas')

        try:
            with transaction.atomic():
                qs = NotificacaoAgendamento.objects.filter(status='pendente')
                count += qs.count()
                for n in qs.select_related('cliente').order_by('-data_agendada_envio')[:5]:
                    notifs.append({
                        'id': None,
                        'title': f"{n.get_tipo_notificacao_display()} — {n.cliente.nome_completo}",
                        'message': (n.mensagem or '')[:80],
                        'url': f'/notificacoes/{n.id}/editar/',
                        'icon': 'bell', 'type': 'blue',
                        'created_at': n.created_at.isoformat(), 'source': 'agendamento',
                    })
        except Exception:
            log.exception('Falha na fonte: agendamentos')

        try:
            with transaction.atomic():
                qs = AlertaProdutoExpiracao.objects.filter(enviado=False)
                count += qs.count()
                hoje = timezone.localdate()
                for a in qs.select_related('lote__produto').order_by('-created_at')[:5]:
                    dias = (a.lote.data_validade - hoje).days
                    notifs.append({
                        'id': None, 'title': 'Produto prestes a expirar',
                        'message': f"{a.lote.produto.nome_comercial} vence em {dias} dias",
                        'url': f'/produtos/lotes/{a.lote.id}/',
                        'icon': 'exclamation-triangle', 'type': 'red',
                        'created_at': a.created_at.isoformat(), 'source': 'expiracao',
                    })
        except Exception:
            log.exception('Falha na fonte: expiração')

        notifs.sort(key=lambda x: x['created_at'], reverse=True)
        return JsonResponse({'count': count, 'notifications': notifs[:5]})



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



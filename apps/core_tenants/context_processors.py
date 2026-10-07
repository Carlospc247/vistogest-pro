# apps/core_tenants/context_processors.py
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from apps.produtos.models import AlertaProdutoExpiracao, Lote
from apps.servicos.models import NotificacaoAgendamento
from apps.vendas.models import Venda


def dashboard_data(request):
    """Context processor para dados globais do dashboard (só faz sentido em tenant)."""
    if connection.schema_name == 'public':
        return {}

    if not request.user.is_authenticated or not hasattr(request.user, 'funcionario') or not request.user.funcionario:
        return {}

    hoje = timezone.now().date()
    notificacoes = []

    vencendo_hoje = Lote.objects.filter(
        produto__ativo=True,
        data_validade=hoje,
        quantidade_atual__gt=0
    ).count()

    if vencendo_hoje > 0:
        notificacoes.append({
            'tipo': 'warning',
            'mensagem': f'{vencendo_hoje} produto(s) vencem hoje!',
            'url': '/produtos/vencimentos/'
        })

    uma_hora_atras = timezone.now() - timedelta(hours=1)
    vendas_pendentes = Venda.objects.filter(
        status='aguardando_pagamento',
        created_at__lt=uma_hora_atras
    ).count()

    if vendas_pendentes > 0:
        notificacoes.append({
            'tipo': 'info',
            'mensagem': f'{vendas_pendentes} venda(s) aguardando pagamento',
            'url': '/vendas/pendentes/'
        })

    return {
        'notificacoes_globais': notificacoes,
        'count_notificacoes': len(notificacoes)
    }


def notifications_context(request):
    """Idem — só faz sentido em tenant, onde existem NotificacaoAgendamento/AlertaProdutoExpiracao."""
    if connection.schema_name == 'public':
        return {}

    user = request.user
    notifications = []

    if hasattr(user, 'funcionario') and user.funcionario:
        agend_notifs = NotificacaoAgendamento.objects.filter(
            status='pendente'
        ).order_by('-data_agendada_envio')[:10]

        for n in agend_notifs:
            notifications.append({
                'title': f"{n.get_tipo_notificacao_display()} - {n.cliente.nome_completo}",
                'message': n.mensagem,
                'url': f"/notificacoes/{n.id}/editar/",
                'icon': 'bell',
                'type': 'blue',
                'created_at': n.created_at,
            })

        alertas = AlertaProdutoExpiracao.objects.filter(
            enviado=False
        ).order_by('-created_at')[:20]

        for a in alertas:
            dias = (a.lote.data_validade - timezone.now().date()).days
            notifications.append({
                'title': "Produto prestes a expirar",
                'message': f"{a.lote.produto.nome_comercial} - Lote {a.lote.numero_lote} vence em {dias} dias",
                'url': f"/produtos/lotes/{a.lote.id}/",
                'icon': 'exclamation-triangle',
                'type': 'red',
                'created_at': a.created_at,
            })

    return {
        'notifications': notifications,
        'notifications_count': len(notifications)
    }


def modules_context(request):
    """Idem — módulos activos da licença do tenant."""
    if connection.schema_name == 'public':
        return {}

    if not request.user.is_authenticated or not hasattr(request.user, 'funcionario') or not request.user.funcionario:
        return {}

    empresa_atual = getattr(request, 'tenant', None)
    licenca = getattr(empresa_atual, "licenca", None)
    modulos_ativos = []

    if licenca:
        modulos_ativos = list(licenca.plano.modulos.filter(ativo=True).values_list('slug', flat=True))

    return {
        "modulos_ativos": modulos_ativos
    }
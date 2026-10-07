# apps/core/context_processors.py
from django.utils import timezone
from datetime import timedelta
from apps.servicos.models import NotificacaoAgendamento
from apps.vendas.models import Venda
from apps.produtos.models import Lote


def dashboard_data(request):
    """Context processor para dados globais do dashboard"""
    if not request.user.is_authenticated or not hasattr(request.user, 'funcionario') or not request.user.funcionario:
        return {}
 
    empresa = getattr(connection, 'tenant', None)
    if not empresa:
        return {}

    hoje = timezone.now().date()

    # Notificações rápidas
    notificacoes = []

    # Produtos vencendo hoje
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

    # Vendas sem pagamento há mais de 1 hora
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


from apps.produtos.models import AlertaProdutoExpiracao


def notifications_context(request):
    user = request.user
    notifications = []

    if not user.is_authenticated:
        return {
            'notifications': [],
            'notifications_count': 0,
        }

    # Tenant/empresa atual definido pelo domínio da requisição
    empresa_atual = getattr(request, 'tenant', None)

    if not empresa_atual or getattr(empresa_atual, 'schema_name', 'public') == 'public':
        return {
            'notifications': [],
            'notifications_count': 0,
        }

    # Notificações de agendamentos
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

    # Alertas de produtos prestes a vencer
    alertas = AlertaProdutoExpiracao.objects.filter(
        enviado=False
    ).order_by('-created_at')[:20]

    for a in alertas:
        dias = (a.lote.data_validade - timezone.now().date()).days

        notifications.append({
            'title': "Produto prestes a expirar",
            'message': (
                f"{a.lote.produto.nome_comercial} - "
                f"Lote {a.lote.numero_lote} vence em {dias} dias"
            ),
            'url': f"/produtos/lotes/{a.lote.id}/",
            'icon': 'exclamation-triangle',
            'type': 'red',
            'created_at': a.created_at,
        })

    return {
        'notifications': notifications,
        'notifications_count': len(notifications),
    }


def modules_context(request):
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


from django.db import connection


# apps/core/context_processors.py — versão final, só isto:
from django.db import connection


def regime_context(request):
    """Atalhos globais para controle de interface por regime e schema."""
    if not request.user.is_authenticated:
        return {}

    empresa_atual = getattr(request, 'tenant', None)
    tipo_actividade = getattr(empresa_atual, 'regime', 'MISTO')
    regime_fiscal = getattr(empresa_atual, 'regime_fiscal', 'GERAL')

    return {
        'IS_PUBLIC': connection.schema_name == 'public',
        'IS_COMERCIO': tipo_actividade == 'COMERCIO',
        'IS_SERVICOS': tipo_actividade == 'SERVICOS',
        'IS_MISTO':    tipo_actividade == 'MISTO',
        'PODE_VENDER_PRODUTOS': tipo_actividade in ('COMERCIO', 'MISTO'),
        'PODE_VENDER_SERVICOS': tipo_actividade in ('SERVICOS', 'MISTO'),
        'REGIME_FISCAL':          regime_fiscal,
        'IS_REGIME_GERAL':        regime_fiscal == 'GERAL',
        'IS_REGIME_SIMPLIFICADO': regime_fiscal == 'SIMPLIFICADO',
        'IS_REGIME_EXCLUSAO':     regime_fiscal == 'EXCLUSAO',
        'IS_REGIME_ESPECIAL':     regime_fiscal == 'ESPECIAL',
    }
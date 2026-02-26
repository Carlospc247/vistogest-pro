# apps/vendas/tasks.py (NOVO ARQUIVO)
from celery import shared_task
from django.db.models import F, Sum, DecimalField
from datetime import timedelta
from django.utils import timezone
from apps.produtos.models import Produto # Ajuste o caminho
from apps.vendas.models import ItemVenda
# from apps.users.utils import enviar_email_alerta # Importe sua função de e-mail

@shared_task
def verificar_margem_critica():
    """
    Tarefa Celery para verificar produtos com margem de lucro abaixo do limite.
    Executada periodicamente (e.g., diariamente).
    """
    LIMITE_MARGEM_CRITICA = 0.10  # 10%
    DIAS_ANALISE = 7 # Analisar os últimos 7 dias

    data_limite = timezone.now() - timedelta(days=DIAS_ANALISE)
    
    # 1. Calcular a Margem Agregada nos últimos 7 dias
    margens = ItemVenda.objects.filter(
        venda__data_venda__gte=data_limite
    ).select_related('produto').values(
        'produto__id', 'produto__nome'
    ).annotate(
        receita_total=Sum(F('quantidade') * F('preco_unitario')),
        custo_total=Sum(F('quantidade') * F('produto__custo_unitario')),
    ).annotate(
        margem_bruta=(F('receita_total') - F('custo_total')) / F('receita_total', output_field=DecimalField())
    )

    alertas = []
    
    # 2. Identificar Alertas Críticos
    for item in margens:
        if item['margem_bruta'] is not None and item['margem_bruta'] < LIMITE_MARGEM_CRITICA:
            alertas.append({
                'produto': item['produto__nome'],
                'percentual_margem': f"{item['margem_bruta'] * 100:.2f}%"
            })

    # 3. Disparar Notificação
    if alertas:
        assunto = "⚠️ ALERTA CRÍTICO: Produtos com Margem Abaixo de 10%"
        corpo = "Os seguintes produtos apresentaram margem bruta inferior a 10% na última semana:\n\n"
        for alerta in alertas:
            corpo += f"- {alerta['produto']}: Margem de {alerta['percentual_margem']}\n"
        corpo += "\n**Ação Imediata Necessária: Rever preços de venda e/ou custos de aquisição.**"
        
        # enviar_email_alerta(assunto, corpo, destinatarios=['gestor@empresa.com'])
        print(f"ALERTE ENVIADO: {assunto}") # Simulação de envio
        return f"ALERTA: {len(alertas)} produtos com margem crítica."
    
    return "Verificação de margem concluída. Sem alertas críticos."

@shared_task
def verificar_stock_critico():
    """
    Tarefa Celery para verificar o stock mínimo.
    """
    alertas = []
    # Assumindo que o seu modelo Produto tem um campo 'stock_atual' e 'stock_minimo'
    produtos_criticos = Produto.objects.filter(stock_atual__lte=F('stock_minimo'))
    
    for produto in produtos_criticos:
        alertas.append(f"{produto.nome} (Stock: {produto.stock_atual})")
        
    if alertas:
        assunto = "🛑 ALERTA DE STOCK: Baixo Stock Mínimo Atingido"
        corpo = "Os seguintes produtos atingiram ou ultrapassaram o stock mínimo:\n\n"
        corpo += "\n".join([f"- {a}" for a in alertas])
        corpo += "\n**Ação Imediata Necessária: Gerar ordem de compra.**"
        
        # enviar_email_alerta(assunto, corpo, destinatarios=['logistica@empresa.com'])
        print(f"ALERTE ENVIADO: {assunto}") # Simulação de envio
        return f"ALERTA: {len(alertas)} produtos com stock crítico."
        
    return "Verificação de stock concluída. Sem alertas."


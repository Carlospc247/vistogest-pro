from django.db.models import Sum
from decimal import Decimal
from datetime import date
from .models import MovimentacaoFinanceira, ContaBancaria

class CashFlowService:
    def __init__(self, empresa):
        self.empresa = empresa

    def get_daily_summary(self, target_date=None):
        if not target_date:
            target_date = date.today()

        # 1. Saldo Inicial (Saldo das contas no início do dia)
        # Nota: Calculamos o saldo atual e subtraímos o que aconteceu hoje
        total_hoje = MovimentacaoFinanceira.objects.filter(
            empresa=self.empresa,
            data_movimentacao=target_date,
            confirmada=True
        )

        entradas_hoje = total_hoje.filter(tipo_movimentacao='entrada').aggregate(s=Sum('valor'))['s'] or Decimal('0.00')
        saidas_hoje = total_hoje.filter(tipo_movimentacao='saida').aggregate(s=Sum('valor'))['s'] or Decimal('0.00')

        saldo_atual_total = ContaBancaria.objects.filter(
            empresa=self.empresa, 
            ativa=True
        ).aggregate(s=Sum('saldo_atual'))['s'] or Decimal('0.00')

        # O Rigor SOTARQ exige precisão:
        saldo_inicial = saldo_atual_total - entradas_hoje + saidas_hoje

        return {
            'data': target_date,
            'saldo_inicial': saldo_inicial,
            'entradas': entradas_hoje,
            'saidas': saidas_hoje,
            'saldo_final': saldo_atual_total,
            'movimentacoes': total_hoje.select_related('categoria', 'conta_bancaria', 'usuario_responsavel')
        }
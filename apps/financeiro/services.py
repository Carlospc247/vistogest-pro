# apps/financeiro/services.py
from django.db.models import Sum
from decimal import Decimal
from django.utils import timezone
from .models import MovimentacaoFinanceira, ContaBancaria



class CashFlowService:
    """Resumo diário baseado em movimentos bancários confirmados do tenant actual."""

    ZERO = Decimal("0.00")

    def get_daily_summary(self, target_date=None):
        target_date = target_date or timezone.localdate()
        contas_ativas = ContaBancaria.objects.filter(ativa=True)
        saldo_abertura_contas = contas_ativas.aggregate(total=Sum("saldo_inicial"))["total"] or self.ZERO

        movimentos_anteriores = MovimentacaoFinanceira.objects.filter(
            conta_bancaria__ativa=True,
            confirmada=True,
            status="confirmada",
            data_movimentacao__lt=target_date,
        )
        entradas_anteriores = movimentos_anteriores.filter(
            tipo_movimentacao="entrada"
        ).aggregate(total=Sum("valor"))["total"] or self.ZERO
        saidas_anteriores = movimentos_anteriores.filter(
            tipo_movimentacao__in=["saida", "transferencia"]
        ).aggregate(total=Sum("valor"))["total"] or self.ZERO
        saldo_inicial = saldo_abertura_contas + entradas_anteriores - saidas_anteriores

        movimentacoes = MovimentacaoFinanceira.objects.filter(
            conta_bancaria__ativa=True,
            data_movimentacao=target_date,
            confirmada=True,
        ).select_related("categoria", "conta_bancaria", "usuario_responsavel").order_by(
            "data_movimentacao", "created_at"
        )
        entradas = movimentacoes.filter(tipo_movimentacao="entrada").aggregate(
            total=Sum("valor")
        )["total"] or self.ZERO
        saidas = movimentacoes.filter(
            tipo_movimentacao__in=["saida", "transferencia"]
        ).aggregate(total=Sum("valor"))["total"] or self.ZERO
        saldo_final = saldo_inicial + entradas - saidas

        return {
            "data": target_date,
            "saldo_inicial": saldo_inicial,
            "entradas": entradas,
            "saidas": saidas,
            "saldo_final": saldo_final,
            "movimentacoes": movimentacoes,
        }



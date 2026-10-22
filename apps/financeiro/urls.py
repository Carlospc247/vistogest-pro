# apps/financeiro/urls.py
from django.urls import path
from . import views

app_name = "financeiro"

urlpatterns = [
    # Dashboard / reporting base
    path("", views.FinanceiroDashboardView.as_view(), name="dashboard"),
    path("fluxo-caixa/", views.FluxoCaixaView.as_view(), name="fluxo_caixa"),
    path("fluxo-caixa/novo/", views.FluxoCaixaCreateView.as_view(), name="fluxo_caixa_create"),
    path("fluxo-caixa/<int:pk>/editar/", views.FluxoCaixaUpdateView.as_view(), name="fluxo_caixa_update"),
    path("fluxo-caixa/<int:pk>/realizado/", views.MarcarFluxoRealizadoView.as_view(), name="fluxo_caixa_marcar_realizado"),
    path("fluxo-caixa/gerar/", views.GerarFluxoAutomaticoView.as_view(), name="fluxo_caixa_gerar"),
    path("dre/", views.DREView.as_view(), name="dre"),
    path("balanco/", views.BalancoPatrimonialView.as_view(), name="balanco"),

    # Formas de Pagamentos
    path("formas-pagamento/", views.FormasPagamentoView.as_view(), name="formas_pagamento"),
    path("formas-pagamento/<str:tipo>/alternar/", views.AlternarFormaPagamentoView.as_view(), name="forma_pagamento_alternar"),

    # Financial movements
    path("movimentacoes/", views.MovimentacaoFinanceiraListView.as_view(), name="movimentacao_lista"),
    path("movimentacoes/nova/", views.MovimentacaoFinanceiraCreateView.as_view(), name="movimentacao_create"),
    path("movimentacoes/<int:pk>/", views.MovimentacaoFinanceiraDetailView.as_view(), name="movimentacao_detail"),
    path("movimentacoes/<int:pk>/editar/", views.MovimentacaoFinanceiraUpdateView.as_view(), name="movimentacao_update"),
    path("movimentacoes/<int:pk>/confirmar/", views.ConfirmarMovimentacaoView.as_view(), name="movimentacao_confirmar"),
    path("movimentacoes/<int:pk>/estornar/", views.EstornarMovimentacaoView.as_view(), name="movimentacao_estornar"),
    path("movimentacoes/<int:pk>/conciliar/", views.ConciliarMovimentacaoView.as_view(), name="conciliar_movimentacao"),
    path("movimentacoes/<int:pk>/desconciliar/", views.DesconciliarMovimentacaoView.as_view(), name="desconciliar_movimentacao"),

    # Accounts receivable
    path("contas-receber/", views.ContaReceberListView.as_view(), name="conta_receber_lista"),
    path("contas-receber/nova/", views.ContaReceberCreateView.as_view(), name="conta_receber_create"),
    path("contas-receber/<int:pk>/", views.ContaReceberDetailView.as_view(), name="conta_receber_detail"),
    path("contas-receber/<int:pk>/editar/", views.ContaReceberUpdateView.as_view(), name="conta_receber_update"),
    path("contas-receber/<int:pk>/receber/", views.ReceberContaView.as_view(), name="receber_conta"),
    path("contas-receber/<int:pk>/parcelar/", views.ParcelarContaView.as_view(), name="parcelar_conta"),
    path("contas-receber/vencidas/", views.ContasVencidasView.as_view(), name="contas_vencidas"),
    path("contas-receber/vencendo/", views.ContasVencendoView.as_view(), name="contas_vencendo"),
    path("contas-receber/<int:pk>/negociar/", views.NegociarContaView.as_view(), name="negociar_conta"),
    path("contas-receber/<int:pk>/protestar/", views.ProtestarContaView.as_view(), name="protestar_conta"),

    # Accounts payable
    path("contas-pagar/", views.ContaPagarListView.as_view(), name="conta_pagar_lista"),
    path("contas-pagar/nova/", views.ContaPagarCreateView.as_view(), name="conta_pagar_create"),
    path("contas-pagar/<int:pk>/", views.ContaPagarDetailView.as_view(), name="conta_pagar_detail"),
    path("contas-pagar/<int:pk>/editar/", views.ContaPagarUpdateView.as_view(), name="conta_pagar_update"),
    path("contas-pagar/<int:pk>/pagar/", views.PagarContaView.as_view(), name="pagar_conta"),
    path("contas-pagar/<int:pk>/agendar/", views.AgendarPagamentoView.as_view(), name="agendar_pagamento"),
    path("contas-pagar/agenda/", views.AgendaPagamentosView.as_view(), name="agenda_pagamentos"),
    path("contas-pagar/aprovacao/", views.AprovacaoPagamentosView.as_view(), name="aprovacao_pagamentos"),
    path("contas-pagar/lote/", views.PagamentoLoteView.as_view(), name="pagamento_lote"),

    # plano de contas
    # ADICIONAR ao urlpatterns de apps/financeiro/urls.py (por exemplo antes de "# Planning"):

    # Plano de Contas (PGC)
    path("plano-contas/", views.PlanoContaListView.as_view(), name="plano_conta_lista"),
    path("plano-contas/nova/", views.PlanoContaCreateView.as_view(), name="plano_conta_create"),
    path("plano-contas/<int:pk>/", views.PlanoContaDetailView.as_view(), name="plano_conta_detail"),
    path("plano-contas/<int:pk>/editar/", views.PlanoContaUpdateView.as_view(), name="plano_conta_update"),
    path("plano-contas/<int:pk>/excluir/", views.PlanoContaDeleteView.as_view(), name="plano_conta_delete"),
    path("plano-contas/<int:pk>/alternar/", views.PlanoContaAlternarView.as_view(), name="plano_conta_alternar"),

    
    # Explicit ContaBancaria views (the app also exposes legacy Banco aliases)
    path("contas-bancarias/", views.ContaBancariaListView.as_view(), name="conta_bancaria_lista"),
    path("contas-bancarias/nova/", views.ContaBancariaCreateView.as_view(), name="conta_bancaria_create"),
    path("contas-bancarias/<int:pk>/", views.ContaBancariaDetailView.as_view(), name="conta_bancaria_detail"),
    path("contas-bancarias/<int:pk>/editar/", views.ContaBancariaUpdateView.as_view(), name="conta_bancaria_update"),

    # Banks
    path("bancos/", views.BancoListView.as_view(), name="banco_lista"),
    path("bancos/novo/", views.BancoCreateView.as_view(), name="banco_create"),
    path("bancos/<int:pk>/", views.BancoDetailView.as_view(), name="banco_detail"),
    path("bancos/<int:pk>/editar/", views.BancoEditarView.as_view(), name="banco_update"),
    path("bancos/<int:pk>/extrato/", views.ExtratoBancarioView.as_view(), name="extrato_bancario"),
    path("bancos/<int:pk>/conciliacao/", views.ConciliacaoBancariaView.as_view(), name="conciliacao_bancaria"),
    path("bancos/<int:pk>/deposito/", views.DepositoBancarioView.as_view(), name="deposito_bancario"),
    path("bancos/<int:pk>/saque/", views.SaqueBancarioView.as_view(), name="saque_bancario"),
    path("bancos/<int:pk>/transferencia/", views.TransferenciaBancariaView.as_view(), name="transferencia_bancaria"),

    # Physical cash
    path("caixa/", views.CaixaView.as_view(), name="caixa"),
    path("caixa/abrir/", views.AbrirCaixaView.as_view(), name="abrir_caixa"),
    path("caixa/fechar/", views.FecharCaixaView.as_view(), name="fechar_caixa"),
    path("caixa/sangria/", views.SangriaCaixaView.as_view(), name="sangria_caixa"),
    path("caixa/suprimento/", views.SuprimentoCaixaView.as_view(), name="suprimento_caixa"),
    path("caixa/conferencia/", views.ConferenciaCaixaView.as_view(), name="conferencia_caixa"),
    path("caixa/relatorio-diario/", views.RelatorioCaixaDiarioView.as_view(), name="relatorio_caixa_diario"),
    path("caixa/movimento/", views.MovimentoCaixaView.as_view(), name="movimento_caixa"),
    path("caixa/historico/", views.HistoricoCaixaView.as_view(), name="historico_caixa"),

    # Cards and TEF
    path("cartoes/", views.CartaoListView.as_view(), name="cartao_lista"),
    path("cartoes/vendas/", views.VendasCartaoView.as_view(), name="vendas_cartao"),
    path("cartoes/recebimentos/", views.RecebimentosCartaoView.as_view(), name="recebimentos_cartao"),
    path("cartoes/taxas/", views.TaxasCartaoView.as_view(), name="taxas_cartao"),
    path("cartoes/conciliacao/", views.ConciliacaoCartaoView.as_view(), name="conciliacao_cartao"),
    path("tef/", views.TEFView.as_view(), name="tef"),
    path("tef/transacoes/", views.TransacoesTEFView.as_view(), name="tef_transacoes"),
    path("tef/transacoes/<int:pk>/cancelar/", views.CancelarTEFView.as_view(), name="tef_cancelar"),

    # Cost centers and reconciliations
    path("centros-custo/", views.CentroCustoListView.as_view(), name="centro_custo_lista"),
    path("centros-custo/novo/", views.CentroCustoCreateView.as_view(), name="centro_custo_create"),
    path("centros-custo/<int:pk>/", views.CentroCustoDetailView.as_view(), name="centro_custo_detail"),
    path("conciliacoes-bancarias/", views.ConciliacaoBancariaListView.as_view(), name="conciliacao_lista"),
    path("conciliacoes-bancarias/nova/", views.ConciliacaoBancariaCreateView.as_view(), name="conciliacao_bancaria_create"),
    path("conciliacoes-bancarias/<int:pk>/", views.ConciliacaoBancariaDetailView.as_view(), name="conciliacao_detail"),
    path("conciliacao/", views.ConciliacaoView.as_view(), name="conciliacao"),
    path("conciliacao/automatica/", views.ConciliacaoAutomaticaView.as_view(), name="conciliacao_automatica"),

    # Planning
    path("projecoes/", views.ProjecoesFinanceirasView.as_view(), name="projecoes"),
    path("cenarios/", views.CenariosFinanceirosView.as_view(), name="cenarios"),
    path("metas/", views.MetasFinanceirasView.as_view(), name="metas"),

    # Taxes: dedicated prefix avoids collisions with dashboard/root
    path("impostos/", views.ImpostoTributoListView.as_view(), name="imposto_list"),
    path("impostos/novo/", views.ImpostoTributoCreateView.as_view(), name="imposto_create"),
    path("impostos/<int:pk>/", views.ImpostoTributoDetailView.as_view(), name="imposto_detail"),
    path("impostos/<int:pk>/editar/", views.ImpostoTributoUpdateView.as_view(), name="imposto_update"),
    path("impostos/<int:pk>/excluir/", views.ImpostoTributoDeleteView.as_view(), name="imposto_delete"),
    path("impostos/<int:pk>/calcular/", views.ImpostoCalcularView.as_view(), name="imposto_calcular"),
    path("impostos/<int:pk>/pagar/", views.ImpostoPagarView.as_view(), name="imposto_pagar"),
    path("impostos/<int:pk>/estornar/", views.estornar_imposto_view, name="estornar_imposto"),

    # Close, reports, analyses
    path("fechamento/", views.FechamentoMensalView.as_view(), name="fechamento_mensal"),
    path("fechamento/<int:mes>/<int:ano>/", views.FechamentoDetalhesView.as_view(), name="fechamento_detalhes"),
    path("relatorios/", views.FinanceiroRelatoriosView.as_view(), name="relatorios"),
    path("relatorios/fluxo-caixa/", views.RelatorioFluxoCaixaView.as_view(), name="relatorio_fluxo_caixa"),
    path("relatorios/dre/", views.RelatorioDREView.as_view(), name="relatorio_dre"),
    path("relatorios/balanco/", views.RelatorioBalancoView.as_view(), name="relatorio_balanco"),
    path("relatorios/inadimplencia/", views.RelatorioInadimplenciaView.as_view(), name="relatorio_inadimplencia"),
    path("relatorios/contas-receber/", views.RelatorioContasReceberView.as_view(), name="relatorio_contas_receber"),
    path("relatorios/contas-pagar/", views.RelatorioContasPagarView.as_view(), name="relatorio_contas_pagar"),
    path("relatorios/movimento-bancario/", views.RelatorioMovimentoBancarioView.as_view(), name="relatorio_movimento_bancario"),
    path("analises/", views.AnalisesFinanceirasView.as_view(), name="analises"),
    path("analises/liquidez/", views.AnaliseLiquidezView.as_view(), name="analise_liquidez"),
    path("analises/rentabilidade/", views.AnaliseRentabilidadeView.as_view(), name="analise_rentabilidade"),
    path("analises/endividamento/", views.AnaliseEndividamentoView.as_view(), name="analise_endividamento"),

    # AJAX
    path("ajax/calcular-juros/", views.CalcularJurosView.as_view(), name="calcular_juros"),
    path("ajax/consultar-saldo/", views.ConsultarSaldoView.as_view(), name="consultar_saldo"),
    path("ajax/validar-conta/", views.ValidarContaView.as_view(), name="validar_conta"),
    path("ajax/buscar-banco/", views.BuscarBancoView.as_view(), name="buscar_banco"),

    # Import / export
    path("importar/", views.ImportarFinanceiroView.as_view(), name="importar"),
    path("importar/ofx/", views.ImportarOFXView.as_view(), name="importar_ofx"),
    path("importar/cnab/", views.ImportarCNABView.as_view(), name="importar_cnab"),
    path("exportar/", views.ExportarFinanceiroView.as_view(), name="exportar"),

    # REST API
    path("api/saldo-atual/", views.SaldoAtualAPIView.as_view(), name="api_saldo_atual"),
    path("api/projecao-fluxo/", views.ProjecaoFluxoAPIView.as_view(), name="api_projecao_fluxo"),
    path("api/indicadores/", views.IndicadoresFinanceirosAPIView.as_view(), name="api_indicadores"),
]

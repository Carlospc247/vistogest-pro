# apps/funcionarios/urls_recibo.py
from django.urls import path

from . import views_recibo as v

urlpatterns = [
    # Recibos
    path('recibos/', v.ReciboListView.as_view(), name='recibo_lista'),
    path('recibos/meus/', v.MeusRecibosView.as_view(), name='meus_recibos'),
    path('recibos/previa/', v.ReciboPreviaView.as_view(), name='recibo_previa'),
    path('recibos/<int:pk>/', v.ReciboDetailView.as_view(), name='recibo_detalhe'),
    path('recibos/<int:pk>/pdf/', v.ReciboPDFView.as_view(), name='recibo_pdf'),
    path('recibos/<int:pk>/imprimir/', v.ReciboImprimirView.as_view(), name='recibo_imprimir'),
    path('recibos/<int:pk>/recalcular/', v.ReciboRecalcularView.as_view(), name='recibo_recalcular'),
    path('recibos/<int:pk>/lancamento/', v.ReciboLancamentoView.as_view(), name='recibo_lancamento'),
    path('recibos/<int:pk>/ajuste/', v.ReciboAjusteView.as_view(), name='recibo_ajuste'),
    path('recibos/<int:pk>/emitir/', v.ReciboEmitirView.as_view(), name='recibo_emitir'),
    path('recibos/<int:pk>/pagar/', v.ReciboPagarView.as_view(), name='recibo_pagar'),
    path('recibos/<int:pk>/anular/', v.ReciboAnularView.as_view(), name='recibo_anular'),
    path('recibos/<int:pk>/retificar/', v.ReciboRetificarView.as_view(), name='recibo_retificar'),
    path('recibos/<int:pk>/confirmacao/', v.ReciboConfirmacaoView.as_view(), name='recibo_confirmacao'),
    # Processamentos
    path('recibos/processamentos/', v.ProcessamentoListView.as_view(), name='processamento_lista'),
    path('recibos/processamentos/novo/', v.ProcessamentoCreateView.as_view(), name='processamento_novo'),
    path('recibos/processamentos/<int:pk>/', v.ProcessamentoDetailView.as_view(), name='processamento_detalhe'),
    path('recibos/processamentos/<int:pk>/gerar/', v.ProcessamentoGerarView.as_view(), name='processamento_gerar'),
    path('recibos/processamentos/<int:pk>/emitir/', v.ProcessamentoEmitirView.as_view(), name='processamento_emitir'),
    path('recibos/processamentos/<int:pk>/pagar/', v.ProcessamentoPagarView.as_view(), name='processamento_pagar'),
    path('recibos/processamentos/<int:pk>/cancelar/', v.ProcessamentoCancelarView.as_view(), name='processamento_cancelar'),
    # Rubricas
    path('recibos/rubricas/', v.RubricaListView.as_view(), name='rubrica_lista'),
    path('recibos/rubricas/nova/', v.RubricaCreateView.as_view(), name='rubrica_nova'),
    path('recibos/rubricas/ordem/', v.RubricaOrdemView.as_view(), name='rubrica_ordem'),
    path('recibos/rubricas/<int:pk>/editar/', v.RubricaUpdateView.as_view(), name='rubrica_editar'),
    path('recibos/rubricas/<int:pk>/alternar/', v.RubricaAlternarView.as_view(), name='rubrica_alternar'),
    path('recibos/rubricas/<int:pk>/atribuicoes/', v.AtribuicaoListView.as_view(), name='atribuicao_lista'),
    path('recibos/rubricas/<int:pk>/atribuicoes/nova/', v.AtribuicaoCreateView.as_view(), name='atribuicao_nova'),
    path('recibos/atribuicoes/<int:pk>/remover/', v.AtribuicaoRemoverView.as_view(), name='atribuicao_remover'),
    # Fiscal e configuração
    path('recibos/parametros/', v.ParametroListView.as_view(), name='parametro_lista'),
    path('recibos/parametros/novo/', v.ParametroCreateView.as_view(), name='parametro_novo'),
    path('recibos/parametros/<int:pk>/editar/', v.ParametroUpdateView.as_view(), name='parametro_editar'),
    path('recibos/tabelas-irt/', v.TabelaIRTListView.as_view(), name='tabela_irt_lista'),
    path('recibos/tabelas-irt/nova/', v.TabelaIRTFormView.as_view(), name='tabela_irt_nova'),
    path('recibos/tabelas-irt/<int:pk>/editar/', v.TabelaIRTFormView.as_view(), name='tabela_irt_editar'),
    path('recibos/configuracao/', v.ConfiguracaoReciboView.as_view(), name='recibo_configuracao'),
    path('recibos/funcionario/<int:funcionario_pk>/dados/', v.DadosSalariaisView.as_view(), name='dados_salariais'),
    path('recibos/auditoria/', v.AuditoriaListView.as_view(), name='auditoria_lista'),
]
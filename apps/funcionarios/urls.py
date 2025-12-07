# apps/funcionarios/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .api import viewsets

# API Router
router = DefaultRouter()
router.register(r'funcionarios', viewsets.FuncionarioViewSet)
router.register(r'cargos', viewsets.CargoViewSet)
router.register(r'departamentos', viewsets.DepartamentoViewSet)

app_name = 'funcionarios'

urlpatterns = [
    # =====================================
    # LISTAGENS PRINCIPAIS
    # =====================================
    path('funcionarios/', views.FuncionariosView.as_view(), name='funcionarios'),
    path('meu-turno/', views.MeuTurnoView.as_view(), name='meuturno'),
    path('fechar-turno/', views.FecharTurnoView.as_view(), name='fechar_turno'),
    path('relatorio-fechamento/<int:pk>/', views.RelatorioFechamentoView.as_view(), name='relatorio_fechamento'),
    path('relatorio-fechamento/<int:pk>/pdf/', views.RelatorioFechamentoPDFView.as_view(), name='relatorio_fechamento_pdf'),
    path('dashboard/', views.FuncionarioDashboardView.as_view(), name='dashboard'),
    path('cargos/', views.CargoListView.as_view(), name='cargo_lista'),
    path('departamentos/', views.DepartamentoListView.as_view(), name='departamento_lista'),
    
    # =====================================
    # GESTÃO DE FUNCIONÁRIOS
    # =====================================
    path('novo/', views.FuncionarioCreateView.as_view(), name='create'),
    path('<int:pk>/', views.FuncionarioDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.FuncionarioUpdateView.as_view(), name='update'),
    path('<int:pk>/deletar/', views.FuncionarioDeleteView.as_view(), name='delete'),
    
    # Status do funcionário
    path('<int:pk>/ativar/', views.AtivarFuncionarioView.as_view(), name='ativar'),
    path('<int:pk>/desativar/', views.DesativarFuncionarioView.as_view(), name='desativar'),
    path('<int:pk>/suspender/', views.SuspenderFuncionarioView.as_view(), name='suspender'),
    path('<int:pk>/demitir/', views.DemitirFuncionarioView.as_view(), name='demitir'),
    
    # =====================================
    # PERFIL E DADOS PESSOAIS
    # =====================================
    path('<int:pk>/perfil/', views.PerfilFuncionarioView.as_view(), name='perfil'),
    path('<int:pk>/documentos/', views.DocumentosFuncionarioView.as_view(), name='documentos'),
    path('<int:pk>/foto/', views.FotoFuncionarioView.as_view(), name='foto'),
    path('<int:pk>/contatos/', views.ContatosFuncionarioView.as_view(), name='contatos'),
    
    # =====================================
    # GESTÃO DE CARGOS
    # =====================================
    path('cargos/novo/', views.CargoCreateView.as_view(), name='cargo_create'),
    path('cargos/<int:pk>/', views.CargoDetailView.as_view(), name='cargo_detail'),
    path('cargos/<int:pk>/editar/', views.CargoUpdateView.as_view(), name='cargo_update'),
    path('cargos/<int:pk>/deletar/', views.CargoDeleteView.as_view(), name='cargo_delete'),
    
    # =====================================
    # GESTÃO DE DEPARTAMENTOS
    # =====================================
    path('departamentos/novo/', views.DepartamentoCreateView.as_view(), name='departamento_create'),
    path('departamentos/<int:pk>/', views.DepartamentoDetailView.as_view(), name='departamento_detail'),
    path('departamentos/<int:pk>/editar/', views.DepartamentoUpdateView.as_view(), name='departamento_update'),
    path('departamentos/<int:pk>/funcionarios/', views.FuncionariosDepartamentoView.as_view(), name='departamento_funcionarios'),
    
    # =====================================
    # JORNADA E HORÁRIOS
    # =====================================
    path('jornadas/', views.JornadaTrabalhoListView.as_view(), name='jornada_lista'),
    path('jornadas/nova/', views.JornadaTrabalhoCreateView.as_view(), name='jornada_create'),
    path('<int:pk>/jornada/', views.JornadaFuncionarioView.as_view(), name='funcionario_jornada'),
    path('escalas/', views.EscalaTrabalhoView.as_view(), name='escala'),
    path('horarios/', views.HorarioTrabalhoView.as_view(), name='horarios'),
    
    # =====================================
    # PONTO ELETRÔNICO
    # =====================================
    path('ponto/', views.PontoEletronicoView.as_view(), name='ponto'),
    path('ponto/registrar/', views.RegistrarPontoView.as_view(), name='registrar_ponto'),
    path('ponto/<int:funcionario_pk>/historico/', views.HistoricoPontoView.as_view(), name='historico_ponto'),
    path('ponto/relatorios/', views.RelatorioPontoView.as_view(), name='relatorio_ponto'),
    path('ponto/ajustes/', views.AjustesPontoView.as_view(), name='ajustes_ponto'),
    
    # =====================================
    # FOLHA DE PAGAMENTO
    # =====================================
    path('folha/', views.FolhaPagamentoView.as_view(), name='folha_pagamento'),
    path('folha/calcular/', views.CalcularFolhaView.as_view(), name='calcular_folha'),
    path('folha/<int:mes>/<int:ano>/', views.FolhaMensalView.as_view(), name='folha_mensal'),
    path('<int:pk>/holerite/<int:mes>/<int:ano>/', views.HoleriteView.as_view(), name='holerite'),
    path('<int:pk>/salario/', views.SalarioFuncionarioView.as_view(), name='salario'),
    
    # =====================================
    # BENEFÍCIOS
    # =====================================
    path('beneficios/', views.BeneficioListView.as_view(), name='beneficio_lista'),
    path('<int:pk>/beneficios/', views.BeneficiosFuncionarioView.as_view(), name='funcionario_beneficios'),
    path('vale-transporte/', views.ValeTransporteView.as_view(), name='vale_transporte'),
    path('vale-refeicao/', views.ValeRefeicaoView.as_view(), name='vale_refeicao'),
    path('plano-saude/', views.PlanoSaudeView.as_view(), name='plano_saude'),
    
    # =====================================
    # FÉRIAS E AFASTAMENTOS
    # =====================================
    path('ferias/', views.FeriasListView.as_view(), name='ferias_lista'),
    path('<int:pk>/ferias/', views.FeriasFuncionarioView.as_view(), name='funcionario_ferias'),
    path('ferias/planejar/', views.PlanejarFeriasView.as_view(), name='planejar_ferias'),
    path('afastamentos/', views.AfastamentoListView.as_view(), name='afastamento_lista'),
    path('<int:pk>/afastamentos/', views.AfastamentosFuncionarioView.as_view(), name='funcionario_afastamentos'),
    
    # =====================================
    # TREINAMENTOS E CAPACITAÇÃO
    # =====================================
    path('treinamentos/', views.TreinamentoListView.as_view(), name='treinamento_lista'),
    path('treinamentos/novo/', views.TreinamentoCreateView.as_view(), name='treinamento_create'),
    path('treinamentos/<int:pk>/', views.TreinamentoDetailView.as_view(), name='treinamento_detail'),
    path('<int:pk>/treinamentos/', views.TreinamentosFuncionarioView.as_view(), name='funcionario_treinamentos'),
    path('certificacoes/', views.CertificacaoListView.as_view(), name='certificacao_lista'),
    

    path('responsabilidade-tecnica/', views.ResponsabilidadeTecnicaView.as_view(), name='responsabilidade_tecnica'),
    
    # =====================================
    # AVALIAÇÃO DE DESEMPENHO
    # =====================================
    path('avaliacoes/', views.AvaliacaoDesempenhoListView.as_view(), name='avaliacao_lista'),
    path('<int:pk>/avaliacoes/', views.AvaliacoesFuncionarioView.as_view(), name='funcionario_avaliacoes'),
    path('<int:pk>/nova-avaliacao/', views.NovaAvaliacaoView.as_view(), name='nova_avaliacao'),
    path('metas/', views.MetasFuncionarioView.as_view(), name='metas'),
    
    # =====================================
    # RECRUTAMENTO E SELEÇÃO
    # =====================================
    path('recrutamento/', views.RecrutamentoView.as_view(), name='recrutamento'),
    path('candidatos/', views.CandidatoListView.as_view(), name='candidato_lista'),
    path('candidatos/<int:pk>/', views.CandidatoDetailView.as_view(), name='candidato_detail'),
    path('processos-seletivos/', views.ProcessoSeletivoView.as_view(), name='processo_seletivo'),
    
    # =====================================
    # RELATÓRIOS DE RH
    # =====================================
    path('relatorios/', views.FuncionarioRelatoriosView.as_view(), name='relatorios'),
    path('relatorios/aniversariantes/', views.RelatorioAniversariantesView.as_view(), name='relatorio_aniversariantes'),
    path('relatorios/admissoes/', views.RelatorioAdmissoesView.as_view(), name='relatorio_admissoes'),
    path('relatorios/demissoes/', views.RelatorioDemissoesView.as_view(), name='relatorio_demissoes'),
    path('relatorios/folha/', views.RelatorioFolhaView.as_view(), name='relatorio_folha'),
    
    # =====================================
    # DOCUMENTOS TRABALHISTAS
    # =====================================
    path('<int:pk>/ctps/', views.CTPSView.as_view(), name='ctps'),
    path('<int:pk>/contrato/', views.ContratoTrabalhoView.as_view(), name='contrato'),
    path('<int:pk>/termo-rescisao/', views.TermoRescisaoView.as_view(), name='termo_rescisao'),
    path('<int:pk>/declaracoes/', views.DeclaracoesView.as_view(), name='declaracoes'),
    
    # =====================================
    # COMUNICAÇÃO INTERNA
    # =====================================
    path('comunicados/', views.ComunicadoListView.as_view(), name='comunicado_lista'),
    path('comunicados/novo/', views.ComunicadoCreateView.as_view(), name='comunicado_create'),
    path('<int:pk>/enviar-comunicado/', views.EnviarComunicadoView.as_view(), name='enviar_comunicado'),
    path('muriral/', views.MuralEletronicoView.as_view(), name='mural'),
    
    # =====================================
    # AJAX E UTILITÁRIOS
    # =====================================
    path('ajax/buscar/', views.BuscarFuncionarioAjaxView.as_view(), name='buscar_ajax'),
    path('ajax/calcular-salario/', views.CalcularSalarioView.as_view(), name='calcular_salario'),
    path('ajax/verificar-bi/', views.VerificarBIFuncionarioView.as_view(), name='verificar_bi'),
    path('ajax/consultar-postal/', views.ConsultarPOSTALFuncionarioView.as_view(), name='consultar_POSTAL'),
    
    # =====================================
    # IMPORTAÇÃO E EXPORTAÇÃO
    # =====================================
    path('importar/', views.ImportarFuncionariosView.as_view(), name='importar'),
    path('exportar/', views.ExportarFuncionariosView.as_view(), name='exportar'),
    
    # =====================================
    # API REST
    # =====================================
    path('api/', include(router.urls)),
    
    # API Personalizada
    path('api/registrar-ponto/', views.RegistrarPontoAPIView.as_view(), name='api_registrar_ponto'),
    path('api/consultar-ferias/', views.ConsultarFeriasAPIView.as_view(), name='api_consultar_ferias'),
    path('api/horarios-disponiveis/', views.HorariosDisponiveisAPIView.as_view(), name='api_horarios_disponiveis'),
]
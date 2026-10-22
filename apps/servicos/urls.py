from django.urls import path
from . import views, tracking_views

app_name = "servicos"

urlpatterns = [
    # Dashboard e catálogo
    path("dashboard/", views.ServicoDashboard.as_view(), name="servico_dashboard"),
    path("catalogo/", views.ServicoListView.as_view(), name="servico_list"),
    path("catalogo/novo/", views.ServicoCreateView.as_view(), name="servico_create"),
    path("catalogo/<int:pk>/editar/", views.ServicoUpdateView.as_view(), name="servico_update"),
    path("catalogo/<int:pk>/eliminar/", views.ServicoDeleteView.as_view(), name="servico_delete"),
    path("api/listar/", views.listar_servicos_api, name="listar_servicos_api"),
    path("api/buscar/", views.buscar_servicos_api, name="buscar_servicos_api"),

    # Agendamentos
    path("agendamentos/", views.AgendamentoListView.as_view(), name="agendamento_list"),
    path("agendamentos/novo/", views.AgendamentoCreateView.as_view(), name="agendamento_create"),
    path("agendamentos/<int:pk>/", views.AgendamentoDetailView.as_view(), name="agendamento_detail"),
    path("agendamentos/<int:pk>/editar/", views.AgendamentoUpdateView.as_view(), name="agendamento_update"),
    path("agendamentos/<int:pk>/eliminar/", views.AgendamentoDeleteView.as_view(), name="agendamento_delete"),
    path("api/agendamentos/buscar/", views.buscar_agendamento_api, name="buscar_agendamento_api"),
    path("agendamentos/<int:pk>/iniciar/", views.IniciarServicoView.as_view(), name="servico_iniciar"),
    path("agendamentos/<int:pk>/finalizar/", views.FinalizarServicoView.as_view(), name="servico_finalizar"),

    # Acompanhamento e operações (as operações de alteração aceitam POST)
    path("agendamentos/<int:pk>/acompanhamento/", tracking_views.acompanhamento_agendamento, name="acompanhamento_agendamento"),
    path("agendamentos/<int:pk>/acompanhamento/eventos/", tracking_views.acompanhamento_eventos_api, name="acompanhamento_eventos_api"),
    path("agendamentos/<int:pk>/acompanhamento/mensagem/", tracking_views.acompanhamento_enviar_mensagem, name="acompanhamento_mensagem"),
    path("agendamentos/<int:pk>/pausar/", tracking_views.pausar_agendamento, name="acompanhamento_pausar"),
    path("agendamentos/<int:pk>/retomar/", tracking_views.retomar_agendamento, name="acompanhamento_retomar"),
    path("agendamentos/<int:pk>/adiar/", tracking_views.adiar_agendamento, name="acompanhamento_adiar"),
    path("agendamentos/<int:pk>/cancelar/", tracking_views.cancelar_agendamento, name="acompanhamento_cancelar"),

    # Notificações — prefixo próprio para não colidir com agendamentos e APIs
    path("notificacoes/", views.notificacao_list, name="notificacao_list"),
    path("notificacoes/criar/", views.notificacao_create, name="notificacao_create"),
    path("notificacoes/<int:pk>/editar/", views.notificacao_update, name="notificacao_update"),
    path("notificacoes/<int:pk>/eliminar/", views.notificacao_delete, name="notificacao_delete"),
    path("api/notificacoes/buscar/", views.buscar_notificacao_api, name="buscar_notificacao_api"),

    # Configurações
    path("config/notificacoes/", views.configuracao_notificacao_update, name="config_notificacao"),
]

from django.urls import path
from . import views

app_name = "comunicacao"
urlpatterns = [
    path("", views.CaixaEntradaView.as_view(), name="caixa_entrada"),
    path("conversa/<int:pk>/", views.ConversaDetalheView.as_view(), name="conversa"),
    path("conversa/<int:pk>/mensagens/", views.mensagens_api, name="mensagens_api"),
    path("clientes/<int:cliente_id>/iniciar/", views.iniciar_conversa_cliente, name="iniciar_conversa_cliente"),
    path("grupos/novo/", views.criar_grupo_funcionarios, name="criar_grupo"),
]

from django.urls import path
from . import views

app_name = "clientes"

urlpatterns = [
    # CLIENTE
    path("dashboard/", views.ClienteDashboardView.as_view(), name="dashboard"),
    path("", views.ClienteListView.as_view(), name="lista"),
    path("<int:pk>/", views.ClienteDetailView.as_view(), name="detalhe"),
    path("novo/", views.ClienteCreateView.as_view(), name="novo"),
    path("<int:pk>/editar/", views.ClienteUpdateView.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.ClienteDeleteView.as_view(), name="excluir"),
    path("<int:pk>/toggle/", views.toggle_cliente, name="toggle_cliente"),

    # CATEGORIA CLIENTE
    path("categorias/", views.CategoriaClienteListView.as_view(), name="categorias"),
    path("categorias/<int:pk>/", views.CategoriaClienteDetailView.as_view(), name="categoria_detalhe"),
    path("categorias/novo/", views.CategoriaClienteCreateView.as_view(), name="categoria_novo"),
    path("categorias/<int:pk>/editar/", views.CategoriaClienteUpdateView.as_view(), name="categoria_editar"),
    path("categorias/<int:pk>/excluir/", views.CategoriaClienteDeleteView.as_view(), name="categoria_excluir"),

    # CONTRATOS
    path("", views.lista_contratos, name="lista"),
    path("modelos/<str:tipo>/guardar/", views.guardar_modelo, name="guardar_modelo"),
    path("enviar/<int:cliente_id>/", views.enviar_contrato, name="enviar"),
    path("rever/<int:pk>/", views.rever_contrato, name="rever"),
    path("interno/<int:pk>/", views.detalhe_contrato_staff, name="detalhe_interno"),
    path("portal/<int:pk>/", views.ClienteContratoDetalheView.as_view(), name="cliente_detalhe"),
    
    # ENDEREÇOS
    path("enderecos/", views.EnderecoClienteListView.as_view(), name="enderecos"),
    path("enderecos/<int:pk>/", views.EnderecoClienteDetailView.as_view(), name="endereco_detalhe"),
    path("enderecos/novo/", views.EnderecoClienteCreateView.as_view(), name="endereco_novo"),
    path("enderecos/<int:pk>/editar/", views.EnderecoClienteUpdateView.as_view(), name="endereco_editar"),
    path("enderecos/<int:pk>/excluir/", views.EnderecoClienteDeleteView.as_view(), name="endereco_excluir"),

    # CONTATOS
    path("contatos/", views.ContatoClienteListView.as_view(), name="contatos"),
    path("contatos/<int:pk>/", views.ContatoClienteDetailView.as_view(), name="contato_detalhe"),
    path("contatos/novo/", views.ContatoClienteCreateView.as_view(), name="contato_novo"),
    path("contatos/<int:pk>/editar/", views.ContatoClienteUpdateView.as_view(), name="contato_editar"),
    path("contatos/<int:pk>/excluir/", views.ContatoClienteDeleteView.as_view(), name="contato_excluir"),

    # HISTORICO
    path("historicos/", views.HistoricoClienteListView.as_view(), name="historicos"),
    path("historicos/<int:pk>/", views.HistoricoClienteDetailView.as_view(), name="historico_detalhe"),
    path("historicos/novo/", views.HistoricoClienteCreateView.as_view(), name="historico_novo"),
    path("historicos/<int:pk>/editar/", views.HistoricoClienteUpdateView.as_view(), name="historico_editar"),
    path("historicos/<int:pk>/excluir/", views.HistoricoClienteDeleteView.as_view(), name="historico_excluir"),

    # CARTÕES
    path("cartoes/", views.CartaoFidelidadeListView.as_view(), name="cartoes"),
    path("cartoes/<int:pk>/", views.CartaoFidelidadeDetailView.as_view(), name="cartao_detalhe"),
    path("cartoes/novo/", views.CartaoFidelidadeCreateView.as_view(), name="cartao_novo"),
    path("cartoes/<int:pk>/editar/", views.CartaoFidelidadeUpdateView.as_view(), name="cartao_editar"),
    path("cartoes/<int:pk>/excluir/", views.CartaoFidelidadeDeleteView.as_view(), name="cartao_excluir"),

    # MOVIMENTAÇÕES
    path("movimentacoes/", views.MovimentacaoFidelidadeListView.as_view(), name="movimentacoes"),
    path("movimentacoes/<int:pk>/", views.MovimentacaoFidelidadeDetailView.as_view(), name="movimentacao_detalhe"),
    path("movimentacoes/novo/", views.MovimentacaoFidelidadeCreateView.as_view(), name="movimentacao_novo"),
    path("movimentacoes/<int:pk>/editar/", views.MovimentacaoFidelidadeUpdateView.as_view(), name="movimentacao_editar"),
    path("movimentacoes/<int:pk>/excluir/", views.MovimentacaoFidelidadeDeleteView.as_view(), name="movimentacao_excluir"),

    # PREFERENCIAS
    path("preferencias/", views.PreferenciaClienteListView.as_view(), name="preferencias"),
    path("preferencias/<int:pk>/", views.PreferenciaClienteDetailView.as_view(), name="preferencia_detalhe"),
    path("preferencias/novo/", views.PreferenciaClienteCreateView.as_view(), name="preferencia_novo"),
    path("preferencias/<int:pk>/editar/", views.PreferenciaClienteUpdateView.as_view(), name="preferencia_editar"),
    path("preferencias/<int:pk>/excluir/", views.PreferenciaClienteDeleteView.as_view(), name="preferencia_excluir"),

    # TELEFONES
    path("telefones/", views.TelefoneClienteListView.as_view(), name="telefones"),
    path("telefones/<int:pk>/", views.TelefoneClienteDetailView.as_view(), name="telefone_detalhe"),
    path("telefones/novo/", views.TelefoneClienteCreateView.as_view(), name="telefone_novo"),
    path("telefones/<int:pk>/editar/", views.TelefoneClienteUpdateView.as_view(), name="telefone_editar"),
    path("telefones/<int:pk>/excluir/", views.TelefoneClienteDeleteView.as_view(), name="telefone_excluir"),

    # GRUPOS
    path("grupos/", views.GrupoClienteListView.as_view(), name="grupos"),
    path("grupos/<int:pk>/", views.GrupoClienteDetailView.as_view(), name="grupo_detalhe"),
    path("grupos/novo/", views.GrupoClienteCreateView.as_view(), name="grupo_novo"),
    path("grupos/<int:pk>/editar/", views.GrupoClienteUpdateView.as_view(), name="grupo_editar"),
    path("grupos/<int:pk>/excluir/", views.GrupoClienteDeleteView.as_view(), name="grupo_excluir"),

    # PROGRAMAS FIDELIDADE
    path("programas/", views.ProgramaFidelidadeListView.as_view(), name="programas"),
    path("programas/<int:pk>/", views.ProgramaFidelidadeDetailView.as_view(), name="programa_detalhe"),
    path("programas/novo/", views.ProgramaFidelidadeCreateView.as_view(), name="programa_novo"),
    path("programas/<int:pk>/editar/", views.ProgramaFidelidadeUpdateView.as_view(), name="programa_editar"),
    path("programas/<int:pk>/excluir/", views.ProgramaFidelidadeDeleteView.as_view(), name="programa_excluir"),

    # PONTOS
    path("pontos/", views.PontoListView.as_view(), name="pontos"),
    path("pontos/<int:pk>/", views.PontoDetailView.as_view(), name="ponto_detalhe"),
    path("pontos/novo/", views.PontoCreateView.as_view(), name="ponto_novo"),
    path("pontos/<int:pk>/editar/", views.PontoUpdateView.as_view(), name="ponto_editar"),
    path("pontos/<int:pk>/excluir/", views.PontoDeleteView.as_view(), name="ponto_excluir"),

    
    # Rota para a API de busca de clientes
    path('api/clientes/buscar/', views.buscar_clientes_api, name='api_buscar_clientes'),
]

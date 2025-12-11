

# Em apps/produtos/urls.py

from django.urls import path

from apps.produtos import api_views
from . import views

app_name = 'produtos'

urlpatterns = [
    # --- PRODUTOS ---
    # A sua view 'ProdutosView' não estava registada. Esta é a lista principal.
    path('', views.ProdutosView.as_view(), name='produto_list'),
    path('criar/', views.CriarProdutoView.as_view(), name='criar'),
    path('<int:produto_id>/editar/', views.EditarProdutoView.as_view(), name='editar'),
    path('<int:produto_id>/deletar/', views.DeletarProdutoView.as_view(), name='deletar'),
    path('deletar-todos-tudo/', views.DeletarTodosProdutosLotesView.as_view(), name='deletar_todos_tudo'),
    path('deletar-todos-soft/', views.DeletarTodosProdutosManterLotesView.as_view(), name='deletar_todos_soft'),
    path('<int:produto_id>/toggle/', views.ToggleProdutoView.as_view(), name='toggle_ativo'),

    # --- CATEGORIAS & FABRICANTES ---
    path('categorias/', views.CategoriaListView.as_view(), name='categoria_list'),
    path('categorias/nova/', views.CategoriaCreateView.as_view(), name='categoria_create'),
    path('categorias/<int:pk>/editar/', views.CategoriaUpdateView.as_view(), name='categoria_update'),
    path('categorias/<int:pk>/eliminar/', views.CategoriaDeleteView.as_view(), name='categoria_delete'),


    path('fabricantes/', views.FabricanteListView.as_view(), name='fabricante_list'),
    
    # --- LOTES ---
    path('lotes/', views.LoteListView.as_view(), name='lote_list'),
    path('lotes/criar/', views.LoteCreateView.as_view(), name='lote_create'),
    path('lotes/<int:pk>/editar/', views.LoteUpdateView.as_view(), name='lote_update'),
    path('lotes/<int:pk>/', views.LoteDetailView.as_view(), name='lote_detail'),
    path('lotes/<int:pk>/deletar/', views.LoteDeleteView.as_view(), name='lote_delete'),
    
    # --- IMPORTAÇÃO E TEMPLATES ---
    path('importar/', views.ImportarProdutosView.as_view(), name='importar'),
    path('template/', views.TemplateProdutosView.as_view(), name='template'),
    path('exportar/excel/', views.ExportarProdutosExcelView.as_view(), name='exportar_excel'),
    path('exportar/pdf/', views.ExportarProdutosPDFView.as_view(), name='exportar_pdf'),



    path('api/buscar/', views.buscar_produtos_api, name='buscar_produtos_api'),


    path('api/categorias/', views.listar_categorias_api, name='listar_categorias_api'),
    # path('api/categorias/', api_views.categorias_api, name='categorias_api'), # DUPLICADO




]


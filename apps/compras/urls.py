from django.urls import path
from . import views
app_name="compras"
urlpatterns=[
    path("",views.CompraDashboardView.as_view(),name="dashboard"),
    path("lista/",views.CompraListView.as_view(),name="listar"),
    path("nova/",views.CompraCreateView.as_view(),name="criar"),
    path("<int:pk>/",views.CompraDetailView.as_view(),name="detalhe"),
    path("<int:pk>/editar/",views.CompraUpdateView.as_view(),name="editar"),
    path("<int:pk>/eliminar/",views.CompraDeleteView.as_view(),name="eliminar"),
]

"""URLConf exclusivo da área interna; incluir apenas no URLConf public."""
from django.urls import path
from . import views, views_comercial

app_name = "parceiros_admin"

urlpatterns = [
    path("", views_comercial.PartnerStaffDashboardComercialView.as_view(), name="admin-dashboard"),
    path("parceiros/", views_comercial.PartnerListComercialView.as_view(), name="admin-parceiros"),
    path("parceiros/novo/", views_comercial.PartnerCreateComercialView.as_view(), name="admin-parceiro-criar"),
    path("parceiros/<int:pk>/", views_comercial.PartnerAdminDetailComercialView.as_view(), name="admin-detalhe"),
    # O chat usa namespace do portal para que parceiros e funcionários partilhem a mesma view
    # autenticada e a mesma rota privada de download, com autorização por participante/permissão.
]

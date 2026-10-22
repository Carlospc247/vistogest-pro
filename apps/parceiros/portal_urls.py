"""URLConf exclusivo do portal externo; incluir apenas no URLConf public."""
from django.urls import path
from . import views, views_comercial, views_unlimited

app_name = "parceiros"

urlpatterns = [
    path("", views_comercial.PartnerDashboardComercialView.as_view(), name="portal-dashboard"),
    path("carteira/", views_comercial.PartnerCommissionWalletView.as_view(), name="portal-carteira"),
    path("clientes/", views_comercial.PartnerClientListComercialView.as_view(), name="portal-clientes"),
    path("clientes/novo/", views_unlimited.PartnerClientCreateUnlimitedView.as_view(), name="portal-cliente-criar"),
    path("clientes/<int:pk>/renovar/", views_comercial.PartnerClientRenewLicenseView.as_view(), name="portal-cliente-renovar"),
    path("clientes/<int:pk>/", views.PartnerClientDetailView.as_view(), name="portal-cliente-detalhe"),
    path("reativacao/", views_comercial.PartnerReactivationRequestView.as_view(), name="portal-reativacao"),
    path("conversas/", views_comercial.PartnerChatInboxView.as_view(), name="chat_inbox"),
    path("conversas/novo/", views_comercial.PartnerChatCreateView.as_view(), name="chat_criar"),
    path("conversas/<int:pk>/", views_comercial.PartnerChatDetailView.as_view(), name="chat_detalhe"),
    path("mensagens/<int:pk>/anexo/", views_comercial.PartnerMessageAttachmentView.as_view(), name="mensagem_anexo"),
]

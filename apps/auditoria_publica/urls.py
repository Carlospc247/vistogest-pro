from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LogAuditoriaPublicaViewSet
from rest_framework.routers import SimpleRouter

# SimpleRouter não registra o sufixo de formato automaticamente
router = SimpleRouter()
router.register(r'logs', LogAuditoriaPublicaViewSet, basename='log-auditoria')

app_name = 'auditoria_publica'

urlpatterns = [
    path('', include(router.urls)),
]
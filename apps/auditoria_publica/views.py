from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import LogAuditoriaPublica
from .serializers import LogAuditoriaPublicaSerializer

class LogAuditoriaPublicaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet para visualização de logs de infraestrutura SOTARQ.
    Rigor: Apenas leitura permitida. Exclusão e edição proibidas.
    """
    queryset = LogAuditoriaPublica.objects.all()
    serializer_class = LogAuditoriaPublicaSerializer
    
    # Rigor: Apenas superusuários globais (você) devem ver estes logs
    permission_classes = [permissions.IsAdminUser]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tipo_evento', 'nivel', 'empresa_relacionada']
    search_fields = ['acao', 'ip_address', 'usuario__username']
    ordering_fields = ['created_at', 'nivel']
    ordering = ['-created_at']
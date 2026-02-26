from rest_framework import serializers
from .models import LogAuditoriaPublica

class LogAuditoriaPublicaSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.CharField(source='usuario.username', read_only=True)
    empresa_nome = serializers.CharField(source='empresa_relacionada.nome', read_only=True)
    tipo_display = serializers.CharField(source='get_tipo_evento_display', read_only=True)
    nivel_display = serializers.CharField(source='get_nivel_display', read_only=True)

    class Meta:
        model = LogAuditoriaPublica
        fields = [
            'id', 'created_at', 'usuario', 'usuario_nome', 
            'empresa_relacionada', 'empresa_nome', 'tipo_evento', 
            'tipo_display', 'nivel', 'nivel_display', 'acao', 
            'dados_contexto', 'ip_address', 'user_agent'
        ]
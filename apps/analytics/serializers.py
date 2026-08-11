# apps/analytics/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from .models import (
    EventoAnalytics, AuditoriaAlteracao, AlertaInteligente, 
    NotificacaoAlerta, DashboardPersonalizado
)


class EventoAnalyticsSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.SerializerMethodField()
    categoria_display = serializers.CharField(source='get_categoria_display', read_only=True)
    timestamp_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = EventoAnalytics
        fields = [
            'id', 'categoria', 'categoria_display', 'acao', 'label', 
            'propriedades', 'valor', 'ip_address', 'user_agent', 
            'url', 'referrer', 'pais', 'cidade', 'timestamp', 
            'timestamp_formatted', 'usuario', 'usuario_nome'
        ]
        read_only_fields = ['id', 'timestamp', 'ip_address', 'user_agent']
    
    def get_usuario_nome(self, obj):
        if obj.usuario:
            return obj.usuario.get_full_name() or obj.usuario.username
        return 'Anônimo'
    
    def get_timestamp_formatted(self, obj):
        return obj.timestamp.strftime('%d/%m/%Y %H:%M:%S')
    
    def validate_categoria(self, value):
        valid_categories = [choice[0] for choice in EventoAnalytics.CATEGORIA_CHOICES]
        if value not in valid_categories:
            raise serializers.ValidationError(f'Categoria deve ser uma das opções: {valid_categories}')
        return value
    
    def validate_acao(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError('Ação é obrigatória')
        if len(value) > 100:
            raise serializers.ValidationError('Ação deve ter no máximo 100 caracteres')
        return value.strip()


class AuditoriaAlteracaoSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.SerializerMethodField()
    content_type_name = serializers.SerializerMethodField()
    tipo_operacao_display = serializers.CharField(source='get_tipo_operacao_display', read_only=True)
    timestamp_formatted = serializers.SerializerMethodField()
    campos_alterados_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditoriaAlteracao
        fields = [
            'id', 'usuario', 'usuario_nome', 'content_type', 'content_type_name',
            'object_id', 'tipo_operacao', 'tipo_operacao_display', 
            'dados_anteriores', 'dados_posteriores', 'campos_alterados',
            'campos_alterados_count', 'motivo', 'ip_address', 
            'user_agent', 'timestamp', 'timestamp_formatted'
        ]
        read_only_fields = ['id', 'timestamp']
    
    def get_usuario_nome(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username
    
    def get_content_type_name(self, obj):
        return f"{obj.content_type.app_label}.{obj.content_type.model}"
    
    def get_timestamp_formatted(self, obj):
        return obj.timestamp.strftime('%d/%m/%Y %H:%M:%S')
    
    def get_campos_alterados_count(self, obj):
        return len(obj.campos_alterados) if obj.campos_alterados else 0


class NotificacaoAlertaSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.SerializerMethodField()
    enviada_em_formatted = serializers.SerializerMethodField()
    lida_em_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = NotificacaoAlerta
        fields = [
            'id', 'usuario', 'usuario_nome', 'enviada', 'lida',
            'via_email', 'via_sistema', 'via_whatsapp',
            'enviada_em', 'enviada_em_formatted', 'lida_em', 'lida_em_formatted'
        ]
        read_only_fields = ['id', 'enviada_em', 'lida_em']
    
    def get_usuario_nome(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username
    
    def get_enviada_em_formatted(self, obj):
        return obj.enviada_em.strftime('%d/%m/%Y %H:%M:%S') if obj.enviada_em else None
    
    def get_lida_em_formatted(self, obj):
        return obj.lida_em.strftime('%d/%m/%Y %H:%M:%S') if obj.lida_em else None


class AlertaInteligenteSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    prioridade_display = serializers.CharField(source='get_prioridade_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_at_formatted = serializers.SerializerMethodField()
    resolvido_em_formatted = serializers.SerializerMethodField()
    resolvido_por_nome = serializers.SerializerMethodField()
    notificacoes = NotificacaoAlertaSerializer(source='notificacaoalerta_set', many=True, read_only=True)
    usuarios_notificados_count = serializers.SerializerMethodField()
    tempo_resolucao = serializers.SerializerMethodField()
    
    class Meta:
        model = AlertaInteligente
        fields = [
            'id', 'tipo', 'tipo_display', 'prioridade', 'prioridade_display',
            'status', 'status_display', 'titulo', 'mensagem', 'dados_contexto',
            'acoes_sugeridas', 'created_at', 'created_at_formatted',
            'resolvido_em', 'resolvido_em_formatted', 'resolvido_por',
            'resolvido_por_nome', 'notificacoes', 'usuarios_notificados_count',
            'tempo_resolucao'
        ]
        read_only_fields = ['id', 'created_at', 'resolvido_em']
    
    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime('%d/%m/%Y %H:%M:%S')
    
    def get_resolvido_em_formatted(self, obj):
        return obj.resolvido_em.strftime('%d/%m/%Y %H:%M:%S') if obj.resolvido_em else None
    
    def get_resolvido_por_nome(self, obj):
        if obj.resolvido_por:
            return obj.resolvido_por.get_full_name() or obj.resolvido_por.username
        return None
    
    def get_usuarios_notificados_count(self, obj):
        return obj.usuarios_notificados.count()
    
    def get_tempo_resolucao(self, obj):
        if obj.resolvido_em and obj.created_at:
            delta = obj.resolvido_em - obj.created_at
            hours = delta.total_seconds() / 3600
            if hours < 1:
                return f"{int(delta.total_seconds() / 60)} minutos"
            elif hours < 24:
                return f"{int(hours)} horas"
            else:
                return f"{int(hours / 24)} dias"
        return None
    
    def validate_titulo(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError('Título é obrigatório')
        if len(value) > 200:
            raise serializers.ValidationError('Título deve ter no máximo 200 caracteres')
        return value.strip()
    
    def validate_mensagem(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError('Mensagem é obrigatória')
        return value.strip()
    
    def validate_acoes_sugeridas(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Ações sugeridas deve ser uma lista')
        return value


class DashboardPersonalizadoSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.SerializerMethodField()
    created_at_formatted = serializers.SerializerMethodField()
    updated_at_formatted = serializers.SerializerMethodField()
    widgets_count = serializers.SerializerMethodField()
    
    class Meta:
        model = DashboardPersonalizado
        fields = [
            'id', 'usuario', 'usuario_nome', 'nome', 'descricao',
            'layout', 'widgets', 'widgets_count', 'filtros_padrao',
            'padrao', 'publico', 'created_at', 'created_at_formatted',
            'updated_at', 'updated_at_formatted'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_usuario_nome(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username
    
    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime('%d/%m/%Y %H:%M:%S')
    
    def get_updated_at_formatted(self, obj):
        return obj.updated_at.strftime('%d/%m/%Y %H:%M:%S')
    
    def get_widgets_count(self, obj):
        return len(obj.widgets) if obj.widgets else 0
    
    def validate_nome(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError('Nome é obrigatório')
        if len(value) > 100:
            raise serializers.ValidationError('Nome deve ter no máximo 100 caracteres')
        return value.strip()
    
    def validate_layout(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Layout deve ser um objeto JSON válido')
        return value
    
    def validate_widgets(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Widgets deve ser uma lista')
        
        # Validar estrutura básica dos widgets
        for widget in value:
            if not isinstance(widget, dict):
                raise serializers.ValidationError('Cada widget deve ser um objeto')
            if 'id' not in widget or 'type' not in widget:
                raise serializers.ValidationError('Cada widget deve ter id e type')
        
        return value
    
    def validate_filtros_padrao(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Filtros padrão deve ser um objeto JSON válido')
        return value
    
    def validate(self, attrs):
        # Validar que apenas um dashboard por usuário pode ser padrão
        if attrs.get('padrao', False):
            user = attrs.get('usuario') or self.instance.usuario if self.instance else None
            
            if user and empresa:
                existing_default = DashboardPersonalizado.objects.filter(
                    usuario=user,
                    padrao=True
                ).exclude(id=self.instance.id if self.instance else None)
                
                if existing_default.exists():
                    raise serializers.ValidationError(
                        'Apenas um dashboard pode ser definido como padrão por usuário'
                    )
        
        return attrs


class EventoAnalyticsCreateSerializer(serializers.ModelSerializer):
    """Serializer simplificado para criação rápida de eventos"""
    
    class Meta:
        model = EventoAnalytics
        fields = [
            'categoria', 'acao', 'label', 'propriedades', 'valor',
            'url', 'referrer', 'pais', 'cidade'
        ]
    
    def validate_categoria(self, value):
        valid_categories = [choice[0] for choice in EventoAnalytics.CATEGORIA_CHOICES]
        if value not in valid_categories:
            raise serializers.ValidationError(f'Categoria inválida. Opções: {valid_categories}')
        return value


class AlertaInteligenteCreateSerializer(serializers.ModelSerializer):
    """Serializer para criação de alertas com validações específicas"""
    usuarios_notificar = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text='Lista de IDs de usuários para notificar'
    )
    
    class Meta:
        model = AlertaInteligente
        fields = [
            'tipo', 'prioridade', 'titulo', 'mensagem', 'dados_contexto',
            'acoes_sugeridas', 'usuarios_notificar'
        ]
    
    def validate_usuarios_notificar(self, value):
        if value:
            # Verificar se todos os usuários existem
            existing_users = User.objects.filter(id__in=value).count()
            if existing_users != len(value):
                raise serializers.ValidationError('Um ou mais usuários não foram encontrados')
        return value
    
    def create(self, validated_data):
        usuarios_notificar = validated_data.pop('usuarios_notificar', [])
        alerta = super().create(validated_data)
        
        # Criar notificações para os usuários
        for user_id in usuarios_notificar:
            try:
                user = User.objects.get(id=user_id)
                NotificacaoAlerta.objects.create(
                    alerta=alerta,
                    usuario=user,
                    via_email=True,
                    via_sistema=True
                )
            except User.DoesNotExist:
                continue
        
        return alerta


class DashboardWidgetSerializer(serializers.Serializer):
    """Serializer para validação de widgets individuais"""
    id = serializers.CharField(max_length=50)
    type = serializers.CharField(max_length=50)
    title = serializers.CharField(max_length=100, required=False)
    position = serializers.DictField(required=False)
    size = serializers.DictField(required=False)
    config = serializers.DictField(required=False)
    
    def validate_type(self, value):
        valid_types = [
            'vendas_hoje', 'top_produtos', 'alertas_ativos', 'eventos_tempo_real',
            'grafico_vendas', 'mapa_usuarios', 'performance', 'metricas'
        ]
        if value not in valid_types:
            raise serializers.ValidationError(f'Tipo de widget inválido. Opções: {valid_types}')
        return value
    
    def validate_position(self, value):
        if value:
            required_keys = ['x', 'y']
            if not all(key in value for key in required_keys):
                raise serializers.ValidationError('Posição deve conter x e y')
            if not all(isinstance(value[key], (int, float)) for key in required_keys):
                raise serializers.ValidationError('Coordenadas devem ser números')
        return value
    
    def validate_size(self, value):
        if value:
            required_keys = ['width', 'height']
            if not all(key in value for key in required_keys):
                raise serializers.ValidationError('Tamanho deve conter width e height')
            if not all(isinstance(value[key], (int, float)) and value[key] > 0 for key in required_keys):
                raise serializers.ValidationError('Dimensões devem ser números positivos')
        return value


class MetricasSerializer(serializers.Serializer):
    """Serializer para dados de métricas"""
    total_eventos = serializers.IntegerField()
    usuarios_unicos = serializers.IntegerField()
    eventos_por_categoria = serializers.ListField(
        child=serializers.DictField()
    )
    eventos_por_dia = serializers.ListField(
        child=serializers.DictField()
    )
    periodo_dias = serializers.IntegerField()


class FiltroEventosSerializer(serializers.Serializer):
    """Serializer para filtros de eventos"""
    categoria = serializers.ChoiceField(
        choices=EventoAnalytics.CATEGORIA_CHOICES,
        required=False
    )
    acao = serializers.CharField(max_length=100, required=False)
    usuario_id = serializers.IntegerField(required=False)
    data_inicio = serializers.DateTimeField(required=False)
    data_fim = serializers.DateTimeField(required=False)
    pais = serializers.CharField(max_length=2, required=False)
    
    def validate(self, attrs):
        data_inicio = attrs.get('data_inicio')
        data_fim = attrs.get('data_fim')
        
        if data_inicio and data_fim and data_inicio >= data_fim:
            raise serializers.ValidationError('Data de início deve ser anterior à data de fim')
        
        return attrs


class FiltroAuditoriaSerializer(serializers.Serializer):
    """Serializer para filtros de auditoria"""
    usuario_id = serializers.IntegerField(required=False)
    tipo_operacao = serializers.ChoiceField(
        choices=AuditoriaAlteracao.TIPO_OPERACAO_CHOICES,
        required=False
    )
    content_type_id = serializers.IntegerField(required=False)
    object_id = serializers.IntegerField(required=False)
    data_inicio = serializers.DateTimeField(required=False)
    data_fim = serializers.DateTimeField(required=False)
    
    def validate(self, attrs):
        data_inicio = attrs.get('data_inicio')
        data_fim = attrs.get('data_fim')
        
        if data_inicio and data_fim and data_inicio >= data_fim:
            raise serializers.ValidationError('Data de início deve ser anterior à data de fim')
        
        return attrs


# apps/analytics/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from datetime import datetime, date, timedelta
import json

from .models import AlertaInteligente, DashboardPersonalizado, EventoAnalytics, AuditoriaAlteracao
from apps.empresas.models import Empresa


Usuario = get_user_model()

class BaseAnalyticsForm(forms.Form):
    """Form base para analytics com métodos comuns"""
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)
        
        # Aplicar classes CSS padrão
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput,
                                       forms.URLInput, forms.PasswordInput, forms.Textarea)):
                field.widget.attrs.update({
                    'class': 'form-control border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': 'form-select border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent'
                })
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'form-check-input rounded border-gray-300 text-blue-600 focus:ring-blue-500'
                })
            elif isinstance(field.widget, (forms.DateInput, forms.DateTimeInput)):
                field.widget.attrs.update({
                    'class': 'form-control border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent'
                })


class AlertaInteligenteForm(BaseAnalyticsForm, forms.ModelForm):
    """Form para criação e edição de alertas inteligentes"""
    
    usuarios_notificar = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Usuários para Notificar'
    )
    
    acoes_sugeridas_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Ações Sugeridas',
        help_text='Digite uma ação por linha'
    )
    
    dados_contexto_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Dados de Contexto (JSON)',
        help_text='JSON com dados adicionais do alerta'
    )
    
    class Meta:
        model = AlertaInteligente
        fields = [
            'tipo', 'prioridade', 'titulo', 'mensagem',
            'acoes_sugeridas_text', 'dados_contexto_json'
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={
                'placeholder': 'Título descritivo do alerta'
            }),
            'mensagem': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Descrição detalhada do problema ou situação'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar usuários da empresa
            self.fields['usuarios_notificar'].queryset = Usuario.objects.filter(
                funcionario__empresa=self.empresa,
                funcionario__ativo=True
            ).order_by('first_name', 'username')
        
        # Valores iniciais para edição
        if self.instance.pk:
            if self.instance.acoes_sugeridas:
                self.fields['acoes_sugeridas_text'].initial = '\n'.join(self.instance.acoes_sugeridas)
            
            if self.instance.dados_contexto:
                self.fields['dados_contexto_json'].initial = json.dumps(
                    self.instance.dados_contexto, indent=2, ensure_ascii=False
                )
        
        # Labels e help texts personalizados
        self.fields['tipo'].label = 'Tipo do Alerta'
        self.fields['prioridade'].label = 'Nível de Prioridade'
        self.fields['titulo'].label = 'Título do Alerta'
        self.fields['mensagem'].label = 'Mensagem Detalhada'
    
    def clean_titulo(self):
        titulo = self.cleaned_data.get('titulo')
        if titulo:
            titulo = titulo.strip()
            if len(titulo) < 5:
                raise ValidationError('Título deve ter pelo menos 5 caracteres.')
            if len(titulo) > 200:
                raise ValidationError('Título deve ter no máximo 200 caracteres.')
        return titulo
    
    def clean_mensagem(self):
        mensagem = self.cleaned_data.get('mensagem')
        if mensagem:
            mensagem = mensagem.strip()
            if len(mensagem) < 10:
                raise ValidationError('Mensagem deve ter pelo menos 10 caracteres.')
        return mensagem
    
    def clean_dados_contexto_json(self):
        dados_json = self.cleaned_data.get('dados_contexto_json')
        if dados_json:
            try:
                dados = json.loads(dados_json)
                if not isinstance(dados, dict):
                    raise ValidationError('Dados de contexto deve ser um objeto JSON válido.')
                return dados
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return {}
    
    def clean_acoes_sugeridas_text(self):
        acoes_text = self.cleaned_data.get('acoes_sugeridas_text')
        if acoes_text:
            acoes = [acao.strip() for acao in acoes_text.split('\n') if acao.strip()]
            if len(acoes) > 10:
                raise ValidationError('Máximo de 10 ações sugeridas.')
            return acoes
        return []
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Processar dados JSON
        instance.dados_contexto = self.cleaned_data.get('dados_contexto_json', {})
        instance.acoes_sugeridas = self.cleaned_data.get('acoes_sugeridas_text', [])
        
        if commit:
            instance.save()
            
            # Processar usuários para notificar
            usuarios_notificar = self.cleaned_data.get('usuarios_notificar', [])
            if usuarios_notificar:
                from .models import NotificacaoAlerta
                for usuario in usuarios_notificar:
                    NotificacaoAlerta.objects.get_or_create(
                        alerta=instance,
                        usuario=usuario,
                        defaults={
                            'via_email': True,
                            'via_sistema': True
                        }
                    )
        
        return instance


class DashboardPersonalizadoForm(BaseAnalyticsForm, forms.ModelForm):
    """Form para criação e edição de dashboards personalizados"""
    
    widgets_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10}),
        required=False,
        label='Widgets (JSON)',
        help_text='Configuração dos widgets em formato JSON'
    )
    
    layout_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        required=False,
        label='Layout (JSON)',
        help_text='Configuração do layout em formato JSON'
    )
    
    filtros_padrao_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Filtros Padrão (JSON)',
        help_text='Filtros padrão aplicados ao dashboard'
    )
    
    class Meta:
        model = DashboardPersonalizado
        fields = [
            'nome', 'descricao', 'padrao', 'publico',
            'widgets_json', 'layout_json', 'filtros_padrao_json'
        ]
        widgets = {
            'nome': forms.TextInput(attrs={
                'placeholder': 'Nome do dashboard'
            }),
            'descricao': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Descrição opcional do dashboard'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Valores iniciais para edição
        if self.instance.pk:
            if self.instance.widgets:
                self.fields['widgets_json'].initial = json.dumps(
                    self.instance.widgets, indent=2, ensure_ascii=False
                )
            
            if self.instance.layout:
                self.fields['layout_json'].initial = json.dumps(
                    self.instance.layout, indent=2, ensure_ascii=False
                )
            
            if self.instance.filtros_padrao:
                self.fields['filtros_padrao_json'].initial = json.dumps(
                    self.instance.filtros_padrao, indent=2, ensure_ascii=False
                )
        
        # Labels e help texts
        self.fields['nome'].label = 'Nome do Dashboard'
        self.fields['descricao'].label = 'Descrição'
        self.fields['padrao'].label = 'Dashboard Padrão'
        self.fields['publico'].label = 'Dashboard Público'
        self.fields['padrao'].help_text = 'Marque para definir como dashboard padrão'
        self.fields['publico'].help_text = 'Marque para tornar visível para outros usuários'
    
    def clean_nome(self):
        nome = self.cleaned_data.get('nome')
        if nome:
            nome = nome.strip()
            if len(nome) < 3:
                raise ValidationError('Nome deve ter pelo menos 3 caracteres.')
            if len(nome) > 100:
                raise ValidationError('Nome deve ter no máximo 100 caracteres.')
            
            # Verificar duplicatas para o mesmo usuário
            if self.usuario:
                existing = DashboardPersonalizado.objects.filter(
                    usuario=self.usuario,
                    empresa=self.empresa,
                    nome__iexact=nome
                )
                if self.instance.pk:
                    existing = existing.exclude(pk=self.instance.pk)
                
                if existing.exists():
                    raise ValidationError('Você já possui um dashboard com este nome.')
        
        return nome
    
    def clean_widgets_json(self):
        widgets_json = self.cleaned_data.get('widgets_json')
        if widgets_json:
            try:
                widgets = json.loads(widgets_json)
                if not isinstance(widgets, list):
                    raise ValidationError('Widgets deve ser uma lista JSON.')
                
                # Validar estrutura básica dos widgets
                for i, widget in enumerate(widgets):
                    if not isinstance(widget, dict):
                        raise ValidationError(f'Widget {i+1} deve ser um objeto.')
                    
                    required_fields = ['id', 'type']
                    for field in required_fields:
                        if field not in widget:
                            raise ValidationError(f'Widget {i+1} deve ter o campo "{field}".')
                
                return widgets
            except json.JSONDecodeError as e:
                raise ValidationError(f'JSON de widgets inválido: {e}')
        return []
    
    def clean_layout_json(self):
        layout_json = self.cleaned_data.get('layout_json')
        if layout_json:
            try:
                layout = json.loads(layout_json)
                if not isinstance(layout, dict):
                    raise ValidationError('Layout deve ser um objeto JSON.')
                return layout
            except json.JSONDecodeError as e:
                raise ValidationError(f'JSON de layout inválido: {e}')
        return {}
    
    def clean_filtros_padrao_json(self):
        filtros_json = self.cleaned_data.get('filtros_padrao_json')
        if filtros_json:
            try:
                filtros = json.loads(filtros_json)
                if not isinstance(filtros, dict):
                    raise ValidationError('Filtros padrão deve ser um objeto JSON.')
                return filtros
            except json.JSONDecodeError as e:
                raise ValidationError(f'JSON de filtros inválido: {e}')
        return {}
    
    def clean(self):
        cleaned_data = super().clean()
        padrao = cleaned_data.get('padrao', False)
        
        # Validar que apenas um dashboard pode ser padrão por usuário
        if padrao and self.usuario and self.empresa:
            existing_default = DashboardPersonalizado.objects.filter(
                usuario=self.usuario,
                empresa=self.empresa,
                padrao=True
            )
            
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            
            if existing_default.exists():
                raise ValidationError({
                    'padrao': 'Você já possui um dashboard padrão. Desmarque o outro primeiro.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Processar dados JSON
        instance.widgets = self.cleaned_data.get('widgets_json', [])
        instance.layout = self.cleaned_data.get('layout_json', {})
        instance.filtros_padrao = self.cleaned_data.get('filtros_padrao_json', {})
        
        if commit:
            instance.save()
        
        return instance


class FiltroEventosForm(BaseAnalyticsForm):
    """Form para filtros de eventos analytics"""
    
    categoria = forms.ChoiceField(
        choices=[('', 'Todas as categorias')] + EventoAnalytics.CATEGORIA_CHOICES,
        required=False,
        label='Categoria'
    )
    
    acao = forms.CharField(
        max_length=100,
        required=False,
        label='Ação',
        widget=forms.TextInput(attrs={'placeholder': 'Filtrar por ação'})
    )
    
    usuarios_notificados = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        required=False,
        empty_label='Todos os usuários',
        label='Notificar Utilizadores Específicos'
    )
    
    data_inicio = forms.DateField(
        required=False,
        label='Data Início',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    data_fim = forms.DateField(
        required=False,
        label='Data Fim',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    periodo_predefinido = forms.ChoiceField(
        choices=[
            ('', 'Período personalizado'),
            ('hoje', 'Hoje'),
            ('ontem', 'Ontem'),
            ('7_dias', 'Últimos 7 dias'),
            ('30_dias', 'Últimos 30 dias'),
            ('90_dias', 'Últimos 90 dias'),
        ],
        required=False,
        label='Período Pré-definido'
    )
    
    pais = forms.CharField(
        max_length=2,
        required=False,
        label='País (código)',
        widget=forms.TextInput(attrs={'placeholder': 'Ex: BR, US, PT'})
    )
    
    cidade = forms.CharField(
        max_length=100,
        required=False,
        label='Cidade',
        widget=forms.TextInput(attrs={'placeholder': 'Nome da cidade'})
    )
    
    valor_minimo = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        label='Valor Mínimo',
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )
    
    valor_maximo = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        label='Valor Máximo',
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar usuários da empresa
            self.fields['usuario'].queryset = Usuario.objects.filter(
                funcionario__empresa=self.empresa
            ).order_by('first_name', 'username')
    
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        periodo_predefinido = cleaned_data.get('periodo_predefinido')
        valor_minimo = cleaned_data.get('valor_minimo')
        valor_maximo = cleaned_data.get('valor_maximo')
        
        # Processar período pré-definido
        if periodo_predefinido:
            hoje = date.today()
            if periodo_predefinido == 'hoje':
                cleaned_data['data_inicio'] = hoje
                cleaned_data['data_fim'] = hoje
            elif periodo_predefinido == 'ontem':
                ontem = hoje - timedelta(days=1)
                cleaned_data['data_inicio'] = ontem
                cleaned_data['data_fim'] = ontem
            elif periodo_predefinido == '7_dias':
                cleaned_data['data_inicio'] = hoje - timedelta(days=7)
                cleaned_data['data_fim'] = hoje
            elif periodo_predefinido == '30_dias':
                cleaned_data['data_inicio'] = hoje - timedelta(days=30)
                cleaned_data['data_fim'] = hoje
            elif periodo_predefinido == '90_dias':
                cleaned_data['data_inicio'] = hoje - timedelta(days=90)
                cleaned_data['data_fim'] = hoje
        
        # Validar datas
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise ValidationError('Data de início deve ser anterior à data de fim.')
            
            # Limite máximo de 1 ano
            if (data_fim - data_inicio).days > 365:
                raise ValidationError('Período máximo de consulta é de 1 ano.')
        
        # Validar valores
        if valor_minimo and valor_maximo:
            if valor_minimo > valor_maximo:
                raise ValidationError('Valor mínimo deve ser menor que o valor máximo.')
        
        return cleaned_data


class FiltroAuditoriaForm(BaseAnalyticsForm):
    """Form para filtros de auditoria"""
    
    usuario = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        required=False,
        empty_label='Todos os usuários',
        label='Usuário'
    )
    
    tipo_operacao = forms.ChoiceField(
        choices=[('', 'Todas as operações')] + AuditoriaAlteracao.TIPO_OPERACAO_CHOICES,
        required=False,
        label='Tipo de Operação'
    )
    
    content_type = forms.ModelChoiceField(
        queryset=ContentType.objects.none(),
        required=False,
        empty_label='Todos os tipos de objeto',
        label='Tipo de Objeto'
    )
    
    object_id = forms.IntegerField(
        required=False,
        label='ID do Objeto',
        widget=forms.NumberInput(attrs={'placeholder': 'ID específico do objeto'})
    )
    
    data_inicio = forms.DateTimeField(
        required=False,
        label='Data/Hora Início',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    
    data_fim = forms.DateTimeField(
        required=False,
        label='Data/Hora Fim',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    
    periodo_predefinido = forms.ChoiceField(
        choices=[
            ('', 'Período personalizado'),
            ('1_hora', 'Última hora'),
            ('24_horas', 'Últimas 24 horas'),
            ('7_dias', 'Últimos 7 dias'),
            ('30_dias', 'Últimos 30 dias'),
        ],
        required=False,
        label='Período Pré-definido'
    )
    
    motivo = forms.CharField(
        max_length=200,
        required=False,
        label='Motivo',
        widget=forms.TextInput(attrs={'placeholder': 'Buscar no motivo da alteração'})
    )
    
    ip_address = forms.GenericIPAddressField(
        required=False,
        label='Endereço IP',
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 192.168.1.1'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar usuários da empresa
            self.fields['usuario'].queryset = Usuario.objects.filter(
                funcionario__empresa=self.empresa
            ).order_by('first_name', 'username')
            
            # Filtrar content types que têm auditorias na empresa
            self.fields['content_type'].queryset = ContentType.objects.filter(
                auditoriaaltercao__empresa=self.empresa
            ).distinct().order_by('model')
    
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        periodo_predefinido = cleaned_data.get('periodo_predefinido')
        
        # Processar período pré-definido
        if periodo_predefinido:
            agora = datetime.now()
            if periodo_predefinido == '1_hora':
                cleaned_data['data_inicio'] = agora - timedelta(hours=1)
                cleaned_data['data_fim'] = agora
            elif periodo_predefinido == '24_horas':
                cleaned_data['data_inicio'] = agora - timedelta(hours=24)
                cleaned_data['data_fim'] = agora
            elif periodo_predefinido == '7_dias':
                cleaned_data['data_inicio'] = agora - timedelta(days=7)
                cleaned_data['data_fim'] = agora
            elif periodo_predefinido == '30_dias':
                cleaned_data['data_inicio'] = agora - timedelta(days=30)
                cleaned_data['data_fim'] = agora
        
        # Validar datas
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise ValidationError('Data de início deve ser anterior à data de fim.')
            
            # Limite máximo de 6 meses para auditoria
            if (data_fim - data_inicio).days > 180:
                raise ValidationError('Período máximo de consulta de auditoria é de 6 meses.')
        
        return cleaned_data


class ExportarDadosForm(BaseAnalyticsForm):
    """Form para exportação de dados"""
    
    FORMATO_CHOICES = [
        ('csv', 'CSV'),
        ('xlsx', 'Excel (XLSX)'),
        ('json', 'JSON'),
    ]
    
    TIPO_DADOS_CHOICES = [
        ('eventos', 'Eventos Analytics'),
        ('auditoria', 'Auditoria'),
        ('alertas', 'Alertas'),
        ('dashboards', 'Dashboards'),
    ]
    
    tipo_dados = forms.ChoiceField(
        choices=TIPO_DADOS_CHOICES,
        label='Tipo de Dados'
    )
    
    formato = forms.ChoiceField(
        choices=FORMATO_CHOICES,
        label='Formato do Arquivo'
    )
    
    data_inicio = forms.DateField(
        required=False,
        label='Data Início',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    data_fim = forms.DateField(
        required=False,
        label='Data Fim',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    incluir_dados_sensíveis = forms.BooleanField(
        required=False,
        label='Incluir Dados Sensíveis',
        help_text='IPs, User Agents e dados pessoais'
    )
    
    limite_registros = forms.IntegerField(
        min_value=1,
        max_value=100000,
        initial=10000,
        label='Limite de Registros',
        help_text='Máximo 100.000 registros'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise ValidationError('Data de início deve ser anterior à data de fim.')
        
        return cleaned_data


class ConfiguracaoTrackingForm(BaseAnalyticsForm):
    """Form para configurações de tracking"""
    
    ativar_tracking_navegacao = forms.BooleanField(
        required=False,
        label='Ativar Tracking de Navegação',
        help_text='Rastrear cliques, visualizações de página, etc.'
    )
    
    ativar_tracking_vendas = forms.BooleanField(
        required=False,
        label='Ativar Tracking de Vendas',
        help_text='Rastrear eventos relacionados a vendas'
    )
    
    ativar_tracking_erros = forms.BooleanField(
        required=False,
        label='Ativar Tracking de Erros',
        help_text='Rastrear erros da aplicação'
    )
    
    tracking_anonimo = forms.BooleanField(
        required=False,
        label='Permitir Tracking Anônimo',
        help_text='Rastrear usuários não logados'
    )
    
    retention_dias_eventos = forms.IntegerField(
        min_value=30,
        max_value=365,
        initial=90,
        label='Retenção de Eventos (dias)',
        help_text='Quantos dias manter os eventos armazenados'
    )
    
    retention_dias_auditoria = forms.IntegerField(
        min_value=90,
        max_value=2555,  # ~7 anos
        initial=365,
        label='Retenção de Auditoria (dias)',
        help_text='Quantos dias manter a auditoria armazenada'
    )
    
    ips_excluidos = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='IPs Excluídos do Tracking',
        help_text='Um IP por linha. Ex: 192.168.1.1'
    )
    
    def clean_ips_excluidos(self):
        ips_text = self.cleaned_data.get('ips_excluidos', '')
        ips = []
        
        if ips_text:
            for line in ips_text.split('\n'):
                ip = line.strip()
                if ip:
                    try:
                        # Validar IP
                        import ipaddress
                        ipaddress.ip_address(ip)
                        ips.append(ip)
                    except ValueError:
                        raise ValidationError(f'IP inválido: {ip}')
        
        return ips

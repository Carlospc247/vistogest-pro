# apps/relatorios/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from datetime import date, datetime, timedelta
import json

from .models import (
    TipoRelatorio, RelatorioGerado, MetricaKPI, DashboardConfig,
    AnaliseVendas, AnaliseEstoque, AnaliseClientes, AlertaGerencial,
    TemplateRelatorio, Relatorio, AgendamentoRelatorio
)
from apps.empresas.models import Empresa
from apps.produtos.models import Categoria
from apps.funcionarios.models import Funcionario, Cargo
from apps.clientes.models import Cliente


class BaseRelatoriosForm(forms.Form):
    """Form base para relatórios com métodos comuns"""
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)
        
        # Aplicar classes CSS padrão
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput,
                                       forms.URLInput, forms.PasswordInput, forms.Textarea)):
                field.widget.attrs.update({
                    'class': 'form-control'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': 'form-select'
                })
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'form-check-input'
                })
            elif isinstance(field.widget, (forms.DateInput, forms.DateTimeInput)):
                field.widget.attrs.update({
                    'class': 'form-control'
                })


class TipoRelatorioForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para criação e edição de tipos de relatório"""
    
    parametros_schema_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10}),
        required=False,
        label='Schema de Parâmetros (JSON)',
        help_text='Defina os parâmetros aceitos pelo relatório em formato JSON'
    )
    
    class Meta:
        model = TipoRelatorio
        fields = [
            'codigo', 'nome', 'descricao', 'categoria', 'periodicidade',
            'publico', 'requer_aprovacao', 'ativo', 'ordem_exibicao',
            'parametros_schema_text', 'query_sql', 'template_html',
            'cargos_permitidos'
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 4}),
            'query_sql': forms.Textarea(attrs={'rows': 8}),
            'template_html': forms.Textarea(attrs={'rows': 10}),
            'cargos_permitidos': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar cargos da empresa
            self.fields['cargos_permitidos'].queryset = Cargo.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Valores iniciais para edição
        if self.instance.pk and self.instance.parametros_schema:
            self.fields['parametros_schema_text'].initial = json.dumps(
                self.instance.parametros_schema, indent=2, ensure_ascii=False
            )
    
    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo')
        if codigo:
            codigo = codigo.upper().strip()
            
            # Verificar se já existe
            existing = TipoRelatorio.objects.filter(codigo=codigo)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError('Já existe um tipo de relatório com este código.')
        
        return codigo
    
    def clean_parametros_schema_text(self):
        schema_text = self.cleaned_data.get('parametros_schema_text')
        if schema_text:
            try:
                schema = json.loads(schema_text)
                if not isinstance(schema, dict):
                    raise ValidationError('Schema deve ser um objeto JSON válido.')
                return schema
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return {}
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.parametros_schema = self.cleaned_data.get('parametros_schema_text', {})
        
        if commit:
            instance.save()
            self.save_m2m()
        
        return instance


class RelatorioGeradoForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para geração de relatórios"""
    
    parametros_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        required=False,
        label='Parâmetros (JSON)',
        help_text='Parâmetros específicos para este relatório'
    )
    
    class Meta:
        model = RelatorioGerado
        fields = [
            'tipo_relatorio', 'formato', 'data_inicio', 'data_fim',
            'parametros_text', 'lojas', 'categorias', 'funcionarios'
        ]
        widgets = {
            'data_inicio': forms.DateInput(attrs={'type': 'date'}),
            'data_fim': forms.DateInput(attrs={'type': 'date'}),
            'lojas': forms.CheckboxSelectMultiple(),
            'categorias': forms.CheckboxSelectMultiple(),
            'funcionarios': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar por empresa
            self.fields['tipo_relatorio'].queryset = TipoRelatorio.objects.filter(
                ativo=True
            )
            self.fields['lojas'].queryset = self.empresa.lojas.filter(ativa=True)
            self.fields['categorias'].queryset = Categoria.objects.filter(
                empresa=self.empresa, ativa=True
            )
            self.fields['funcionarios'].queryset = Funcionario.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Valores padrão
        if not self.instance.pk:
            # Últimos 30 dias por padrão
            hoje = date.today()
            self.fields['data_fim'].initial = hoje
            self.fields['data_inicio'].initial = hoje - timedelta(days=30)
    
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise ValidationError('Data de início deve ser anterior à data de fim.')
            
            # Verificar período máximo (1 ano)
            if (data_fim - data_inicio).days > 365:
                raise ValidationError('Período máximo permitido é de 1 ano.')
        
        return cleaned_data
    
    def clean_parametros_text(self):
        parametros_text = self.cleaned_data.get('parametros_text')
        if parametros_text:
            try:
                parametros = json.loads(parametros_text)
                if not isinstance(parametros, dict):
                    raise ValidationError('Parâmetros devem ser um objeto JSON válido.')
                return parametros
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return {}
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.parametros = self.cleaned_data.get('parametros_text', {})
        instance.empresa = self.empresa
        instance.solicitante = self.usuario
        
        if commit:
            instance.save()
            self.save_m2m()
        
        return instance


class MetricaKPIForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para criação de métricas KPI"""
    
    detalhes_calculo_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        required=False,
        label='Detalhes do Cálculo (JSON)',
        help_text='Informações detalhadas sobre como a métrica foi calculada'
    )
    
    class Meta:
        model = MetricaKPI
        fields = [
            'codigo', 'nome', 'descricao', 'tipo_metrica', 'periodo',
            'data_referencia', 'valor_atual', 'valor_anterior', 'valor_meta',
            'unidade_medida', 'formato_exibicao', 'loja', 'categoria',
            'detalhes_calculo_text'
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'data_referencia': forms.DateInput(attrs={'type': 'date'}),
            'valor_atual': forms.NumberInput(attrs={'step': '0.01'}),
            'valor_anterior': forms.NumberInput(attrs={'step': '0.01'}),
            'valor_meta': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['loja'].queryset = self.empresa.lojas.filter(ativa=True)
            self.fields['categoria'].queryset = Categoria.objects.filter(
                empresa=self.empresa, ativa=True
            )
        
        # Valores iniciais
        if not self.instance.pk:
            self.fields['data_referencia'].initial = date.today()
        
        # Valores iniciais para edição
        if self.instance.pk and self.instance.detalhes_calculo:
            self.fields['detalhes_calculo_text'].initial = json.dumps(
                self.instance.detalhes_calculo, indent=2, ensure_ascii=False
            )
    
    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo')
        if codigo:
            codigo = codigo.upper().strip()
            
            # Verificar duplicatas considerando empresa, loja e data
            data_referencia = self.cleaned_data.get('data_referencia')
            loja = self.cleaned_data.get('loja')
            
            if data_referencia:
                existing = MetricaKPI.objects.filter(
                    codigo=codigo,
                    empresa=self.empresa,
                    data_referencia=data_referencia,
                    loja=loja
                )
                
                if self.instance.pk:
                    existing = existing.exclude(pk=self.instance.pk)
                
                if existing.exists():
                    raise ValidationError(
                        'Já existe uma métrica com este código para esta data e loja.'
                    )
        
        return codigo
    
    def clean_detalhes_calculo_text(self):
        detalhes_text = self.cleaned_data.get('detalhes_calculo_text')
        if detalhes_text:
            try:
                detalhes = json.loads(detalhes_text)
                if not isinstance(detalhes, dict):
                    raise ValidationError('Detalhes devem ser um objeto JSON válido.')
                return detalhes
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return {}
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.detalhes_calculo = self.cleaned_data.get('detalhes_calculo_text', {})
        instance.empresa = self.empresa
        
        if commit:
            instance.save()
        
        return instance


class DashboardConfigForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para configuração de dashboards"""
    
    configuracao_layout_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 8}),
        required=False,
        label='Configuração do Layout (JSON)',
        help_text='Configuração do layout dos widgets'
    )
    
    widgets_incluidos_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10}),
        required=False,
        label='Widgets Incluídos (JSON)',
        help_text='Lista de widgets incluídos no dashboard'
    )
    
    class Meta:
        model = DashboardConfig
        fields = [
            'nome', 'descricao', 'codigo', 'publico', 'dashboard_padrao',
            'auto_refresh', 'intervalo_refresh', 'ativo',
            'configuracao_layout_text', 'widgets_incluidos_text'
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'intervalo_refresh': forms.NumberInput(attrs={'min': '30', 'step': '30'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Valores iniciais para edição
        if self.instance.pk:
            if self.instance.configuracao_layout:
                self.fields['configuracao_layout_text'].initial = json.dumps(
                    self.instance.configuracao_layout, indent=2, ensure_ascii=False
                )
            
            if self.instance.widgets_incluidos:
                self.fields['widgets_incluidos_text'].initial = json.dumps(
                    self.instance.widgets_incluidos, indent=2, ensure_ascii=False
                )
    
    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo')
        if codigo:
            codigo = codigo.lower().strip()
            
            # Verificar duplicatas para o mesmo usuário
            existing = DashboardConfig.objects.filter(
                codigo=codigo,
                usuario=self.usuario,
                empresa=self.empresa
            )
            
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError('Você já possui um dashboard com este código.')
        
        return codigo
    
    def clean_configuracao_layout_text(self):
        layout_text = self.cleaned_data.get('configuracao_layout_text')
        if layout_text:
            try:
                layout = json.loads(layout_text)
                if not isinstance(layout, dict):
                    raise ValidationError('Layout deve ser um objeto JSON válido.')
                return layout
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return {}
    
    def clean_widgets_incluidos_text(self):
        widgets_text = self.cleaned_data.get('widgets_incluidos_text')
        if widgets_text:
            try:
                widgets = json.loads(widgets_text)
                if not isinstance(widgets, list):
                    raise ValidationError('Widgets devem ser uma lista JSON válida.')
                return widgets
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return []
    
    def clean(self):
        cleaned_data = super().clean()
        dashboard_padrao = cleaned_data.get('dashboard_padrao', False)
        
        # Verificar se já existe um dashboard padrão para o usuário
        if dashboard_padrao and self.usuario and self.empresa:
            existing_default = DashboardConfig.objects.filter(
                usuario=self.usuario,
                empresa=self.empresa,
                dashboard_padrao=True
            )
            
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            
            if existing_default.exists():
                raise ValidationError({
                    'dashboard_padrao': 'Você já possui um dashboard padrão. Desmarque o outro primeiro.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.configuracao_layout = self.cleaned_data.get('configuracao_layout_text', {})
        instance.widgets_incluidos = self.cleaned_data.get('widgets_incluidos_text', [])
        instance.usuario = self.usuario
        instance.empresa = self.empresa
        
        if commit:
            instance.save()
        
        return instance


class FiltroAnaliseVendasForm(BaseRelatoriosForm):
    """Form para filtros de análise de vendas"""
    
    dimensao = forms.ChoiceField(
        choices=AnaliseVendas.DIMENSAO_CHOICES,
        label='Dimensão da Análise'
    )
    
    data_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data Início'
    )
    
    data_fim = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data Fim'
    )
    
    loja = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Todas as lojas',
        label='Loja'
    )
    
    categoria = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Todas as categorias',
        label='Categoria'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['loja'].queryset = self.empresa.lojas.filter(ativa=True)
            self.fields['categoria'].queryset = Categoria.objects.filter(
                empresa=self.empresa, ativa=True
            )
        
        # Valores padrão
        hoje = date.today()
        self.fields['data_fim'].initial = hoje
        self.fields['data_inicio'].initial = hoje - timedelta(days=30)
    
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise ValidationError('Data de início deve ser anterior à data de fim.')
            
            # Limite máximo de 2 anos
            if (data_fim - data_inicio).days > 730:
                raise ValidationError('Período máximo para análise é de 2 anos.')
        
        return cleaned_data


class FiltroAnaliseEstoqueForm(BaseRelatoriosForm):
    """Form para filtros de análise de estoque"""
    
    tipo_analise = forms.ChoiceField(
        choices=AnaliseEstoque.TIPO_ANALISE_CHOICES,
        label='Tipo de Análise'
    )
    
    data_referencia = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data de Referência'
    )
    
    periodo_analise_dias = forms.IntegerField(
        min_value=30,
        max_value=365,
        initial=90,
        label='Período de Análise (dias)',
        help_text='Quantos dias considerar para o cálculo'
    )
    
    loja = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Todas as lojas',
        label='Loja'
    )
    
    categoria = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Todas as categorias',
        label='Categoria'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['loja'].queryset = self.empresa.lojas.filter(ativa=True)
            self.fields['categoria'].queryset = Categoria.objects.filter(
                empresa=self.empresa, ativa=True
            )
        
        # Valor padrão
        self.fields['data_referencia'].initial = date.today()


class FiltroAnaliseClientesForm(BaseRelatoriosForm):
    """Form para filtros de análise de clientes"""
    
    tipo_segmentacao = forms.ChoiceField(
        choices=AnaliseClientes.TIPO_SEGMENTACAO_CHOICES,
        label='Tipo de Segmentação'
    )
    
    data_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data Início'
    )
    
    data_fim = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data Fim'
    )
    
    loja = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Todas as lojas',
        label='Loja'
    )
    
    incluir_inativos = forms.BooleanField(
        required=False,
        label='Incluir Clientes Inativos',
        help_text='Incluir clientes que não compraram no período'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['loja'].queryset = self.empresa.lojas.filter(ativa=True)
        
        # Valores padrão (últimos 6 meses)
        hoje = date.today()
        self.fields['data_fim'].initial = hoje
        self.fields['data_inicio'].initial = hoje - timedelta(days=180)
    
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise ValidationError('Data de início deve ser anterior à data de fim.')
            
            # Limite mínimo de 30 dias
            if (data_fim - data_inicio).days < 30:
                raise ValidationError('Período mínimo para análise de clientes é de 30 dias.')
            
            # Limite máximo de 3 anos
            if (data_fim - data_inicio).days > 1095:
                raise ValidationError('Período máximo para análise de clientes é de 3 anos.')
        
        return cleaned_data


class AlertaGerencialForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para criação de alertas gerenciais"""
    
    acoes_recomendadas_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Ações Recomendadas',
        help_text='Digite uma ação por linha'
    )
    
    class Meta:
        model = AlertaGerencial
        fields = [
            'tipo_alerta', 'prioridade', 'titulo', 'descricao',
            'valor_atual', 'valor_esperado', 'data_referencia',
            'loja', 'produto', 'cliente', 'funcionario',
            'acoes_recomendadas_text'
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 4}),
            'data_referencia': forms.DateInput(attrs={'type': 'date'}),
            'valor_atual': forms.NumberInput(attrs={'step': '0.01'}),
            'valor_esperado': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['loja'].queryset = self.empresa.lojas.filter(ativa=True)
            self.fields['funcionario'].queryset = Funcionario.objects.filter(
                empresa=self.empresa, ativo=True
            )
            # Produtos e clientes da empresa também podem ser filtrados se necessário
        
        # Valor padrão
        if not self.instance.pk:
            self.fields['data_referencia'].initial = date.today()
        
        # Valores iniciais para edição
        if self.instance.pk and self.instance.acoes_recomendadas:
            self.fields['acoes_recomendadas_text'].initial = '\n'.join(
                self.instance.acoes_recomendadas
            )
    
    def clean_acoes_recomendadas_text(self):
        acoes_text = self.cleaned_data.get('acoes_recomendadas_text')
        if acoes_text:
            acoes = [acao.strip() for acao in acoes_text.split('\n') if acao.strip()]
            if len(acoes) > 10:
                raise ValidationError('Máximo de 10 ações recomendadas.')
            return acoes
        return []
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.acoes_recomendadas = self.cleaned_data.get('acoes_recomendadas_text', [])
        instance.empresa = self.empresa
        
        if commit:
            instance.save()
        
        return instance


class TemplateRelatorioForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para templates de relatório"""
    
    campos_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        required=False,
        label='Campos (JSON)',
        help_text='Lista de campos a incluir no relatório'
    )
    
    filtros_disponiveis_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Filtros Disponíveis (JSON)',
        help_text='Campos pelos quais se pode filtrar'
    )
    
    class Meta:
        model = TemplateRelatorio
        fields = [
            'nome', 'descricao', 'modelo_base', 'campos_text',
            'filtros_disponiveis_text', 'ativo'
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Valores iniciais para edição
        if self.instance.pk:
            if self.instance.campos:
                self.fields['campos_text'].initial = json.dumps(
                    self.instance.campos, indent=2, ensure_ascii=False
                )
            
            if self.instance.filtros_disponiveis:
                self.fields['filtros_disponiveis_text'].initial = json.dumps(
                    self.instance.filtros_disponiveis, indent=2, ensure_ascii=False
                )
    
    def clean_nome(self):
        nome = self.cleaned_data.get('nome')
        if nome:
            nome = nome.strip()
            
            # Verificar duplicatas na empresa
            existing = TemplateRelatorio.objects.filter(
                nome__iexact=nome,
                empresa=self.empresa
            )
            
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError('Já existe um template com este nome.')
        
        return nome
    
    def clean_campos_text(self):
        campos_text = self.cleaned_data.get('campos_text')
        if campos_text:
            try:
                campos = json.loads(campos_text)
                if not isinstance(campos, list):
                    raise ValidationError('Campos devem ser uma lista JSON válida.')
                return campos
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return []
    
    def clean_filtros_disponiveis_text(self):
        filtros_text = self.cleaned_data.get('filtros_disponiveis_text')
        if filtros_text:
            try:
                filtros = json.loads(filtros_text)
                if not isinstance(filtros, list):
                    raise ValidationError('Filtros devem ser uma lista JSON válida.')
                return filtros
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return []
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.campos = self.cleaned_data.get('campos_text', [])
        instance.filtros_disponiveis = self.cleaned_data.get('filtros_disponiveis_text', [])
        instance.empresa = self.empresa
        
        if commit:
            instance.save()
        
        return instance


class GerarRelatorioForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para gerar relatórios baseados em templates"""
    
    filtros_aplicados_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Filtros Aplicados (JSON)',
        help_text='Filtros específicos para este relatório'
    )
    
    class Meta:
        model = Relatorio
        fields = [
            'template', 'formato', 'filtros_aplicados_text'
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['template'].queryset = TemplateRelatorio.objects.filter(
                empresa=self.empresa, ativo=True
            )
    
    def clean_filtros_aplicados_text(self):
        filtros_text = self.cleaned_data.get('filtros_aplicados_text')
        if filtros_text:
            try:
                filtros = json.loads(filtros_text)
                if not isinstance(filtros, dict):
                    raise ValidationError('Filtros devem ser um objeto JSON válido.')
                return filtros
            except json.JSONDecodeError:
                raise ValidationError('JSON inválido. Verifique a sintaxe.')
        return {}
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.filtros_aplicados = self.cleaned_data.get('filtros_aplicados_text', {})
        instance.gerado_por = self.usuario
        
        if commit:
            instance.save()
        
        return instance


class AgendamentoRelatorioForm(BaseRelatoriosForm, forms.ModelForm):
    """Form para agendamento de relatórios"""
    
    destinatarios_list = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        label='Lista de Destinatários',
        help_text='Digite um email por linha'
    )
    
    class Meta:
        model = AgendamentoRelatorio
        fields = [
            'template', 'frequencia', 'horario', 'destinatarios_list', 'ativo'
        ]
        widgets = {
            'horario': forms.TimeInput(attrs={'type': 'time'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['template'].queryset = TemplateRelatorio.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Valores iniciais para edição
        if self.instance.pk and self.instance.destinatarios:
            emails = [email.strip() for email in self.instance.destinatarios.split(',')]
            self.fields['destinatarios_list'].initial = '\n'.join(emails)
    
    def clean_destinatarios_list(self):
        destinatarios_text = self.cleaned_data.get('destinatarios_list')
        if destinatarios_text:
            emails = [email.strip() for email in destinatarios_text.split('\n') if email.strip()]
            
            # Validar emails
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError as DjangoValidationError
            
            for email in emails:
                try:
                    validate_email(email)
                except DjangoValidationError:
                    raise ValidationError(f'Email inválido: {email}')
            
            if len(emails) > 20:
                raise ValidationError('Máximo de 20 destinatários por agendamento.')
            
            return ','.join(emails)
        
        raise ValidationError('Pelo menos um destinatário é obrigatório.')
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.destinatarios = self.cleaned_data.get('destinatarios_list', '')
        
        if commit:
            instance.save()
        
        return instance


class ExportarRelatorioForm(BaseRelatoriosForm):
    """Form para exportação de relatórios"""
    
    FORMATO_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel (XLSX)'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
    ]
    
    formato = forms.ChoiceField(
        choices=FORMATO_CHOICES,
        label='Formato do Arquivo'
    )
    
    incluir_graficos = forms.BooleanField(
        required=False,
        initial=True,
        label='Incluir Gráficos',
        help_text='Incluir gráficos no relatório (apenas PDF e Excel)'
    )
    
    incluir_detalhes = forms.BooleanField(
        required=False,
        initial=True,
        label='Incluir Dados Detalhados',
        help_text='Incluir todos os dados detalhados'
    )
    
    orientacao = forms.ChoiceField(
        choices=[
            ('portrait', 'Retrato'),
            ('landscape', 'Paisagem'),
        ],
        initial='portrait',
        label='Orientação da Página',
        help_text='Apenas para PDF'
    )


class FiltroRelatoriosForm(BaseRelatoriosForm):
    """Form para filtros gerais de relatórios"""
    
    PERIODO_CHOICES = [
        ('', 'Período personalizado'),
        ('hoje', 'Hoje'),
        ('ontem', 'Ontem'),
        ('esta_semana', 'Esta semana'),
        ('semana_passada', 'Semana passada'),
        ('este_mes', 'Este mês'),
        ('mes_passado', 'Mês passado'),
        ('ultimos_30_dias', 'Últimos 30 dias'),
        ('ultimos_90_dias', 'Últimos 90 dias'),
        ('este_ano', 'Este ano'),
        ('ano_passado', 'Ano passado'),
    ]
    
    periodo_predefinido = forms.ChoiceField(
        choices=PERIODO_CHOICES,
        required=False,
        label='Período Pré-definido'
    )
    
    data_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data Início'
    )
    
    data_fim = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Data Fim'
    )
    
    categoria_relatorio = forms.ChoiceField(
        choices=[('', 'Todas as categorias')] + TipoRelatorio.CATEGORIA_CHOICES,
        required=False,
        label='Categoria'
    )
    
    status = forms.ChoiceField(
        choices=[('', 'Todos os status')] + RelatorioGerado.STATUS_CHOICES,
        required=False,
        label='Status'
    )
    
    formato = forms.ChoiceField(
        choices=[('', 'Todos os formatos')] + RelatorioGerado.FORMATO_CHOICES,
        required=False,
        label='Formato'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        periodo_predefinido = cleaned_data.get('periodo_predefinido')
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        # Se período pré-definido for selecionado, calcular as datas
        if periodo_predefinido:
            hoje = date.today()
            
            if periodo_predefinido == 'hoje':
                cleaned_data['data_inicio'] = hoje
                cleaned_data['data_fim'] = hoje
            elif periodo_predefinido == 'ontem':
                ontem = hoje - timedelta(days=1)
                cleaned_data['data_inicio'] = ontem
                cleaned_data['data_fim'] = ontem
            elif periodo_predefinido == 'ultimos_30_dias':
                cleaned_data['data_inicio'] = hoje - timedelta(days=30)
                cleaned_data['data_fim'] = hoje
            elif periodo_predefinido == 'ultimos_90_dias':
                cleaned_data['data_inicio'] = hoje - timedelta(days=90)
                cleaned_data['data_fim'] = hoje
            # Adicionar outros períodos conforme necessário
        
        # Validar datas se fornecidas
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        
        if data_inicio and data_fim and data_inicio > data_fim:
            raise ValidationError('Data de início deve ser anterior à data de fim.')
        
        return cleaned_data
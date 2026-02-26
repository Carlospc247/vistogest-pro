# apps/comandas/filters.py
import django_filters
from django import forms
from .models import (
    Comanda, ItemComanda, ProdutoComanda, CategoriaComanda,
    Mesa, CentroRequisicao, TemplateComanda
)

class ComandaFilter(django_filters.FilterSet):
    """Filtros para comandas"""
    numero_comanda = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Número da comanda...'
        })
    )
    
    status = django_filters.ChoiceFilter(
        choices=Comanda.STATUS_CHOICES,
        empty_label="Todos os Status",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    tipo_atendimento = django_filters.ChoiceFilter(
        choices=Comanda.TIPO_ATENDIMENTO_CHOICES,
        empty_label="Todos os Tipos",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    data_abertura = django_filters.DateFromToRangeFilter(
        widget=django_filters.widgets.RangeWidget(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    mesa = django_filters.ModelChoiceFilter(
        queryset=Mesa.objects.none(),  # Será definido no __init__
        empty_label="Todas as Mesas",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    atendente = django_filters.ModelChoiceFilter(
        queryset=None,  # Será definido no __init__
        empty_label="Todos os Atendentes",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    cliente = django_filters.CharFilter(
        field_name='cliente__nome',
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do cliente...'
        })
    )
    
    total = django_filters.RangeFilter(
        widget=django_filters.widgets.RangeWidget(attrs={
            'type': 'number',
            'step': '0.01',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = Comanda
        fields = [
            'numero_comanda', 'status', 'tipo_atendimento', 
            'data_abertura', 'mesa', 'atendente', 'cliente', 'total'
        ]
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            # Filtrar mesas por empresa
            self.filters['mesa'].queryset = Mesa.objects.filter(
                empresa=empresa, ativa=True
            )
            
            # Filtrar atendentes por empresa
            from apps.funcionarios.models import Funcionario
            self.filters['atendente'].queryset = Funcionario.objects.filter(
                empresa=empresa, ativo=True
            )

class ItemComandaFilter(django_filters.FilterSet):
    """Filtros para itens de comandas"""
    comanda__numero_comanda = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Número da comanda...'
        })
    )
    
    produto__nome = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do produto...'
        })
    )
    
    produto__categoria = django_filters.ModelChoiceFilter(
        queryset=CategoriaComanda.objects.none(),
        empty_label="Todas as Categorias",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    status = django_filters.ChoiceFilter(
        choices=ItemComanda.STATUS_CHOICES,
        empty_label="Todos os Status",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    hora_pedido = django_filters.DateFromToRangeFilter(
        widget=django_filters.widgets.RangeWidget(attrs={
            'type': 'datetime-local',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = ItemComanda
        fields = [
            'comanda__numero_comanda', 'produto__nome', 
            'produto__categoria', 'status', 'hora_pedido'
        ]
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.filters['produto__categoria'].queryset = CategoriaComanda.objects.filter(
                empresa=empresa, ativa=True
            )

class ProdutoComandaFilter(django_filters.FilterSet):
    """Filtros para produtos de comandas"""
    nome = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do produto...'
        })
    )
    
    codigo = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Código...'
        })
    )
    
    categoria = django_filters.ModelChoiceFilter(
        queryset=CategoriaComanda.objects.none(),
        empty_label="Todas as Categorias",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    disponivel = django_filters.BooleanFilter(
        widget=forms.Select(
            choices=[('', 'Todos'), (True, 'Disponíveis'), (False, 'Indisponíveis')],
            attrs={'class': 'form-control'}
        )
    )
    
    destaque = django_filters.BooleanFilter(
        widget=forms.Select(
            choices=[('', 'Todos'), (True, 'Em Destaque'), (False, 'Normais')],
            attrs={'class': 'form-control'}
        )
    )
    
    preco_venda = django_filters.RangeFilter(
        widget=django_filters.widgets.RangeWidget(attrs={
            'type': 'number',
            'step': '0.01',
            'class': 'form-control'
        })
    )
    
    controla_estoque = django_filters.BooleanFilter(
        widget=forms.Select(
            choices=[('', 'Todos'), (True, 'Com Estoque'), (False, 'Sem Estoque')],
            attrs={'class': 'form-control'}
        )
    )
    
    class Meta:
        model = ProdutoComanda
        fields = [
            'nome', 'codigo', 'categoria', 'disponivel', 
            'destaque', 'preco_venda', 'controla_estoque'
        ]
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.filters['categoria'].queryset = CategoriaComanda.objects.filter(
                empresa=empresa, ativa=True
            )

class MesaFilter(django_filters.FilterSet):
    """Filtros para mesas"""
    numero = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Número da mesa...'
        })
    )
    
    nome = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome da mesa...'
        })
    )
    
    status = django_filters.ChoiceFilter(
        choices=Mesa.STATUS_CHOICES,
        empty_label="Todos os Status",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    capacidade = django_filters.RangeFilter(
        widget=django_filters.widgets.RangeWidget(attrs={
            'type': 'number',
            'class': 'form-control'
        })
    )
    
    localizacao = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Localização...'
        })
    )
    
    ativa = django_filters.BooleanFilter(
        widget=forms.Select(
            choices=[('', 'Todas'), (True, 'Ativas'), (False, 'Inativas')],
            attrs={'class': 'form-control'}
        )
    )
    
    class Meta:
        model = Mesa
        fields = ['numero', 'nome', 'status', 'capacidade', 'localizacao', 'ativa']

class CentroRequisicaoFilter(django_filters.FilterSet):
    """Filtros para centros de requisição"""
    nome = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do centro...'
        })
    )
    
    codigo = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Código...'
        })
    )
    
    tipo_centro = django_filters.ChoiceFilter(
        choices=CentroRequisicao.TIPO_CENTRO_CHOICES,
        empty_label="Todos os Tipos",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    ativo = django_filters.BooleanFilter(
        widget=forms.Select(
            choices=[('', 'Todos'), (True, 'Ativos'), (False, 'Inativos')],
            attrs={'class': 'form-control'}
        )
    )
    
    aceita_pedidos = django_filters.BooleanFilter(
        widget=forms.Select(
            choices=[('', 'Todos'), (True, 'Aceita'), (False, 'Não Aceita')],
            attrs={'class': 'form-control'}
        )
    )
    
    responsavel = django_filters.ModelChoiceFilter(
        queryset=None,  # Será definido no __init__
        empty_label="Todos os Responsáveis",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = CentroRequisicao
        fields = ['nome', 'codigo', 'tipo_centro', 'ativo', 'aceita_pedidos', 'responsavel']
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            from apps.funcionarios.models import Funcionario
            self.filters['responsavel'].queryset = Funcionario.objects.filter(
                empresa=empresa, ativo=True
            )

class RelatorioComandaFilter(django_filters.FilterSet):
    """Filtros específicos para relatórios"""
    data_inicio = django_filters.DateFilter(
        field_name='data_abertura__date',
        lookup_expr='gte',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    data_fim = django_filters.DateFilter(
        field_name='data_abertura__date',
        lookup_expr='lte',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    periodo = django_filters.ChoiceFilter(
        method='filter_periodo',
        choices=[
            ('hoje', 'Hoje'),
            ('ontem', 'Ontem'),
            ('esta_semana', 'Esta Semana'),
            ('semana_passada', 'Semana Passada'),
            ('este_mes', 'Este Mês'),
            ('mes_passado', 'Mês Passado'),
            ('ultimos_30_dias', 'Últimos 30 Dias'),
            ('este_ano', 'Este Ano'),
        ],
        empty_label="Período Personalizado",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    valor_minimo = django_filters.NumberFilter(
        field_name='total',
        lookup_expr='gte',
        widget=forms.NumberInput(attrs={
            'type': 'number',
            'step': '0.01',
            'class': 'form-control',
            'placeholder': 'Valor mínimo'
        })
    )
    
    valor_maximo = django_filters.NumberFilter(
        field_name='total',
        lookup_expr='lte',
        widget=forms.NumberInput(attrs={
            'type': 'number',
            'step': '0.01',
            'class': 'form-control',
            'placeholder': 'Valor máximo'
        })
    )
    
    class Meta:
        model = Comanda
        fields = ['data_inicio', 'data_fim', 'periodo', 'valor_minimo', 'valor_maximo']
    
    def filter_periodo(self, queryset, name, value):
        """Filtro personalizado para períodos pré-definidos"""
        from datetime import date, timedelta
        from django.utils import timezone
        
        hoje = date.today()
        
        if value == 'hoje':
            return queryset.filter(data_abertura__date=hoje)
        elif value == 'ontem':
            ontem = hoje - timedelta(days=1)
            return queryset.filter(data_abertura__date=ontem)
        elif value == 'esta_semana':
            inicio_semana = hoje - timedelta(days=hoje.weekday())
            return queryset.filter(data_abertura__date__gte=inicio_semana)
        elif value == 'semana_passada':
            fim_semana_passada = hoje - timedelta(days=hoje.weekday() + 1)
            inicio_semana_passada = fim_semana_passada - timedelta(days=6)
            return queryset.filter(
                data_abertura__date__gte=inicio_semana_passada,
                data_abertura__date__lte=fim_semana_passada
            )
        elif value == 'este_mes':
            inicio_mes = hoje.replace(day=1)
            return queryset.filter(data_abertura__date__gte=inicio_mes)
        elif value == 'mes_passado':
            if hoje.month == 1:
                mes_passado = hoje.replace(year=hoje.year - 1, month=12, day=1)
            else:
                mes_passado = hoje.replace(month=hoje.month - 1, day=1)
            
            # Último dia do mês passado
            if mes_passado.month == 12:
                fim_mes_passado = date(mes_passado.year + 1, 1, 1) - timedelta(days=1)
            else:
                fim_mes_passado = mes_passado.replace(month=mes_passado.month + 1) - timedelta(days=1)
            
            return queryset.filter(
                data_abertura__date__gte=mes_passado,
                data_abertura__date__lte=fim_mes_passado
            )
        elif value == 'ultimos_30_dias':
            data_inicio = hoje - timedelta(days=30)
            return queryset.filter(data_abertura__date__gte=data_inicio)
        elif value == 'este_ano':
            inicio_ano = hoje.replace(month=1, day=1)
            return queryset.filter(data_abertura__date__gte=inicio_ano)
        
        return queryset

# Filtro customizado para cozinha
class CozinhaFilter(django_filters.FilterSet):
    """Filtros específicos para interface da cozinha"""
    centro_requisicao = django_filters.ModelChoiceFilter(
        field_name='produto__centro_requisicao',
        queryset=CentroRequisicao.objects.none(),
        empty_label="Todos os Centros",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    status = django_filters.ChoiceFilter(
        choices=[
            ('pendente', 'Pendente'),
            ('em_preparo', 'Em Preparo'),
            ('pronto', 'Pronto'),
        ],
        empty_label="Todos os Status",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    urgente = django_filters.BooleanFilter(
        method='filter_urgente',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    tempo_espera = django_filters.ChoiceFilter(
        method='filter_tempo_espera',
        choices=[
            ('5', 'Mais de 5 min'),
            ('10', 'Mais de 10 min'),
            ('15', 'Mais de 15 min'),
            ('30', 'Mais de 30 min'),
        ],
        empty_label="Qualquer Tempo",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = ItemComanda
        fields = ['centro_requisicao', 'status', 'urgente', 'tempo_espera']
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.filters['centro_requisicao'].queryset = CentroRequisicao.objects.filter(
                empresa=empresa, ativo=True
            )
    
    def filter_urgente(self, queryset, name, value):
        """Filtrar itens urgentes (mais de 15 minutos de espera)"""
        if value:
            from django.utils import timezone
            limite = timezone.now() - timezone.timedelta(minutes=15)
            return queryset.filter(hora_pedido__lt=limite)
        return queryset
    
    def filter_tempo_espera(self, queryset, name, value):
        """Filtrar por tempo de espera"""
        if value:
            from django.utils import timezone
            minutos = int(value)
            limite = timezone.now() - timezone.timedelta(minutes=minutos)
            return queryset.filter(hora_pedido__lt=limite)
        return queryset
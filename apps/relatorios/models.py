# apps/relatorios/models.py
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel, Usuario
from apps.empresas.models import Empresa, Loja, Categoria
from apps.produtos.models import Produto, Categoria
from apps.clientes.models import Cliente
from apps.vendas.models import Venda
from apps.funcionarios.models import Funcionario
from decimal import Decimal
from datetime import date, datetime, timedelta
import json
import uuid
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from apps.core.models import TimeStampedModel
from apps.empresas.models import Empresa, Loja
from django.db import models
from django.contrib.auth.models import User



class TipoRelatorio(TimeStampedModel):
    """Tipos de relatórios disponíveis no sistema"""
    CATEGORIA_CHOICES = [
        ('vendas', 'Vendas'),
        ('estoque', 'Estoque'),
        ('financeiro', 'Financeiro'),
        ('clientes', 'Clientes'),
        ('funcionarios', 'Funcionários'),
        ('produtos', 'Produtos'),
        ('regulatorio', 'Regulatório'),
        ('gerencial', 'Gerencial'),
        ('operacional', 'Operacional'),
    ]
    
    PERIODICIDADE_CHOICES = [
        ('diario', 'Diário'),
        ('semanal', 'Semanal'),
        ('mensal', 'Mensal'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
        ('sob_demanda', 'Sob Demanda'),
    ]
    
    # Identificação
    codigo = models.CharField(max_length=50, unique=True)
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    categoria = models.CharField(max_length=15, choices=CATEGORIA_CHOICES)
    
    # Configurações
    periodicidade = models.CharField(max_length=15, choices=PERIODICIDADE_CHOICES, default='sob_demanda')
    requer_aprovacao = models.BooleanField(default=False)
    publico = models.BooleanField(default=True, help_text="Disponível para todos os usuários")
    
    # Parâmetros do relatório
    parametros_schema = models.JSONField(
        default=dict,
        help_text="Schema JSON dos parâmetros aceitos pelo relatório"
    )
    
    # Query/Template
    query_sql = models.TextField(blank=True, help_text="Query SQL personalizada")
    template_html = models.TextField(blank=True, help_text="Template HTML para exibição")
    
    # Permissões
    cargos_permitidos = models.ManyToManyField(
        'funcionarios.Cargo',
        blank=True,
        help_text="Cargos que podem acessar este relatório"
    )
    
    ativo = models.BooleanField(default=True)
    ordem_exibicao = models.IntegerField(default=0)
    
    class Meta:
        verbose_name = "Tipo de Relatório"
        verbose_name_plural = "Tipos de Relatórios"
        ordering = ['categoria', 'ordem_exibicao', 'nome']
    
    def __str__(self):
        return f"{self.nome} ({self.get_categoria_display()})"

class RelatorioGerado(TimeStampedModel):
    """Relatórios gerados pelos usuários"""
    STATUS_CHOICES = [
        ('processando', 'Processando'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
        ('cancelado', 'Cancelado'),
    ]
    
    FORMATO_CHOICES = [
        ('html', 'HTML'),
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
    ]
    
    # Identificação
    codigo_relatorio = models.CharField(max_length=20, unique=True)
    tipo_relatorio = models.ForeignKey(TipoRelatorio, on_delete=models.CASCADE, related_name='execucoes')
    
    # Parâmetros utilizados
    parametros = models.JSONField(default=dict, help_text="Parâmetros utilizados na geração")
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    
    # Filtros aplicados
    lojas = models.ManyToManyField(Loja, blank=True)
    categorias = models.ManyToManyField(Categoria, blank=True)
    funcionarios = models.ManyToManyField(Funcionario, blank=True)
    
    # Processamento
    formato = models.CharField(max_length=10, choices=FORMATO_CHOICES, default='html')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='processando')
    
    # Datas
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_inicio_processamento = models.DateTimeField(null=True, blank=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)
    tempo_processamento = models.DurationField(null=True, blank=True)
    
    # Resultado
    arquivo_resultado = models.FileField(upload_to='relatorios/gerados/', null=True, blank=True)
    dados_resultado = models.JSONField(default=dict, blank=True)
    total_registros = models.IntegerField(default=0)
    
    # Log de erros
    mensagem_erro = models.TextField(blank=True)
    
    # Usuário solicitante
    solicitante = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='relatorios_solicitados')
    
    # Aprovação (se necessária)
    aprovador = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='relatorios_aprovados'
    )
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Relatório Gerado"
        verbose_name_plural = "Relatórios Gerados"
        ordering = ['-data_solicitacao']
    
    def __str__(self):
        return f"{self.codigo_relatorio} - {self.tipo_relatorio.nome}"
    
    def save(self, *args, **kwargs):
        if not self.codigo_relatorio:
            self.codigo_relatorio = self.gerar_codigo_relatorio()
        super().save(*args, **kwargs)
    
    def gerar_codigo_relatorio(self):
        """Gera código único do relatório"""
        from django.db.models import Max
        hoje = date.today()
        prefixo = f"REL-{hoje.strftime('%Y%m%d')}"
        
        ultimo_numero = RelatorioGerado.objects.filter(
            codigo_relatorio__startswith=prefixo
        ).aggregate(Max('codigo_relatorio'))['codigo_relatorio__max']
        
        if ultimo_numero:
            try:
                numero = int(ultimo_numero.split('-')[-1]) + 1
            except:
                numero = 1
        else:
            numero = 1
        
        return f"{prefixo}-{numero:04d}"

class MetricaKPI(TimeStampedModel):
    """Métricas e KPIs do sistema"""
    TIPO_METRICA_CHOICES = [
        ('vendas', 'Vendas'),
        ('financeiro', 'Financeiro'),
        ('estoque', 'Estoque'),
        ('clientes', 'Clientes'),
        ('operacional', 'Operacional'),
    ]
    
    PERIODO_CHOICES = [
        ('diario', 'Diário'),
        ('semanal', 'Semanal'),
        ('mensal', 'Mensal'),
        ('trimestral', 'Trimestral'),
        ('anual', 'Anual'),
    ]
    
    # Identificação
    codigo = models.CharField(max_length=50, unique=True)
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    tipo_metrica = models.CharField(max_length=15, choices=TIPO_METRICA_CHOICES)
    
    # Período de cálculo
    periodo = models.CharField(max_length=15, choices=PERIODO_CHOICES)
    data_referencia = models.DateField()
    
    # Valores
    valor_atual = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_anterior = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_meta = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Variações
    variacao_absoluta = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variacao_percentual = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Configurações de exibição
    unidade_medida = models.CharField(max_length=20, default='unidade')
    formato_exibicao = models.CharField(max_length=20, choices=[
        ('numero', 'Número'),
        ('moeda', 'Moeda'),
        ('percentual', 'Percentual'),
        ('tempo', 'Tempo'),
    ], default='numero')
    
    # Filtros aplicados
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Detalhes do cálculo
    detalhes_calculo = models.JSONField(default=dict, blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Métrica KPI"
        verbose_name_plural = "Métricas KPIs"
        unique_together = ['codigo', 'data_referencia', 'loja', 'empresa']
        ordering = ['-data_referencia', 'tipo_metrica', 'codigo']
    
    def __str__(self):
        return f"{self.nome} - {self.data_referencia}"
    
    def save(self, *args, **kwargs):
        # Calcular variações
        if self.valor_anterior:
            self.variacao_absoluta = self.valor_atual - self.valor_anterior
            self.variacao_percentual = (self.variacao_absoluta / self.valor_anterior) * 100
        
        super().save(*args, **kwargs)
    
    @property
    def percentual_meta(self):
        """Percentual atingido da meta"""
        if self.valor_meta and self.valor_meta > 0:
            return (self.valor_atual / self.valor_meta) * 100
        return None
    
    @property
    def status_meta(self):
        """Status em relação à meta"""
        percentual = self.percentual_meta
        if percentual is None:
            return 'sem_meta'
        elif percentual >= 100:
            return 'atingida'
        elif percentual >= 80:
            return 'proximo'
        else:
            return 'distante'

class DashboardConfig(TimeStampedModel):
    """Configurações de dashboards personalizados"""
    # Identificação
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    codigo = models.CharField(max_length=50)
    
    # Proprietário
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dashboards_relatorios'  # ✅ ÚNICO
    )
    publico = models.BooleanField(default=False, help_text="Visível para outros usuários")
    
    # Layout
    configuracao_layout = models.JSONField(
        default=dict,
        help_text="Configuração do layout dos widgets"
    )
    
    # Widgets incluídos
    widgets_incluidos = models.JSONField(
        default=list,
        help_text="Lista de widgets incluídos no dashboard"
    )
    
    # Configurações de atualização
    auto_refresh = models.BooleanField(default=True)
    intervalo_refresh = models.IntegerField(
        default=300,
        help_text="Intervalo de atualização em segundos"
    )
    
    # Status
    ativo = models.BooleanField(default=True)
    dashboard_padrao = models.BooleanField(default=False)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Configuração de Dashboard"
        verbose_name_plural = "Configurações de Dashboards"
        unique_together = ['codigo', 'usuario', 'empresa']
        ordering = ['nome']
    
    def __str__(self):
        return f"{self.nome} ({self.usuario.username})"

class AnaliseVendas(TimeStampedModel):
    """Análises de vendas por diferentes dimensões"""
    DIMENSAO_CHOICES = [
        ('produto', 'Por Produto'),
        ('categoria', 'Por Categoria'),
        ('cliente', 'Por Cliente'),
        ('vendedor', 'Por Vendedor'),
        ('forma_pagamento', 'Por Forma de Pagamento'),
        ('periodo', 'Por Período'),
        ('loja', 'Por Loja'),
    ]
    
    # Período da análise
    data_inicio = models.DateField()
    data_fim = models.DateField()
    dimensao = models.CharField(max_length=20, choices=DIMENSAO_CHOICES)
    
    # Filtros aplicados
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Resultados da análise
    total_vendas = models.IntegerField(default=0)
    total_itens = models.IntegerField(default=0)
    faturamento_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    ticket_medio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Top performers
    top_produtos = models.JSONField(default=list, blank=True)
    top_clientes = models.JSONField(default=list, blank=True)
    top_vendedores = models.JSONField(default=list, blank=True)
    
    # Análises por período
    vendas_por_dia = models.JSONField(default=dict, blank=True)
    vendas_por_hora = models.JSONField(default=dict, blank=True)
    vendas_por_dia_semana = models.JSONField(default=dict, blank=True)
    
    # Análises de margem
    margem_bruta_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    margem_bruta_percentual = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Dados detalhados
    dados_detalhados = models.JSONField(default=dict, blank=True)
    
    # Metadados
    data_processamento = models.DateTimeField(auto_now_add=True)
    usuario_solicitante = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Análise de Vendas"
        verbose_name_plural = "Análises de Vendas"
        ordering = ['-data_processamento']
    
    def __str__(self):
        return f"Análise {self.get_dimensao_display()} - {self.data_inicio} a {self.data_fim}"

class AnaliseEstoque(TimeStampedModel):
    """Análises de estoque e movimentações"""
    TIPO_ANALISE_CHOICES = [
        ('giro', 'Giro de Estoque'),
        ('abc', 'Curva ABC'),
        ('vencimento', 'Análise de Vencimentos'),
        ('ruptura', 'Análise de Rupturas'),
        ('sazonalidade', 'Análise de Sazonalidade'),
    ]
    
    # Configuração da análise
    tipo_analise = models.CharField(max_length=20, choices=TIPO_ANALISE_CHOICES)
    data_referencia = models.DateField()
    periodo_analise_dias = models.IntegerField(default=90)
    
    # Filtros
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Resultados gerais
    total_produtos_analisados = models.IntegerField(default=0)
    valor_estoque_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    giro_medio = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Classificações ABC
    produtos_classe_a = models.JSONField(default=list, blank=True)
    produtos_classe_b = models.JSONField(default=list, blank=True)
    produtos_classe_c = models.JSONField(default=list, blank=True)
    
    # Produtos críticos
    produtos_ruptura = models.JSONField(default=list, blank=True)
    produtos_excesso = models.JSONField(default=list, blank=True)
    produtos_vencendo = models.JSONField(default=list, blank=True)
    produtos_sem_giro = models.JSONField(default=list, blank=True)
    
    # Análise de sazonalidade
    vendas_por_mes = models.JSONField(default=dict, blank=True)
    tendencia_vendas = models.CharField(max_length=20, blank=True)
    
    # Recomendações
    recomendacoes_compra = models.JSONField(default=list, blank=True)
    recomendacoes_promocao = models.JSONField(default=list, blank=True)
    
    # Dados detalhados
    dados_completos = models.JSONField(default=dict, blank=True)
    
    # Metadados
    data_processamento = models.DateTimeField(auto_now_add=True)
    usuario_solicitante = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Análise de Estoque"
        verbose_name_plural = "Análises de Estoque"
        ordering = ['-data_processamento']
    
    def __str__(self):
        return f"Análise {self.get_tipo_analise_display()} - {self.data_referencia}"

class AnaliseClientes(TimeStampedModel):
    """Análises de comportamento e segmentação de clientes"""
    TIPO_SEGMENTACAO_CHOICES = [
        ('rfm', 'RFM (Recência, Frequência, Valor)'),
        ('valor', 'Por Valor de Compra'),
        ('frequencia', 'Por Frequência'),
        ('produtos', 'Por Produtos Comprados'),
        ('geografica', 'Geográfica'),
    ]
    
    # Configuração
    tipo_segmentacao = models.CharField(max_length=20, choices=TIPO_SEGMENTACAO_CHOICES)
    data_inicio = models.DateField()
    data_fim = models.DateField()
    
    # Filtros
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    
    # Estatísticas gerais
    total_clientes_analisados = models.IntegerField(default=0)
    total_clientes_ativos = models.IntegerField(default=0)
    valor_medio_compra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frequencia_media_compra = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Segmentação RFM
    clientes_vip = models.JSONField(default=list, blank=True)
    clientes_frequentes = models.JSONField(default=list, blank=True)
    clientes_ocasionais = models.JSONField(default=list, blank=True)
    clientes_inativos = models.JSONField(default=list, blank=True)
    clientes_em_risco = models.JSONField(default=list, blank=True)
    
    # Análise de produtos
    produtos_mais_vendidos = models.JSONField(default=list, blank=True)
    categorias_preferidas = models.JSONField(default=dict, blank=True)
    
    # Análise temporal
    distribuicao_compras_mes = models.JSONField(default=dict, blank=True)
    distribuicao_compras_dia_semana = models.JSONField(default=dict, blank=True)
    distribuicao_compras_hora = models.JSONField(default=dict, blank=True)
    
    # Análise geográfica
    distribuicao_por_cidade = models.JSONField(default=dict, blank=True)
    distribuicao_por_bairro = models.JSONField(default=dict, blank=True)
    
    # Recomendações
    recomendacoes_retencao = models.JSONField(default=list, blank=True)
    recomendacoes_reativacao = models.JSONField(default=list, blank=True)
    
    # Dados completos
    dados_detalhados = models.JSONField(default=dict, blank=True)
    
    # Metadados
    data_processamento = models.DateTimeField(auto_now_add=True)
    usuario_solicitante = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Análise de Clientes"
        verbose_name_plural = "Análises de Clientes"
        ordering = ['-data_processamento']
    
    def __str__(self):
        return f"Análise {self.get_tipo_segmentacao_display()} - {self.data_inicio} a {self.data_fim}"


class AlertaGerencial(TimeStampedModel):
    """Alertas gerenciais baseados em métricas e KPIs"""
    TIPO_ALERTA_CHOICES = [
        ('meta_nao_atingida', 'Meta Não Atingida'),
        ('queda_vendas', 'Queda nas Vendas'),
        ('estoque_baixo', 'Estoque Baixo'),
        ('margem_baixa', 'Margem Baixa'),
        ('cliente_inativo', 'Cliente Inativo'),
        ('produto_sem_giro', 'Produto Sem Giro'),
        ('vencimento_proximo', 'Vencimento Próximo'),
        ('performance_vendedor', 'Performance Vendedor'),
    ]
    
    PRIORIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ]
    
    # Configuração do alerta
    tipo_alerta = models.CharField(max_length=25, choices=TIPO_ALERTA_CHOICES)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES)
    
    # Dados do alerta
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    valor_atual = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    valor_esperado = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Contexto
    data_referencia = models.DateField()
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, null=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, null=True, blank=True)
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, null=True, blank=True)
    
    # Ações recomendadas
    acoes_recomendadas = models.JSONField(default=list, blank=True)
    
    # Status
    ativo = models.BooleanField(default=True)
    data_resolucao = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    observacoes_resolucao = models.TextField(blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Alerta Gerencial"
        verbose_name_plural = "Alertas Gerenciais"
        ordering = ['-prioridade', '-created_at']
    
    def __str__(self):
        return f"{self.get_tipo_alerta_display()} - {self.titulo}"
    
    def resolver_alerta(self, usuario, observacoes=""):
        """Resolve o alerta"""
        self.ativo = False
        self.data_resolucao = datetime.now()
        self.resolvido_por = usuario
        self.observacoes_resolucao = observacoes
        self.save()


class TemplateRelatorio(TimeStampedModel):
    """
    Define a estrutura de um tipo de relatório.
    Ex: "Relatório de Vendas por Vendedor", "Inventário por Categoria".
    """
    nome = models.CharField("Nome do Template", max_length=255)
    descricao = models.TextField("Descrição", blank=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='templates_relatorios')

    # Torna o template genérico para qualquer modelo (Venda, Produto, etc.)
    modelo_base = models.ForeignKey(
        ContentType, 
        on_delete=models.PROTECT,
        help_text="O modelo principal sobre o qual o relatório é baseado."
    )

    campos = models.JSONField("Campos/Colunas", default=list, help_text="Lista de campos a incluir no relatório.")
    filtros_disponiveis = models.JSONField("Filtros Disponíveis", default=list, help_text="Campos pelos quais se pode filtrar.")

    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Template de Relatório"
        verbose_name_plural = "Templates de Relatórios"
        unique_together = ('empresa', 'nome')
        ordering = ['nome']

    def __str__(self):
        return self.nome

class Relatorio(TimeStampedModel):
    """
    Regista uma instância de um relatório que foi gerado.
    """
    FORMATO_CHOICES = [('pdf', 'PDF'), ('excel', 'Excel'), ('csv', 'CSV')]
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('gerando', 'Gerando'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]

    template = models.ForeignKey(TemplateRelatorio, on_delete=models.PROTECT)
    formato = models.CharField("Formato", max_length=10, choices=FORMATO_CHOICES, default='pdf')
    filtros_aplicados = models.JSONField("Filtros Aplicados", default=dict)

    gerado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    data_geracao = models.DateTimeField(auto_now_add=True)

    arquivo_gerado = models.FileField("Ficheiro do Relatório", upload_to='relatorios/', null=True, blank=True)
    status = models.CharField("Status", max_length=15, choices=STATUS_CHOICES, default='pendente')

    class Meta:
        verbose_name = "Relatório Gerado"
        verbose_name_plural = "Relatórios Gerados"
        ordering = ['-data_geracao']

    def __str__(self):
        return f"{self.template.nome} gerado em {self.data_geracao.strftime('%d/%m/%Y %H:%M')}"

class AgendamentoRelatorio(TimeStampedModel):
    """
    Agenda a geração recorrente de um relatório.
    """
    FREQUENCIA_CHOICES = [
        ('diario', 'Diário'),
        ('semanal', 'Semanal'),
        ('mensal', 'Mensal'),
    ]

    template = models.ForeignKey(TemplateRelatorio, on_delete=models.CASCADE)
    frequencia = models.CharField("Frequência", max_length=10, choices=FREQUENCIA_CHOICES)
    horario = models.TimeField("Horário de Execução")
    destinatarios = models.TextField("Emails de Destinatários", help_text="Separados por vírgula.")

    ativo = models.BooleanField("Agendamento Ativo", default=True)

    class Meta:
        verbose_name = "Agendamento de Relatório"
        verbose_name_plural = "Agendamentos de Relatórios"

    def __str__(self):
        return f"Agendamento {self.get_frequencia_display()} de '{self.template.nome}'"


class LogRelatorio(models.Model):
    """
    Regista eventos importantes relacionados com relatórios para auditoria.
    """
    # Ações possíveis que podem ser registadas
    ACAO_CHOICES = [
        ('GERACAO', 'Geração'),
        ('ENVIO', 'Envio por E-mail'),
        ('EXPORT', 'Exportação'),
        ('ACESSO', 'Acesso/Visualização'),
        ('CRIACAO', 'Criação de Agendamento'),
        ('ALTERACAO', 'Alteração de Agendamento'),
        ('EXCLUSAO', 'Exclusão de Agendamento'),
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, help_text="Utilizador que realizou a ação")
    acao = models.CharField(max_length=20, choices=ACAO_CHOICES, help_text="Ação que foi realizada")
    timestamp = models.DateTimeField(auto_now_add=True, help_text="Data e hora em que a ação ocorreu")
    detalhes = models.TextField(help_text="Detalhes sobre a ação, como nome do relatório ou destinatários")

    def __str__(self):
        return f"{self.usuario} - {self.get_acao_display()} em {self.timestamp.strftime('%d/%m/%Y %H:%M')}"

    class Meta:
        verbose_name = "Log de Relatório"
        verbose_name_plural = "Logs de Relatórios"
        ordering = ['-timestamp']


class RegraDistribuicao(models.Model):
    """
    Define uma regra específica de como e para quem um relatório deve ser distribuído.
    """
    METODO_CHOICES = [
        ('EMAIL', 'E-mail'),
        ('FTP', 'Servidor FTP'),
        ('WEBHOOK', 'API Webhook'),
    ]
    FORMATO_CHOICES = [
        ('PDF', 'PDF'),
        ('EXCEL', 'Excel (.xlsx)'),
        ('CSV', 'CSV'),
    ]

    nome_regra = models.CharField(max_length=255, help_text="Nome descritivo da regra. Ex: 'Enviar DRE para Direção'")
    agendamento = models.ForeignKey('Agendamento', on_delete=models.CASCADE, related_name="regras_distribuicao")
    
    metodo_entrega = models.CharField(max_length=10, choices=METODO_CHOICES, default='EMAIL')
    formato = models.CharField(max_length=10, choices=FORMATO_CHOICES, default='PDF')
    
    destinatarios = models.TextField(help_text="Lista de destinatários. Para e-mails, separe por vírgula. Para webhooks, coloque a URL.")
    ativo = models.BooleanField(default=True, help_text="Desmarque para desativar esta regra de distribuição.")

    def __str__(self):
        return f"Regra: {self.nome_regra} ({self.get_metodo_entrega_display()})"

    class Meta:
        verbose_name = "Regra de Distribuição"
        verbose_name_plural = "Regras de Distribuição"


class LogAtividade(models.Model):
    """
    Modelo consolidado que regista todas as atividades relevantes do sistema.
    """
    TIPO_LOG_CHOICES = [
        ('HISTORICO', 'Histórico'),
        ('AUDITORIA', 'Auditoria'),
        ('DISTRIBUICAO', 'Distribuição'),
        ('ERRO', 'Erro do Sistema'),
    ]
    STATUS_CHOICES = [
        ('SUCESSO', 'Sucesso'),
        ('FALHA', 'Falha'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_LOG_CHOICES)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SUCESSO')
    acao = models.CharField(max_length=255)
    detalhes = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_str = self.usuario.username if self.usuario else "Sistema"
        return f"[{self.get_tipo_display()}] {self.acao} por {user_str}"

    class Meta:
        verbose_name = "Log de Atividade"
        verbose_name_plural = "Logs de Atividades"
        ordering = ['-timestamp']


class AuditoriaRelatoriosView(models.Model):
    """
    Exibe logs de alterações em configurações de relatórios e agendamentos.
    """
    model = LogAtividade  # CORRIGIDO
    template_name = 'historico/lista.html'
    # Filtra os logs que são do tipo 'AUDITORIA'
    queryset = LogAtividade.objects.filter(tipo='AUDITORIA') # CORRIGIDO
    context_object_name = 'logs'
    paginate_by = 25

class LogsRelatoriosView(models.Model):
    """
    Exibe todos os logs do sistema de relatórios, com capacidade de filtro.
    """
    model = LogAtividade  # CORRIGIDO
    template_name = 'historico/lista_completa.html'
    context_object_name = 'logs'
    paginate_by = 50

class LogAcessoRelatoriosView(models.Model):
    """
    Exibe quem acedeu a quais relatórios e quando.
    """
    model = LogAtividade  # CORRIGIDO
    template_name = 'historico/lista.html'
    # Filtra os logs de HISTORICO com uma ação específica de ACESSO
    queryset = LogAtividade.objects.filter(tipo='HISTORICO', acao__icontains='Acesso') # CORRIGIDO
    context_object_name = 'logs'
    paginate_by = 25



class Agendamento(TimeStampedModel):
    """
    Agendamento de relatórios ou processos automatizados.
    Permite definir periodicidade, próximo agendamento e status.
    """

    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
        ('executado', 'Executado'),
        ('erro', 'Erro'),
    ]

    PERIODICIDADE_CHOICES = [
        ('diario', 'Diário'),
        ('semanal', 'Semanal'),
        ('mensal', 'Mensal'),
        ('anual', 'Anual'),
    ]

    # Vinculação à empresa
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='agendamentos',
        help_text="Empresa responsável pelo agendamento."
    )

    # Identificação do agendamento
    nome = models.CharField(max_length=200, help_text="Nome do agendamento, ex: 'Relatório de Vendas Mensal'.")
    descricao = models.TextField(blank=True, help_text="Descrição detalhada do agendamento ou do relatório.")

    # Configuração de execução
    periodicidade = models.CharField(max_length=20, choices=PERIODICIDADE_CHOICES, default='mensal')
    proximo_agendamento = models.DateTimeField(help_text="Data e hora do próximo agendamento.")
    ultimo_executado = models.DateTimeField(null=True, blank=True, help_text="Última execução realizada.")

    # Controle e status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ativo')
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agendamentos_responsavel',
        help_text="Usuário responsável por este agendamento."
    )
    observacoes = models.TextField(blank=True, help_text="Observações gerais sobre este agendamento.")

    class Meta:
        verbose_name = "Agendamento"
        verbose_name_plural = "Agendamentos"
        ordering = ['-proximo_agendamento']

    def __str__(self):
        return f"{self.nome} - {self.empresa.nome}"

    @property
    def esta_ativo(self):
        """Retorna True se o agendamento estiver ativo"""
        return self.status == 'ativo'



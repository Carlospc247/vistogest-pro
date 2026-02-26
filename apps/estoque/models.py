# apps/estoque/models.py
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel, Usuario
from apps.empresas.models import Empresa, Loja
from apps.produtos.models import Produto, Lote
from decimal import Decimal
from datetime import date, datetime
import uuid
from django.db.models import Sum


class TipoMovimentacao(TimeStampedModel):
    """Tipos de movimentação de estoque"""
    nome = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(max_length=20, unique=True)
    
    # Natureza da movimentação
    NATUREZA_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
        ('ajuste', 'Ajuste'),
        ('transferencia', 'Transferência'),
    ]
    natureza = models.CharField(max_length=15, choices=NATUREZA_CHOICES)
    
    # Características
    requer_documento = models.BooleanField(default=False, help_text="Requer documento fiscal")
    requer_aprovacao = models.BooleanField(default=False, help_text="Requer aprovação para executar")
    automatico = models.BooleanField(default=False, help_text="Movimentação automática do sistema")
    
    # Controle de estoque
    controla_lote = models.BooleanField(default=True, help_text="Controla número de lote")
    controla_validade = models.BooleanField(default=True, help_text="Controla data de validade")
    
    # Descrição e observações
    descricao = models.TextField(blank=True)
    
    ativo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Tipo de Movimentação"
        verbose_name_plural = "Tipos de Movimentação"
        ordering = ['natureza', 'nome']
    
    def __str__(self):
        return f"{self.nome} ({self.get_natureza_display()})"


class MovimentacaoEstoque(TimeStampedModel):
    """Movimentação de estoque"""
    TIPO_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
        ('ajuste', 'Ajuste'),
    ]
    
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='movimentacoes_produto')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='movimentacoes_usuario')
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    loja = models.ForeignKey('empresas.Loja', on_delete=models.PROTECT, related_name='movimentacoes_loja')

    quantidade = models.IntegerField()
    motivo = models.CharField(max_length=200)
    observacoes = models.TextField(blank=True)
    
    @classmethod
    def calcular_estoque_atual(cls, produto, loja=None):
        filtros = {'produto': produto}
        if loja:
            filtros['loja'] = loja
        resultado = cls.objects.filter(**filtros).aggregate(estoque_total=Sum('quantidade'))
        return resultado['estoque_total'] or 0

    
    class Meta:
        verbose_name = 'Movimentação de Estoque'
        verbose_name_plural = 'Movimentações de Estoque'
        
    def __str__(self):
        return f"{self.get_tipo_display()} - {self.produto.nome_produto}"



class Inventario(TimeStampedModel):
    """Inventários de estoque"""
    STATUS_CHOICES = [
        ('planejado', 'Planejado'),
        ('em_andamento', 'Em Andamento'),
        ('concluido', 'Concluído'),
        ('cancelado', 'Cancelado'),
    ]
    
    # Identificação
    numero_inventario = models.CharField(max_length=20, unique=True)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    
    # Escopo
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name='inventarios')
    categorias = models.ManyToManyField(
        'empresas.Categoria',  # ✅ CORRIGIDO: referência correta
        blank=True,
        help_text="Categorias incluídas (vazio = todas)"
    )
    apenas_produtos_ativos = models.BooleanField(default=True)
    apenas_com_estoque = models.BooleanField(default=False)
    
    # Datas
    data_planejada = models.DateField()
    data_inicio = models.DateTimeField(null=True, blank=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)
    
    # Responsáveis
    responsavel_planejamento = models.ForeignKey(
        Usuario, 
        on_delete=models.PROTECT,
        related_name='inventarios_planejados'
    )
    responsaveis_contagem = models.ManyToManyField(
        Usuario,
        related_name='inventarios_contagem',
        help_text="Usuários responsáveis pela contagem"
    )
    
    # Status e controle
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='planejado')
    requer_dupla_contagem = models.BooleanField(default=False)
    bloqueio_movimentacao = models.BooleanField(
        default=True, 
        help_text="Bloquear movimentações durante inventário"
    )
    
    # Resultados
    total_produtos_planejados = models.IntegerField(default=0)
    total_produtos_contados = models.IntegerField(default=0)
    total_divergencias = models.IntegerField(default=0)
    valor_divergencia_total = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    observacoes = models.TextField(blank=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Inventário"
        verbose_name_plural = "Inventários"
        ordering = ['-data_planejada']
    
    def __str__(self):
        return f"{self.numero_inventario} - {self.titulo}"
    
    def save(self, *args, **kwargs):
        if not self.numero_inventario:
            self.numero_inventario = self.gerar_numero_inventario()
        super().save(*args, **kwargs)
    
    def gerar_numero_inventario(self):
        """Gera número sequencial do inventário"""
        from django.db.models import Max
        ultimo_numero = Inventario.objects.filter(
            empresa=self.empresa
        ).aggregate(Max('numero_inventario'))['numero_inventario__max']
        
        if ultimo_numero:
            try:
                numero = int(ultimo_numero.split('-')[-1]) + 1
            except:
                numero = 1
        else:
            numero = 1
        
        return f"INV-{numero:04d}"
    
    def iniciar_inventario(self):
        """Inicia o processo de inventário"""
        if self.status != 'planejado':
            raise ValidationError("Apenas inventários planejados podem ser iniciados")
        
        self.status = 'em_andamento'
        self.data_inicio = datetime.now()
        
        # Gerar itens do inventário
        self.gerar_itens_inventario()
        
        self.save()
    
    def gerar_itens_inventario(self):
        """Gera os itens a serem inventariados"""
        # Filtros para produtos
        filtros = {'empresa': self.empresa}
        
        if self.apenas_produtos_ativos:
            filtros['ativo'] = True
        
        # Buscar produtos
        produtos = Produto.objects.filter(**filtros)
        
        # Filtrar por categorias se especificado
        if self.categorias.exists():
            produtos = produtos.filter(categoria__in=self.categorias.all())
        
        count = 0
        for produto in produtos:
            # Calcular estoque atual
            estoque_sistema = MovimentacaoEstoque.calcular_estoque_atual(produto, self.loja)
            
            # Apenas produtos com estoque se especificado
            if self.apenas_com_estoque and estoque_sistema <= 0:
                continue
            
            ItemInventario.objects.create(
                inventario=self,
                produto=produto,
                quantidade_sistema=estoque_sistema,
                valor_unitario=produto.preco_custo
            )
            count += 1
        
        self.total_produtos_planejados = count
        self.save()
    
    def concluir_inventario(self):
        """Conclui o inventário gerando ajustes"""
        if self.status != 'em_andamento':
            raise ValidationError("Apenas inventários em andamento podem ser concluídos")
        
        # Processar divergências
        self.processar_divergencias()
        
        self.status = 'concluido'
        self.data_conclusao = datetime.now()
        self.save()
    
    def processar_divergencias(self):
        """Processa as divergências gerando movimentações de ajuste"""
        tipo_ajuste = TipoMovimentacao.objects.filter(
            codigo='AJUSTE_INVENTARIO',
            natureza='ajuste'
        ).first()
        
        if not tipo_ajuste:
            tipo_ajuste = TipoMovimentacao.objects.create(
                nome='Ajuste por Inventário',
                codigo='AJUSTE_INVENTARIO',
                natureza='ajuste',
                automatico=True
            )
        
        divergencias = 0
        total_divergencia = Decimal('0.00')
        
        for item in self.itens.filter(tem_divergencia=True):
            # Criar movimentação de ajuste
            MovimentacaoEstoque.objects.create(
                tipo_movimentacao=tipo_ajuste,
                produto=item.produto,
                loja=self.loja,
                quantidade=item.quantidade_contada,
                quantidade_anterior=item.quantidade_sistema,
                quantidade_atual=item.quantidade_contada,
                valor_unitario=item.valor_unitario,
                usuario_responsavel=self.responsavel_planejamento,
                observacoes=f"Ajuste por inventário {self.numero_inventario}",
                inventario_relacionado=self,
                status='concluida',
                empresa=self.empresa
            )
            
            divergencias += 1
            total_divergencia += abs(item.valor_divergencia)
        
        self.total_divergencias = divergencias
        self.valor_divergencia_total = total_divergencia
        self.save()
 
class ItemInventario(TimeStampedModel):
    """Itens do inventário"""
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('primeira_contagem', 'Primeira Contagem'),
        ('segunda_contagem', 'Segunda Contagem'),
        ('finalizado', 'Finalizado'),
    ]
    
    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    
    # Quantidades
    quantidade_sistema = models.IntegerField(default=0, help_text="Quantidade no sistema")
    quantidade_contada_1 = models.IntegerField(null=True, blank=True, help_text="Primeira contagem")
    quantidade_contada_2 = models.IntegerField(null=True, blank=True, help_text="Segunda contagem")
    quantidade_contada = models.IntegerField(null=True, blank=True, help_text="Quantidade final contada")
    
    # Valores
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Responsáveis das contagens
    usuario_contagem_1 = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='contagens_1'
    )
    usuario_contagem_2 = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='contagens_2'
    )
    
    # Datas das contagens
    data_contagem_1 = models.DateTimeField(null=True, blank=True)
    data_contagem_2 = models.DateTimeField(null=True, blank=True)
    
    # Status e observações
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Item do Inventário"
        verbose_name_plural = "Itens do Inventário"
        unique_together = ['inventario', 'produto']
        ordering = ['produto__nome_produto']
    
    def __str__(self):
        return f"{self.inventario.numero_inventario} - {self.produto.nome_produto}"
    
    @property
    def divergencia_quantidade(self):
        """Diferença entre sistema e contado"""
        if self.quantidade_contada is not None:
            return self.quantidade_contada - self.quantidade_sistema
        return 0
    
    @property
    def valor_divergencia(self):
        """Valor da divergência"""
        return self.divergencia_quantidade * self.valor_unitario
    
    @property
    def tem_divergencia(self):
        """Verifica se há divergência"""
        return self.divergencia_quantidade != 0
    
    @property
    def percentual_divergencia(self):
        """Percentual de divergência"""
        if self.quantidade_sistema > 0:
            return (abs(self.divergencia_quantidade) / self.quantidade_sistema) * 100
        return 0 if self.quantidade_contada == 0 else 100
    
    def registrar_primeira_contagem(self, quantidade, usuario):
        """Registra a primeira contagem"""
        self.quantidade_contada_1 = quantidade
        self.usuario_contagem_1 = usuario
        self.data_contagem_1 = datetime.now()
        
        if not self.inventario.requer_dupla_contagem:
            self.quantidade_contada = quantidade
            self.status = 'finalizado'
        else:
            self.status = 'primeira_contagem'
        
        self.save()
    
    def registrar_segunda_contagem(self, quantidade, usuario):
        """Registra a segunda contagem"""
        if self.status != 'primeira_contagem':
            raise ValidationError("Segunda contagem apenas após primeira contagem")
        
        self.quantidade_contada_2 = quantidade
        self.usuario_contagem_2 = usuario
        self.data_contagem_2 = datetime.now()
        
        # Determinar quantidade final
        if self.quantidade_contada_1 == quantidade:
            self.quantidade_contada = quantidade
        else:
            # Divergência entre contagens - usar a segunda
            self.quantidade_contada = quantidade
            self.observacoes += f"\nDivergência entre contagens: 1ª={self.quantidade_contada_1}, 2ª={quantidade}"
        
        self.status = 'finalizado'
        self.save()

class AlertaEstoque(TimeStampedModel):
    """Alertas de estoque baixo, vencimento, etc."""
    TIPO_ALERTA_CHOICES = [
        ('estoque_baixo', 'Estoque Baixo'),
        ('estoque_zerado', 'Estoque Zerado'),
        ('vencimento_proximo', 'Vencimento Próximo'),
        ('produto_vencido', 'Produto Vencido'),
        ('ruptura', 'Ruptura de Estoque'),
        ('excesso', 'Excesso de Estoque'),
    ]
    
    PRIORIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ]
    
    tipo_alerta = models.CharField(max_length=20, choices=TIPO_ALERTA_CHOICES)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES)
    
    # Produto relacionado
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='alertas_estoque')
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, null=True, blank=True)
    
    # Detalhes do alerta
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    quantidade_atual = models.IntegerField()
    quantidade_recomendada = models.IntegerField(null=True, blank=True)
    
    # Controle
    ativo = models.BooleanField(default=True)
    data_resolucao = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    observacoes_resolucao = models.TextField(blank=True)
    
    # Notificação
    notificado = models.BooleanField(default=False)
    data_notificacao = models.DateTimeField(null=True, blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Alerta de Estoque"
        verbose_name_plural = "Alertas de Estoque"
        indexes = [
            models.Index(fields=['tipo_alerta', 'ativo']),
            models.Index(fields=['prioridade', 'ativo']),
            models.Index(fields=['produto', 'loja']),
        ]
        ordering = ['-prioridade', '-created_at']
    
    def __str__(self):
        return f"{self.get_tipo_alerta_display()} - {self.produto.nome_produto}"
    
    def resolver_alerta(self, usuario, observacoes=""):
        """Resolve o alerta"""
        self.ativo = False
        self.data_resolucao = datetime.now()
        self.resolvido_por = usuario
        self.observacoes_resolucao = observacoes
        self.save()
    
    @classmethod
    def gerar_alertas_automaticos(cls, empresa):
        """Gera alertas automáticos para a empresa"""
        from datetime import timedelta
        
        # Alertas de estoque baixo
        produtos_estoque_baixo = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        )
        
        for produto in produtos_estoque_baixo:
            estoque_atual = MovimentacaoEstoque.calcular_estoque_atual(produto, loja=produto.loja_padrao)
            
            if estoque_atual <= 0:
                # Alerta de estoque zerado
                cls.objects.get_or_create(
                    tipo_alerta='estoque_zerado',
                    produto=produto,
                    empresa=empresa,
                    ativo=True,
                    defaults={
                        'prioridade': 'critica',
                        'titulo': f'Estoque zerado: {produto.nome_produto}',
                        'descricao': f'O produto {produto.nome_produto} está com estoque zerado.',
                        'quantidade_atual': estoque_atual,
                        'quantidade_recomendada': produto.ponto_reposicao
                    }
                )
            elif estoque_atual <= produto.estoque_minimo:
                # Alerta de estoque baixo
                cls.objects.get_or_create(
                    tipo_alerta='estoque_baixo',
                    produto=produto,
                    empresa=empresa,
                    ativo=True,
                    defaults={
                        'prioridade': 'alta',
                        'titulo': f'Estoque baixo: {produto.nome_produto}',
                        'descricao': f'O produto {produto.nome_produto} está com estoque baixo ({estoque_atual} unidades).',
                        'quantidade_atual': estoque_atual,
                        'quantidade_recomendada': produto.ponto_reposicao
                    }
                )
        
        # Alertas de vencimento
        data_limite = date.today() + timedelta(days=30)
        lotes_vencendo = Lote.objects.filter(
            produto__empresa=empresa,
            data_validade__lte=data_limite,#era __lte=data_limite
            data_vencimento__gt=date.today(),
            quantidade_atual__gt=0,
            ativo=True
        )
        
        for lote in lotes_vencendo:
            dias_restantes = (lote.data_vencimento - date.today()).days
            
            cls.objects.get_or_create(
                tipo_alerta='vencimento_proximo',
                produto=lote.produto,
                lote=lote,
                empresa=empresa,
                ativo=True,
                defaults={
                    'prioridade': 'alta' if dias_restantes <= 7 else 'media',
                    'titulo': f'Vencimento próximo: {lote.produto.nome_produto}',
                    'descricao': f'Lote {lote.numero_lote} vence em {dias_restantes} dias ({lote.data_vencimento}).',
                    'quantidade_atual': lote.quantidade_atual
                }
            )

class LocalizacaoEstoque(models.Model):
    nome = models.CharField(max_length=100, unique=True, help_text="Nome do local ou setor do estoque")
    descricao = models.TextField(blank=True, null=True, help_text="Descrição opcional do local")
    ativo = models.BooleanField(default=True, help_text="Se o local está ativo e disponível para uso")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Localização"
        verbose_name_plural = "Localizações"
        ordering = ['nome']

    def __str__(self):
        return self.nome



# apps/fiscal/models.py
from django.db import models
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.core.choices import TIPO_RETENCAO_CHOICES
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from apps.core.models import Empresa, TimeStampedModel
from django.utils import timezone
from pharmassys import settings
import hashlib
import json
from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from apps.core.models import Empresa, TimeStampedModel
from apps.clientes.models import Cliente
from apps.produtos.models import Produto
from django.contrib.postgres.fields import JSONField


#log de auditoria para tentativa de download das chaves públicas
#Audit log para AGT
class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    acao = models.CharField(max_length=50)
    empresa_id = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()



class TaxaIVAAGT(TimeStampedModel):
    """
    Tabela Mestra de Impostos (Tax Table) conforme Requisitos AGT/SAF-T AO.
    Define as taxas e códigos legais para o IVA, Isenções (IS) e Não Sujeição (NS).
    """
    TAX_TYPE_CHOICES = [
        ('IVA', 'Imposto sobre o Valor Acrescentado (IVA)'),
        ('IS', 'Isenção'),
        ('NS', 'Não Sujeição'),
    ]
    
    TAX_CODE_CHOICES = [
        ('NOR', 'Normal'),
        ('INT', 'Intercalar'),
        ('RED', 'Reduzida'),
        ('ISE', 'Isento'), # Este é o mais comum para isenções
        ('NSU', 'Não Sujeito'), # Este é o mais comum para não sujeição
        # Adicionar mais códigos SAF-T se necessário
    ]
    
    TAX_EXEMPTION_REASON_CHOICES = [
        ('M99', 'Outras isenções (Art. 18.º CIVA)'),
        ('M01', 'Art. 13.º - Isenções nas Transmissões de Bens'),
        ('M02', 'Art. 14.º - Isenções nas Prestações de Serviços'),
        # Adicionar códigos específicos de Angola (ex: Isenções de Produtos Farmacêuticos)
    ]

    # Vínculo com a empresa para personalização, embora as taxas sejam tipicamente globais.
    empresa = models.ForeignKey(
        'core.Empresa', 
        on_delete=models.CASCADE, 
        related_name='taxas_iva'
    )
    
    # Detalhes Fiscais
    nome = models.CharField(max_length=100, help_text="Ex: IVA Taxa Normal 14%")
    codigo_pais = models.CharField(max_length=2, default='AO', editable=False) # Angola
    tax_type = models.CharField(max_length=3, choices=TAX_TYPE_CHOICES, verbose_name="Tipo de Imposto (TaxType)")
    tax_code = models.CharField(max_length=3, choices=TAX_CODE_CHOICES, verbose_name="Código da Taxa (TaxCode)")
    
    # Taxa (apenas aplicável se tax_type for 'IVA')
    tax_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Taxa em percentagem (e.g., 14.00)"
    )
    
    # Razão de Isenção (apenas aplicável se tax_type for 'IS' ou 'NS')
    exemption_reason = models.CharField(
        max_length=3, 
        choices=TAX_EXEMPTION_REASON_CHOICES, 
        blank=True, 
        null=True,
        verbose_name="Razão de Isenção (TaxExemptionCode)"
    )
    
    # Informação Legal
    legislacao_referencia = models.CharField(max_length=255, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Taxa de IVA (AGT)"
        verbose_name_plural = "Tabela de Impostos (AGT)"
        ordering = ['-tax_percentage', 'tax_type']
        
    def __str__(self):
        if self.tax_type == 'IVA':
            return f"{self.nome} ({self.tax_percentage}%)"
        return f"{self.nome} ({self.tax_type} - {self.exemption_reason})"


# apps/fiscal/services/assinatura_service.py
import base64
import hashlib
import json
import logging
from typing import Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend

from decimal import Decimal


logger = logging.getLogger(__name__)




class AssinaturaDigital(TimeStampedModel):
    """
    Armazena a chave pública/privada (RSA) ou apenas a chave de hash,
    utilizada para assinar documentos e garantir a cadeia de integridade.
    """
    empresa = models.OneToOneField(
        'core.Empresa', 
        on_delete=models.CASCADE, 
        related_name='assinatura_fiscal'
    )
    
    # O hash do último documento emitido na série de documentos da empresa. 
    # CRÍTICO para a Geração do ATCUD e Cadeia de Integridade.
    ultimo_hash = models.CharField(
        max_length=256, 
        blank=True, 
        null=True, 
        verbose_name="Último Hash em Cadeia (SAF-T)"
    )
    
    chave_privada = models.TextField(blank=True, null=True, help_text="Chave privada RSA cifrada (Fernet). Mantenha em segredo")

    chave_publica = models.TextField(blank=True, null=True, help_text="Chave pública RSA PEM.")
    
    dados_series_fiscais = models.JSONField(default=dict, blank=True, verbose_name="Dados de Hash e Código AGT por Série")
    
    data_geracao = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Assinatura Fiscal"
        verbose_name_plural = "Assinaturas Fiscais"

    def __str__(self):
        return f"Assinatura Fiscal de {self.empresa.nome}"




class RetencaoFonte(TimeStampedModel):
    """
    Registo das Retenções na Fonte efetuadas pela empresa (pagador).
    Essencial para o bloco <WithholdingTax> do SAF-T.
    """
    # Identificação
    referencia_documento = models.CharField(max_length=50, help_text="Ex: Número da Fatura do Fornecedor ou Recibo")
    data_retencao = models.DateField(help_text="Data em que a retenção foi efetuada (geralmente data de pagamento)")
    
    # Valores
    valor_base = models.DecimalField(max_digits=12, decimal_places=2, help_text="Base tributável da retenção")
    
    valor_retido = models.DecimalField(max_digits=12, decimal_places=2, help_text="Valor efetivamente retido")
    
    # Classificação Fiscal
    taxa_retencao = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentual da retenção aplicada sobre o valor base"
    )
    tipo_retencao = models.CharField(
        max_length=10, 
        choices=TIPO_RETENCAO_CHOICES, 
        help_text="Tipo de imposto retido (código SAF-T obrigatório - ex: IRPC, IRT)"
    )
    codigo_tributario = models.CharField(max_length=50, blank=True, help_text="Código da Secção/Artigo da lei fiscal (se aplicável)")
    
    # Rastreamento Contábil
    conta_pagar = models.ForeignKey(
        'financeiro.ContaPagar', 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        help_text="Conta a pagar que gerou esta retenção"
    )
    fornecedor = models.ForeignKey(
        'fornecedores.Fornecedor', 
        on_delete=models.PROTECT, 
        help_text="Fornecedor/Prestador de serviço a quem foi efetuada a retenção"
    )
    
    # Controle
    paga_ao_estado = models.BooleanField(default=False, help_text="Indica se o valor retido já foi pago ao Estado")
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Retenção na Fonte"
        verbose_name_plural = "Retenções na Fonte"
        ordering = ['-data_retencao']

    def save(self, *args, **kwargs):
        # 🚨 Lógica de Negócio Obrigatória: Cálculo do valor retido
        if self.valor_base and self.taxa_retencao:
            self.valor_retido = self.valor_base * (self.taxa_retencao / Decimal('100.00'))
        
        # 🚨 Hook Contábil: Deve ser gerado um LançamentoFinanceiro aqui (ex: Débito em Passivo (Impostos a Pagar), Crédito em ContaPagar)
        self.gerar_lancamento_contabil() 
        
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Retenção {self.tipo_retencao} de {self.valor_retido} em {self.data_retencao}"



class DocumentoFiscal(TimeStampedModel):
    """
    Modelo principal para documentos fiscais (Faturas, Notas de Crédito, etc.)
    Compatível com SAF-T Angola e AGT.
    Suporta assinatura digital e cadeia de integridade.
    """
    
    # Tipos de Documento conforme SAF-T AO
    TIPO_DOCUMENTO_CHOICES = [
        ('FT', 'Fatura Crédito'),
        ('REC', 'Recibo'),
        ('FR', 'Fatura-Recibo'),
        ('NC', 'Nota de Crédito'),
        ('ND', 'Nota de Débito'),
        ('DT', 'Documento de Transporte'),
        ('VD', 'Venda a Dinheiro'),
        ('TV', 'Talão de Venda'),
        ('TD', 'Talão de Devolução'),
        ('AA', 'Alienação de Ativos'),
        ('DA', 'Devolução de Ativos'),
        ('RP', 'Prémio ou Penalização'),
        ('RE', 'Estorno ou Anulação'),
        ('CS', 'Imputação a Co-Produtos'),
        ('LD', 'Lançamentos Diversos'),
        ('RA', 'Resseguro Aceite'),
        ('RC', 'Resseguro Cedido'),
    ]
    
    # Status do Documento
    STATUS_CHOICES = [
        ('draft', 'Rascunho'),
        ('confirmed', 'Confirmado'),
        ('posted', 'Lançado'),
        ('paid', 'Pago'),
        ('cancelled', 'Cancelado'),
        ('rectified', 'Retificado'),
    ]
    
    # Origem do Documento
    ORIGEM_CHOICES = [
        ('manual', 'Manual'),
        ('sistema', 'Sistema'),
        ('importacao', 'Importação'),
        ('api', 'API Externa'),
        ('edi', 'EDI'),
    ]
    
    # Tipo de Cliente/Regime
    TIPO_CLIENTE_CHOICES = [
        ('particular', 'Particular'),
        ('empresa', 'Empresa'),
        ('isento', 'Isento de IVA'),
        ('nao_residente', 'Não Residente'),
        ('regime_especial', 'Regime Especial'),
    ]

    # ==========================================
    # IDENTIFICAÇÃO DO DOCUMENTO
    # ==========================================
    
    empresa = models.ForeignKey(
        'core.Empresa',
        on_delete=models.CASCADE,
        related_name='documentos_fiscais'
    )
    
    # Numeração Sequencial Obrigatória (SAF-T)
    tipo_documento = models.CharField(
        max_length=3,
        choices=TIPO_DOCUMENTO_CHOICES,
        verbose_name="Tipo de Documento"
    )
    
    serie = models.CharField(
        max_length=10,
        default='A',
        help_text="Série do documento (ex: A, B, C, 2024A)"
    )
    
    numero = models.PositiveIntegerField(
        verbose_name="Número do Documento",
        help_text="Número sequencial dentro da série"
    )
    
    numero_documento = models.CharField(
        max_length=50,
        verbose_name="Número Completo",
        help_text="Formato: TIPO SERIE/NUMERO (ex: FT A/1234)",
        editable=False
    )
    
    # ATCUD (Código Único de Documento - Obrigatório AGT)
    atcud = models.CharField(
        max_length=70,
        verbose_name="ATCUD",
        help_text="Código Único de Documento gerado pelo sistema",
        editable=False,
        db_index=True
    )
    
    # ==========================================
    # DADOS TEMPORAIS
    # ==========================================
    
    data_emissao = models.DateField(
        verbose_name="Data de Emissão",
        help_text="Data de emissão do documento"
    )
    
    data_vencimento = models.DateField(
        blank=True,
        null=True,
        verbose_name="Data de Vencimento",
        help_text="Data de vencimento para documentos a prazo"
    )
    
    data_operacao = models.DateField(
        blank=True,
        null=True,
        verbose_name="Data da Operação",
        help_text="Data efetiva da operação (se diferente da emissão)"
    )
    
    hora_emissao = models.TimeField(
        auto_now_add=True,
        verbose_name="Hora de Emissão"
    )
    
    # ==========================================
    # PARTES ENVOLVIDAS
    # ==========================================
    
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        related_name='documentos_fiscais',
        blank=True,
        null=True,
        verbose_name="Cliente"
    )
    
    # Dados do Cliente (snapshot no momento da emissão)
    cliente_nome = models.CharField(
        max_length=200,
        verbose_name="Nome do Cliente"
    )
    
    cliente_nif = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="NIF do Cliente"
    )
    
    cliente_endereco = models.TextField(
        blank=True,
        verbose_name="Endereço do Cliente"
    )
    
    cliente_email = models.EmailField(
        blank=True,
        verbose_name="Email do Cliente"
    )
    
    cliente_telefone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Telefone do Cliente"
    )
    
    tipo_cliente = models.CharField(
        max_length=20,
        choices=TIPO_CLIENTE_CHOICES,
        default='particular',
        verbose_name="Tipo de Cliente"
    )
    
    # ==========================================
    # VALORES E IMPOSTOS
    # ==========================================
    
    # Valores Base
    valor_base = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor Base (sem IVA)",
        help_text="Soma de todas as linhas sem IVA"
    )
    
    valor_iva = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor do IVA",
        help_text="Soma de todo o IVA aplicado"
    )
    
    valor_desconto = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor de Desconto",
        help_text="Desconto total aplicado"
    )
    
    valor_retencao = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor de Retenção na Fonte",
        help_text="Retenção aplicada (se aplicável)"
    )
    
    valor_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor Total",
        help_text="Valor final a pagar/receber"
    )
    
    # Moeda
    moeda = models.CharField(
        max_length=3,
        default='AOA',
        verbose_name="Moeda",
        help_text="Código ISO da moeda (ex: AOA, USD, EUR)"
    )
    
    taxa_cambio = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal('1.000000'),
        validators=[MinValueValidator(Decimal('0.000001'))],
        verbose_name="Taxa de Câmbio",
        help_text="Taxa de conversão para AOA (se aplicável)"
    )
    
    # ==========================================
    # INFORMAÇÕES ADICIONAIS
    # ==========================================
    
    observacoes = models.TextField(
        blank=True,
        verbose_name="Observações",
        help_text="Observações ou notas adicionais"
    )
    
    referencia_externa = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Referência Externa",
        help_text="Número de referência do cliente ou sistema externo"
    )
    
    condicoes_pagamento = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Condições de Pagamento",
        help_text="Ex: Pronto pagamento, 30 dias, etc."
    )
    
    forma_pagamento = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Forma de Pagamento",
        help_text="Ex: Dinheiro, Transferência, Cartão"
    )
    
    # ==========================================
    # CONTROLE E STATUS
    # ==========================================
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Status"
    )
    
    origem = models.CharField(
        max_length=20,
        choices=ORIGEM_CHOICES,
        default='manual',
        verbose_name="Origem"
    )
    
    # ==========================================
    # ASSINATURA DIGITAL E INTEGRIDADE
    # ==========================================
    
    hash_documento = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash do Documento",
        help_text="SHA-256 do conteúdo do documento",
        editable=False
    )
    
    hash_anterior = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash do Documento Anterior",
        help_text="Hash do documento anterior da mesma série",
        editable=False
    )
    
    assinatura_digital = models.TextField(
        blank=True,
        verbose_name="Assinatura Digital",
        help_text="Assinatura RSA do hash do documento",
        editable=False
    )
    
    # ==========================================
    # RASTREABILIDADE E AUDITORIA
    # ==========================================
    
    usuario_criacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_criados',
        verbose_name="Criado por"
    )
    
    usuario_modificacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_modificados',
        blank=True,
        null=True,
        verbose_name="Modificado por"
    )
    
    data_confirmacao = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Data de Confirmação"
    )
    
    usuario_confirmacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_confirmados',
        blank=True,
        null=True,
        verbose_name="Confirmado por"
    )
    
    # ==========================================
    # DADOS SAF-T ESPECÍFICOS
    # ==========================================
    
    # Campos específicos para exportação SAF-T
    saft_hash = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash SAF-T",
        help_text="Hash específico para SAF-T",
        editable=False
    )
    
    periodo_tributacao = models.CharField(
        max_length=7,
        verbose_name="Período de Tributação",
        help_text="Formato YYYY-MM para SAF-T",
        editable=False
    )
    
    # ==========================================
    # METADADOS
    # ==========================================
    
    metadados = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadados",
        help_text="Dados adicionais em formato JSON"
    )

    class Meta:
        verbose_name = "Documento Fiscal"
        verbose_name_plural = "Documentos Fiscais"
        ordering = ['-data_emissao', '-numero']
        
        # Constraints para garantir unicidade
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'tipo_documento', 'serie', 'numero'],
                name='unique_documento_por_empresa_serie'
            ),
            models.UniqueConstraint(
                fields=['empresa', 'atcud'],
                name='unique_atcud_por_empresa'
            ),
        ]
        
        # Índices para performance
        indexes = [
            models.Index(fields=['empresa', 'data_emissao']),
            models.Index(fields=['empresa', 'status']),
            models.Index(fields=['cliente', 'data_emissao']),
            models.Index(fields=['numero_documento']),
            models.Index(fields=['atcud']),
            models.Index(fields=['hash_documento']),
        ]

    def clean(self):
        """Validações customizadas do modelo."""
        super().clean()
        
        # Validar datas
        if self.data_vencimento and self.data_vencimento < self.data_emissao:
            raise ValidationError({
                'data_vencimento': 'Data de vencimento não pode ser anterior à data de emissão.'
            })
        
        # Validar valores
        if self.valor_total < 0:
            raise ValidationError({
                'valor_total': 'Valor total não pode ser negativo.'
            })
        
        # Validar consistência de valores
        valor_calculado = self.valor_base + self.valor_iva - self.valor_desconto - self.valor_retencao
        if abs(valor_calculado - self.valor_total) > Decimal('0.01'):
            raise ValidationError({
                'valor_total': f'Valor total inconsistente. Esperado: {valor_calculado}'
            })
        
        # Validar NIF se cliente for empresa
        if self.tipo_cliente == 'empresa' and not self.cliente_nif:
            raise ValidationError({
                'cliente_nif': 'NIF é obrigatório para clientes empresariais.'
            })

    def save(self, *args, **kwargs):
        """Override do save para aplicar lógica de negócio."""
        
        # Gerar número do documento se novo
        if not self.pk:
            self._gerar_numero_documento()
            self._gerar_atcud()
            self._definir_periodo_tributacao()
        
        # Gerar hash e assinatura se documento confirmado
        if self.status == 'confirmed' and not self.hash_documento:
            self._gerar_hash_documento()
            self._aplicar_assinatura_digital()
        
        # Atualizar campos calculados
        self._atualizar_campos_calculados()
        
        super().save(*args, **kwargs)
        
        # Atualizar hash da cadeia após salvar
        if self.status == 'confirmed':
            self._atualizar_cadeia_integridade()

    def _gerar_numero_documento(self):
        """Gera numeração sequencial por série."""
        with transaction.atomic():
            ultimo_doc = DocumentoFiscal.objects.filter(
                empresa=self.empresa,
                tipo_documento=self.tipo_documento,
                serie=self.serie
            ).order_by('-numero').first()
            
            self.numero = (ultimo_doc.numero + 1) if ultimo_doc else 1
            self.numero_documento = f"{self.tipo_documento} {self.serie}/{self.numero}"

    def _gerar_atcud(self):
        """Gera ATCUD conforme especificação AGT."""
        from django.utils import timezone
        
        # Formato: EMPRESA_SERIE_NUMERO_TIMESTAMP
        timestamp = int(timezone.now().timestamp())
        self.atcud = f"{self.empresa.nif}_{self.tipo_documento}_{self.serie}_{self.numero}_{timestamp}"

    def _definir_periodo_tributacao(self):
        """Define período de tributação para SAF-T."""
        self.periodo_tributacao = self.data_emissao.strftime('%Y-%m')

    def _gerar_hash_documento(self):
        """Gera hash SHA-256 do conteúdo do documento."""
        # Dados para hash (ordem importante para consistência)
        dados_hash = {
            'atcud': self.atcud,
            'numero_documento': self.numero_documento,
            'data_emissao': self.data_emissao.isoformat(),
            'cliente_nif': self.cliente_nif or '',
            'valor_total': str(self.valor_total),
            'moeda': self.moeda,
        }
        
        # Incluir hash anterior para cadeia de integridade
        if self.hash_anterior:
            dados_hash['hash_anterior'] = self.hash_anterior
        
        # Gerar hash
        dados_json = json.dumps(dados_hash, sort_keys=True, ensure_ascii=False)
        self.hash_documento = hashlib.sha256(dados_json.encode('utf-8')).hexdigest()

    def _aplicar_assinatura_digital(self):
        """Aplica assinatura digital RSA ao hash do documento."""
        try:
            assinatura_obj = AssinaturaDigital.objects.get(empresa=self.empresa)
            
            if assinatura_obj.chave_privada:
                # Aqui você implementaria a assinatura RSA real
                # Por ora, vamos usar um placeholder
                self.assinatura_digital = f"RSA_SIGNATURE_{self.hash_documento[:32]}"
                
        except AssinaturaDigital.DoesNotExist:
            # Log warning but don't fail
            pass

    def _atualizar_campos_calculados(self):
        """Atualiza campos calculados automaticamente."""
        # Atualizar dados do cliente se vinculado
        if self.cliente:
            self.cliente_nome = self.cliente.nome_exibicao
            self.cliente_nif = self.cliente.nif or ''
            self.cliente_endereco = str(self.cliente.endereco) if hasattr(self.cliente, 'endereco') else ''
            self.cliente_email = self.cliente.email or ''
            self.cliente_telefone = self.cliente.telefone or ''

    def _atualizar_cadeia_integridade(self):
        """Atualiza cadeia de integridade e último hash na AssinaturaDigital."""
        try:
            assinatura_obj = AssinaturaDigital.objects.get(empresa=self.empresa)
            
            # Atualizar dados da série fiscal
            if not assinatura_obj.dados_series_fiscais:
                assinatura_obj.dados_series_fiscais = {}
            
            serie_key = f"{self.tipo_documento}_{self.serie}"
            assinatura_obj.dados_series_fiscais[serie_key] = {
                'ultimo_hash': self.hash_documento,
                'ultimo_documento': self.numero_documento,
                'data_ultima_assinatura': datetime.now().isoformat(),
                'total_documentos': DocumentoFiscal.objects.filter(
                    empresa=self.empresa,
                    tipo_documento=self.tipo_documento,
                    serie=self.serie,
                    status='confirmed'
                ).count()
            }
            
            # Atualizar hash geral
            assinatura_obj.ultimo_hash = self.hash_documento
            assinatura_obj.save()
            
        except AssinaturaDigital.DoesNotExist:
            # Criar assinatura se não existir
            AssinaturaDigital.objects.create(
                empresa=self.empresa,
                ultimo_hash=self.hash_documento,
                dados_series_fiscais={
                    f"{self.tipo_documento}_{self.serie}": {
                        'ultimo_hash': self.hash_documento,
                        'ultimo_documento': self.numero_documento,
                        'data_ultima_assinatura': datetime.now().isoformat(),
                        'total_documentos': 1
                    }
                }
            )

    def confirmar_documento(self, usuario):
        """Confirma o documento e aplica assinatura digital."""
        if self.status != 'draft':
            raise ValidationError("Apenas documentos em rascunho podem ser confirmados.")
        
        self.status = 'confirmed'
        self.usuario_confirmacao = usuario
        self.data_confirmacao = timezone.now()
        
        # Buscar hash do documento anterior
        doc_anterior = DocumentoFiscal.objects.filter(
            empresa=self.empresa,
            tipo_documento=self.tipo_documento,
            serie=self.serie,
            numero__lt=self.numero,
            status='confirmed'
        ).order_by('-numero').first()
        
        if doc_anterior:
            self.hash_anterior = doc_anterior.hash_documento
        
        self.save()

    def cancelar_documento(self, usuario, motivo=''):
        """Cancela o documento."""
        if self.status in ['cancelled', 'paid']:
            raise ValidationError(f"Documento não pode ser cancelado no status '{self.status}'.")
        
        self.status = 'cancelled'
        self.usuario_modificacao = usuario
        
        # Adicionar motivo aos metadados
        if not self.metadados:
            self.metadados = {}
        self.metadados['cancelamento'] = {
            'motivo': motivo,
            'data': datetime.now().isoformat(),
            'usuario': usuario.username
        }
        
        self.save()

    def gerar_pdf(self):
        """Gera PDF do documento (placeholder)."""
        # Implementar geração de PDF
        pass

    def enviar_email(self, destinatario=None):
        """Envia documento por email (placeholder)."""
        # Implementar envio por email
        pass

    @property
    def pode_editar(self):
        """Verifica se o documento pode ser editado."""
        return self.status == 'draft'

    @property
    def pode_cancelar(self):
        """Verifica se o documento pode ser cancelado."""
        return self.status in ['draft', 'confirmed']

    @property
    def valor_liquido(self):
        """Retorna valor líquido (total - retenção)."""
        return self.valor_total - self.valor_retencao

    @property
    def taxa_iva_media(self):
        """Calcula taxa média de IVA aplicada."""
        if self.valor_base > 0:
            return (self.valor_iva / self.valor_base) * 100
        return Decimal('0.00')

    def __str__(self):
        return f"{self.numero_documento} - {self.cliente_nome} - {self.valor_total} {self.moeda}"


class DocumentoFiscalLinha(TimeStampedModel):
    """
    Linhas/itens de um documento fiscal.
    Representa cada produto/serviço no documento.
    """
    
    documento = models.ForeignKey(
        DocumentoFiscal,
        on_delete=models.CASCADE,
        related_name='linhas'
    )
    
    # Identificação do Item
    numero_linha = models.PositiveIntegerField(
        verbose_name="Número da Linha"
    )
    
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name="Produto"
    )
    
    # Dados do Produto (snapshot)
    codigo_produto = models.CharField(
        max_length=50,
        verbose_name="Código do Produto"
    )
    
    descricao = models.CharField(
        max_length=200,
        verbose_name="Descrição"
    )
    
    unidade = models.CharField(
        max_length=10,
        default='UN',
        verbose_name="Unidade de Medida"
    )
    
    # Quantidades e Valores
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name="Quantidade"
    )
    
    preco_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        verbose_name="Preço Unitário"
    )
    
    valor_desconto_linha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Desconto da Linha"
    )
    
    valor_liquido = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor Líquido",
        help_text="Quantidade × Preço - Desconto",
        editable=False
    )
    
    # IVA
    taxa_iva = models.ForeignKey(
        TaxaIVAAGT,
        on_delete=models.PROTECT,
        verbose_name="Taxa de IVA"
    )
    
    valor_iva_linha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor IVA da Linha",
        editable=False
    )
    
    valor_total_linha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor Total da Linha",
        editable=False
    )
    
    # Informações Adicionais
    observacoes_linha = models.TextField(
        blank=True,
        verbose_name="Observações da Linha"
    )

    class Meta:
        verbose_name = "Linha de Documento Fiscal"
        verbose_name_plural = "Linhas de Documentos Fiscais"
        ordering = ['numero_linha']
        
        constraints = [
            models.UniqueConstraint(
                fields=['documento', 'numero_linha'],
                name='unique_linha_por_documento'
            ),
        ]

    def clean(self):
        """Validações da linha."""
        super().clean()
        
        if self.quantidade <= 0:
            raise ValidationError({
                'quantidade': 'Quantidade deve ser maior que zero.'
            })
        
        if self.preco_unitario < 0:
            raise ValidationError({
                'preco_unitario': 'Preço unitário não pode ser negativo.'
            })

    def save(self, *args, **kwargs):
        """Calcula valores automaticamente."""
        
        # Calcular valor líquido
        self.valor_liquido = (self.quantidade * self.preco_unitario) - self.valor_desconto_linha
        
        # Calcular IVA
        if self.taxa_iva.tax_type == 'IVA':
            self.valor_iva_linha = self.valor_liquido * (self.taxa_iva.tax_percentage / Decimal('100'))
        else:
            self.valor_iva_linha = Decimal('0.00')
        
        # Calcular total da linha
        self.valor_total_linha = self.valor_liquido + self.valor_iva_linha
        
        super().save(*args, **kwargs)
        
        # Atualizar totais do documento
        self._atualizar_totais_documento()

    def _atualizar_totais_documento(self):
        """Atualiza os totais do documento pai."""
        from django.db.models import Sum
        
        documento = self.documento
        
        # Somar todas as linhas
        totais = documento.linhas.aggregate(
            total_base=Sum('valor_liquido'),
            total_iva=Sum('valor_iva_linha'),
            total_desconto=Sum('valor_desconto_linha'),
            total_geral=Sum('valor_total_linha')
        )
        
        documento.valor_base = totais['total_base'] or Decimal('0.00')
        documento.valor_iva = totais['total_iva'] or Decimal('0.00')
        documento.valor_desconto = totais['total_desconto'] or Decimal('0.00')
        documento.valor_total = totais['total_geral'] or Decimal('0.00')
        
        # Salvar sem triggerar signals para evitar loop
        DocumentoFiscal.objects.filter(pk=documento.pk).update(
            valor_base=documento.valor_base,
            valor_iva=documento.valor_iva,
            valor_desconto=documento.valor_desconto,
            valor_total=documento.valor_total
        )

    def __str__(self):
        return f"Linha {self.numero_linha}: {self.descricao} - {self.quantidade} × {self.preco_unitario}"


class SAFTExport(TimeStampedModel):
    """
    Registro dos arquivos SAF-T exportados.
    Serve para auditoria, rastreabilidade e reenvio.
    Compatível com SAF-T Angola / AGT.
    """

    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('gerado', 'Gerado'),
        ('enviado', 'Enviado'),
        ('falhou', 'Falhou'),
    ]

    empresa = models.ForeignKey(
        'core.Empresa',
        on_delete=models.CASCADE,
        related_name='saft_exports',
        verbose_name="Empresa"
    )

    # Identificação do arquivo
    periodo_tributacao = models.CharField(
        max_length=7,
        verbose_name="Período de Tributação",
        help_text="Formato YYYY-MM",
    )
    nome_arquivo = models.CharField(
        max_length=255,
        verbose_name="Nome do Arquivo SAF-T",
        help_text="Ex: SAFT_2025-10_AOA.xml"
    )
    caminho_arquivo = models.FileField(
        upload_to='saft_exports/',
        verbose_name="Arquivo SAF-T",
        help_text="Arquivo XML gerado para envio AGT/SAF-T"
    )
    hash_arquivo = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash SHA-256 do arquivo",
        help_text="Garantia de integridade do arquivo SAF-T"
    )

    # Status de exportação
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Status do Export"
    )
    
    # Logs e auditoria
    log_geracao = models.TextField(
        blank=True,
        verbose_name="Log de Geração",
        help_text="Mensagens ou erros durante a geração do SAF-T"
    )
    log_envio = models.TextField(
        blank=True,
        verbose_name="Log de Envio",
        help_text="Mensagens ou erros durante o envio para AGT"
    )

    # Controle de usuários
    usuario_geracao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='saft_gerados',
        verbose_name="Gerado por"
    )
    usuario_envio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='saft_enviados',
        blank=True,
        null=True,
        verbose_name="Enviado por"
    )
    data_envio = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Data de Envio"
    )
    

    class Meta:
        verbose_name = "Exportação SAF-T"
        verbose_name_plural = "Exportações SAF-T"
        ordering = ['-periodo_tributacao', '-created_at']

        indexes = [
            models.Index(fields=['empresa', 'periodo_tributacao']),
            models.Index(fields=['status']),
            models.Index(fields=['hash_arquivo']),
        ]

    def __str__(self):
        return f"SAFT {self.periodo_tributacao} - {self.empresa.nome} ({self.status})"

    def marcar_gerado(self, hash_val):
        """Marca o arquivo como gerado e salva o hash."""
        self.status = 'gerado'
        self.hash_arquivo = hash_val
        self.save(update_fields=['status', 'hash_arquivo', 'updated_at'])

    def marcar_enviado(self, usuario):
        """Marca o arquivo como enviado."""
        self.status = 'enviado'
        self.usuario_envio = usuario
        self.data_envio = timezone.now()
        self.save(update_fields=['status', 'usuario_envio', 'data_envio', 'updated_at'])

    def registrar_erro(self, log_texto, envio=False):
        """Registra logs de erro na geração ou envio."""
        if envio:
            self.log_envio += f"{timezone.now().isoformat()} - {log_texto}\n"
            self.status = 'falhou'
            self.save(update_fields=['log_envio', 'status', 'updated_at'])
        else:
            self.log_geracao += f"{timezone.now().isoformat()} - {log_texto}\n"
            self.status = 'falhou'
            self.save(update_fields=['log_geracao', 'status', 'updated_at'])


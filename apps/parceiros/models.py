# apps/parceiros/models.py
"""
Portal de Parceiros — VistoGest Pro / SOTARQ Software.

Secção 6 do PLANO_IMPLEMENTACAO.md.

DOIS TIPOS DE LICENÇA — NÃO CONFUNDIR:
  A) Licença do Parceiro (PartnerLicense): autoriza um parceiro a operar o Portal.
     Define duração, limites de quota, planos de cliente autorizados.
  B) Licença do Cliente (apps.licenca.Licenca): licença do tenant no VistoGest.
     Já existe. O parceiro apenas a vincula — NUNCA a cria ou altera.

ARQUITETURA:
  - Todos os modelos desta app são SHARED_APPS (schema public).
  - Parceiro tem conta Usuario (AUTH_USER_MODEL) — não é um tenant.
  - PartnerClient liga Partner ↔ Empresa (tenant) no schema public.
  - Quota protegida contra concorrência via PartnerQuotaUsage + select_for_update.
  - Tokens armazenados apenas como hash SHA-256 (nunca em claro).
"""

import hashlib
import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel


# ─────────────────────────────────────────────────────────────────────────────
# Partner — o parceiro comercial externo
# ─────────────────────────────────────────────────────────────────────────────

class Partner(TimeStampedModel):
    """
    Representa um parceiro comercial da SOTARQ.
    O parceiro tem acesso ao Portal de Parceiros (/portal-parceiros/)
    e pode cadastrar clientes (empresas/tenants) no VistoGest.

    NÃO confundir com os funcionários da SOTARQ que gerem o programa de parceiros
    (Gerente/Operador Parceiros) — esses são autenticados como staff normal.
    """
    TIPO_CHOICES = [
        ('pessoa_singular', 'Pessoa Singular'),
        ('empresa',         'Empresa'),
    ]
    STATUS_CHOICES = [
        ('activo',    'Activo'),
        ('suspenso',  'Suspenso'),
        ('inactivo',  'Inactivo'),
        ('cancelado', 'Cancelado'),
    ]

    # Conta de acesso ao portal
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='partner_profile',
        verbose_name='Utilizador',
    )
    nome    = models.CharField(max_length=200, verbose_name='Nome')
    tipo    = models.CharField(max_length=20, choices=TIPO_CHOICES, default='empresa')
    nif     = models.CharField(max_length=20, blank=True, verbose_name='NIF')
    telefone = models.CharField(max_length=20, blank=True)
    email   = models.EmailField()
    endereco = models.TextField(blank=True)
    status  = models.CharField(max_length=15, choices=STATUS_CHOICES, default='activo')
    registado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='parceiros_registados',
        verbose_name='Registado por',
        help_text='Funcionário SOTARQ que criou este parceiro.',
    )
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Parceiro'
        verbose_name_plural = 'Parceiros'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.get_status_display()})"

    @property
    def licenca_activa(self):
        """Devolve a licença activa do parceiro, ou None."""
        return self.licencas.filter(status='activa').order_by('-data_expiracao').first()

    @property
    def esta_activo(self):
        return self.status == 'activo' and bool(self.licenca_activa)


# ─────────────────────────────────────────────────────────────────────────────
# PartnerLicensePlan — planos de licença DO parceiro (criados pelo Admin Global)
# ─────────────────────────────────────────────────────────────────────────────

class PartnerLicensePlan(TimeStampedModel):
    """
    Plano de licença para parceiros — DIFERENTE dos planos de licença de clientes.
    Criado e gerido pelo Admin Global da SOTARQ.
    Define: preço, duração, limites de quota, planos de cliente autorizados.
    """
    DURACAO_CHOICES = [
        ('dias',   'Dias'),
        ('meses',  'Meses'),
        ('anos',   'Anos'),
    ]

    nome        = models.CharField(max_length=100)
    descricao   = models.TextField(blank=True)
    preco       = models.DecimalField(max_digits=12, decimal_places=2)
    moeda       = models.CharField(max_length=3, default='AOA')
    duracao     = models.IntegerField(default=1, help_text='Quantidade de unidades de duração.')
    unidade_duracao = models.CharField(max_length=6, choices=DURACAO_CHOICES, default='meses')

    renovacao_automatica = models.BooleanField(default=False)
    permite_renovacao    = models.BooleanField(default=True)
    permite_upgrade      = models.BooleanField(default=True)
    permite_downgrade    = models.BooleanField(default=False)

    # Limites de quota
    max_empresas_total = models.IntegerField(
        default=0,
        help_text='Máximo total de empresas que pode licenciar. 0 = ilimitado.',
    )
    max_empresas_mes = models.IntegerField(
        default=0,
        help_text='Máximo de novas empresas por mês. 0 = ilimitado.',
    )

    # Planos de cliente que o parceiro COM ESTE PLANO pode oferecer.
    # Reutiliza PlanoLicenca da app licenca existente — NÃO duplicar.
    planos_cliente_autorizados = models.ManyToManyField(
        'licenca.PlanoLicenca',
        blank=True,
        related_name='planos_parceiro_autorizados',
        verbose_name='Planos de Cliente Autorizados',
        help_text=(
            'Planos de licença de cliente que parceiros com este plano '
            'estão autorizados a oferecer. O parceiro NÃO cria estes planos.'
        ),
    )

    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Plano de Licença de Parceiro'
        verbose_name_plural = 'Planos de Licença de Parceiro'
        ordering = ['preco']

    def __str__(self):
        return f"{self.nome} ({self.preco} {self.moeda}/{self.duracao} {self.unidade_duracao})"


# ─────────────────────────────────────────────────────────────────────────────
# PartnerToken — tokens de activação/renovação (hash apenas, nunca em claro)
# ─────────────────────────────────────────────────────────────────────────────

class PartnerToken(TimeStampedModel):
    """
    Token de uso único para activar, renovar ou fazer upgrade de uma licença.
    Armazenado apenas como SHA-256 — o valor em claro é gerado uma única vez
    e entregue ao parceiro, nunca guardado aqui.
    """
    TIPO_CHOICES = [
        ('activacao', 'Activação'),
        ('renovacao', 'Renovação'),
        ('upgrade',   'Upgrade'),
    ]
    STATUS_CHOICES = [
        ('disponivel', 'Disponível'),
        ('utilizado',  'Utilizado'),
        ('expirado',   'Expirado'),
        ('cancelado',  'Cancelado'),
    ]

    partner      = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='tokens')
    tipo         = models.CharField(max_length=15, choices=TIPO_CHOICES)
    status       = models.CharField(max_length=15, choices=STATUS_CHOICES, default='disponivel')
    # SHA-256 do token — nunca o valor em claro
    token_hash   = models.CharField(max_length=256, unique=True, verbose_name='Hash do Token')
    criado_por   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='tokens_parceiro_criados'
    )
    utilizado_em = models.DateTimeField(null=True, blank=True)
    expira_em    = models.DateTimeField(null=True, blank=True)
    plano_destino = models.ForeignKey(
        PartnerLicensePlan, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='tokens_destino',
        help_text='Plano para o qual este token é válido.',
    )

    class Meta:
        verbose_name = 'Token de Parceiro'
        verbose_name_plural = 'Tokens de Parceiro'

    def __str__(self):
        return f"Token {self.tipo} ({self.partner.nome}) [{self.status}]"

    @classmethod
    def gerar(cls, partner, tipo, plano_destino=None, criado_por=None, validade_horas=72):
        """
        Gera um token seguro. Devolve (instancia_token, valor_em_claro).
        O valor_em_claro deve ser entregue ao parceiro e NÃO armazenado.
        """
        valor = secrets.token_urlsafe(32)
        hash_val = hashlib.sha256(valor.encode()).hexdigest()
        expira_em = timezone.now() + timezone.timedelta(hours=validade_horas)
        token = cls.objects.create(
            partner=partner,
            tipo=tipo,
            token_hash=hash_val,
            criado_por=criado_por,
            expira_em=expira_em,
            plano_destino=plano_destino,
        )
        return token, valor

    @classmethod
    def validar(cls, partner, valor_em_claro, tipo=None):
        """
        Valida o token. Devolve o objecto PartnerToken se válido, ou levanta ValueError.
        Verifica: hash correcto, partner correcto, status disponivel, não expirado.
        """
        hash_val = hashlib.sha256(valor_em_claro.encode()).hexdigest()
        try:
            token = cls.objects.get(token_hash=hash_val)
        except cls.DoesNotExist:
            raise ValueError("Token inválido.")

        if token.partner_id != partner.pk:
            raise ValueError("Este token não pertence a este parceiro.")
        if token.status != 'disponivel':
            raise ValueError(f"Token já foi {token.get_status_display().lower()}.")
        if tipo and token.tipo != tipo:
            raise ValueError(f"Token do tipo errado (esperado: {tipo}).")
        if token.expira_em and timezone.now() > token.expira_em:
            token.status = 'expirado'
            token.save(update_fields=['status'])
            raise ValueError("Token expirado.")
        return token

    def marcar_utilizado(self):
        self.status = 'utilizado'
        self.utilizado_em = timezone.now()
        self.save(update_fields=['status', 'utilizado_em'])


# ─────────────────────────────────────────────────────────────────────────────
# PartnerLicense — licença activa do parceiro
# ─────────────────────────────────────────────────────────────────────────────

class PartnerLicense(TimeStampedModel):
    """
    Licença efectivamente atribuída a um parceiro.
    Controla estado, datas, quota utilizada e planos autorizados.
    """
    STATUS_CHOICES = [
        ('pendente',  'Pendente Activação'),
        ('activa',    'Activa'),
        ('expirada',  'Expirada'),
        ('suspensa',  'Suspensa'),
        ('cancelada', 'Cancelada'),
    ]
    METODO_PAGAMENTO_CHOICES = [
        ('numerario',    'Numerário'),
        ('transferencia','Transferência Bancária'),
        ('tpa',          'TPA'),
    ]

    partner      = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='licencas')
    plano        = models.ForeignKey(PartnerLicensePlan, on_delete=models.PROTECT)
    status       = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    data_inicio  = models.DateField(null=True, blank=True)
    data_expiracao = models.DateField(null=True, blank=True)
    metodo_pagamento = models.CharField(
        max_length=15, choices=METODO_PAGAMENTO_CHOICES, blank=True
    )
    valor_pago   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    registada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='licencas_parceiro_registadas'
    )
    token_activacao = models.OneToOneField(
        PartnerToken, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='licenca_activada'
    )
    observacoes  = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Licença de Parceiro'
        verbose_name_plural = 'Licenças de Parceiro'
        ordering = ['-data_inicio']

    def __str__(self):
        return f"{self.partner.nome} — {self.plano.nome} [{self.get_status_display()}]"

    @property
    def esta_activa(self):
        if self.status != 'activa':
            return False
        if self.data_expiracao and self.data_expiracao < timezone.now().date():
            return False
        return True

    # ── Quota ──────────────────────────────────────────────────────────────

    @property
    def quota_total_usada(self):
        return self.quota_usages.filter(operation='create').count()

    @property
    def quota_mes_usada(self):
        hoje = timezone.now()
        return self.quota_usages.filter(
            operation='create',
            created_at__year=hoje.year,
            created_at__month=hoje.month,
        ).count()

    @property
    def quota_total_disponivel(self):
        if self.plano.max_empresas_total == 0:
            return None   # ilimitado
        return max(0, self.plano.max_empresas_total - self.quota_total_usada)

    @property
    def quota_mes_disponivel(self):
        if self.plano.max_empresas_mes == 0:
            return None   # ilimitado
        return max(0, self.plano.max_empresas_mes - self.quota_mes_usada)

    def saldo(self) -> dict:
        """Devolve dict com estado completo da quota."""
        return {
            'total_limite':     self.plano.max_empresas_total,
            'total_usado':      self.quota_total_usada,
            'total_disponivel': self.quota_total_disponivel,
            'mes_limite':       self.plano.max_empresas_mes,
            'mes_usado':        self.quota_mes_usada,
            'mes_disponivel':   self.quota_mes_disponivel,
            'ilimitado_total':  self.plano.max_empresas_total == 0,
            'ilimitado_mes':    self.plano.max_empresas_mes == 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PartnerClient — relação Partner ↔ Empresa/tenant
# ─────────────────────────────────────────────────────────────────────────────

class PartnerClient(TimeStampedModel):
    """
    Liga um parceiro a uma empresa/tenant do VistoGest.
    A empresa continua a pertencer ao ecossistema SOTARQ — o parceiro
    é apenas o responsável comercial que a trouxe.

    Se o parceiro deixar de ser parceiro, a empresa NÃO é apagada.
    O histórico é preservado via parceiro_anterior.
    """
    STATUS_CHOICES = [
        ('activo',    'Activo'),
        ('suspenso',  'Suspenso'),
        ('expirado',  'Expirado'),
        ('cancelado', 'Cancelado'),
    ]

    partner  = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='clientes')
    # OneToOne: cada empresa só pode ter 1 parceiro activo
    empresa  = models.OneToOneField(
        'empresas.Empresa',
        on_delete=models.PROTECT,
        related_name='partner_client',
        help_text='Empresa/tenant associado a este parceiro.',
    )
    status   = models.CharField(max_length=15, choices=STATUS_CHOICES, default='activo')
    # Licença do cliente (da app licenca existente — NÃO duplicar)
    licenca_cliente = models.ForeignKey(
        'licenca.Licenca',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='partner_clients',
        help_text='Licença de uso do VistoGest pelo cliente (app licenca existente).',
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='partner_clients_criados'
    )
    # Histórico de transferências entre parceiros
    parceiro_anterior = models.ForeignKey(
        Partner, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='clientes_transferidos',
        help_text='Parceiro anterior (preenchido em transferências).',
    )
    data_transferencia  = models.DateTimeField(null=True, blank=True)
    motivo_transferencia = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Cliente de Parceiro'
        verbose_name_plural = 'Clientes de Parceiro'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.partner.nome} → {self.empresa.nome}"


# ─────────────────────────────────────────────────────────────────────────────
# PartnerQuotaUsage — histórico auditável de consumo de quota
# ─────────────────────────────────────────────────────────────────────────────

class PartnerQuotaUsage(TimeStampedModel):
    """
    Registo auditável de cada consumo de quota.
    Usado pelo PartnerService.verificar_quota() com select_for_update()
    para garantir consistência em caso de requests concorrentes.
    """
    OPERATION_CHOICES = [
        ('create',   'Criar cliente'),
        ('cancel',   'Cancelar cliente'),
        ('transfer', 'Transferir cliente'),
    ]

    partner_license = models.ForeignKey(
        PartnerLicense, on_delete=models.PROTECT, related_name='quota_usages'
    )
    partner_client  = models.ForeignKey(
        PartnerClient, on_delete=models.PROTECT, related_name='quota_entries'
    )
    operation  = models.CharField(max_length=15, choices=OPERATION_CHOICES)
    quantity   = models.IntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='quota_usages_criadas'
    )

    class Meta:
        verbose_name = 'Uso de Quota de Parceiro'
        verbose_name_plural = 'Usos de Quota de Parceiro'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.operation} | {self.partner_license.partner.nome} | {self.created_at}"


# ─────────────────────────────────────────────────────────────────────────────
# PartnerLicenseRequest — pedidos de plano superior / renovação / upgrade
# ─────────────────────────────────────────────────────────────────────────────

class PartnerLicenseRequest(TimeStampedModel):
    STATUS_CHOICES = [
        ('pendente',   'Pendente'),
        ('em_analise', 'Em Análise'),
        ('aprovado',   'Aprovado'),
        ('rejeitado',  'Rejeitado'),
        ('concluido',  'Concluído'),
        ('cancelado',  'Cancelado'),
    ]
    TIPO_CHOICES = [
        ('upgrade',    'Upgrade de Plano'),
        ('downgrade',  'Downgrade de Plano'),
        ('renovacao',  'Renovação'),
        ('outro',      'Outro'),
    ]

    partner          = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='solicitacoes')
    partner_client   = models.ForeignKey(
        PartnerClient, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='solicitacoes', help_text='Cliente relacionado com a solicitação (opcional).',
    )
    tipo             = models.CharField(max_length=15, choices=TIPO_CHOICES, default='upgrade')
    plano_atual      = models.ForeignKey(
        PartnerLicensePlan, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requests_origem',
    )
    plano_solicitado = models.ForeignKey(
        PartnerLicensePlan, on_delete=models.PROTECT, related_name='requests_destino',
    )
    motivo           = models.TextField(help_text='Motivo da solicitação.')
    status           = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    resposta         = models.TextField(blank=True)
    respondido_por   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requests_parceiro_respondidos',
    )
    respondido_em    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Licença de Parceiro'
        verbose_name_plural = 'Solicitações de Licença de Parceiro'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.partner.nome} — {self.get_tipo_display()} [{self.get_status_display()}]"


# ─────────────────────────────────────────────────────────────────────────────
# PartnerBilling — pagamentos do parceiro à SOTARQ
# ─────────────────────────────────────────────────────────────────────────────

class PartnerBilling(TimeStampedModel):
    """
    Registo de pagamentos feitos pelos parceiros à SOTARQ.
    SEPARADO dos pagamentos de clientes normais — nunca misturar.
    """
    STATUS_CHOICES = [
        ('pendente',   'Pendente'),
        ('pago',       'Pago'),
        ('cancelado',  'Cancelado'),
        ('estornado',  'Estornado'),
    ]
    METODO_CHOICES = [
        ('numerario',    'Numerário'),
        ('transferencia','Transferência Bancária'),
        ('tpa',          'TPA'),
    ]

    partner          = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='pagamentos')
    partner_license  = models.ForeignKey(
        PartnerLicense, on_delete=models.PROTECT, related_name='pagamentos',
    )
    valor            = models.DecimalField(max_digits=12, decimal_places=2)
    moeda            = models.CharField(max_length=3, default='AOA')
    metodo           = models.CharField(max_length=15, choices=METODO_CHOICES)
    status           = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    referencia       = models.CharField(max_length=100, blank=True)
    registado_por    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='billing_parceiro_registados',
    )
    data_pagamento   = models.DateTimeField(null=True, blank=True)
    observacoes      = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Pagamento de Parceiro'
        verbose_name_plural = 'Pagamentos de Parceiro'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.partner.nome} — {self.valor} {self.moeda} [{self.get_status_display()}]"


# ─────────────────────────────────────────────────────────────────────────────
# PartnerNotification — notificações internas do portal
# ─────────────────────────────────────────────────────────────────────────────

class PartnerNotification(TimeStampedModel):
    TIPO_CHOICES = [
        ('info',     'Informação'),
        ('aviso',    'Aviso'),
        ('alerta',   'Alerta'),
        ('aprovacao','Aprovação'),
        ('rejeicao', 'Rejeição'),
    ]

    partner  = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='notificacoes')
    tipo     = models.CharField(max_length=15, choices=TIPO_CHOICES, default='info')
    titulo   = models.CharField(max_length=200)
    mensagem = models.TextField()
    lida     = models.BooleanField(default=False)
    lida_em  = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Notificação de Parceiro'
        verbose_name_plural = 'Notificações de Parceiro'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.partner.nome} — {self.titulo}"

    def marcar_lida(self):
        if not self.lida:
            self.lida = True
            self.lida_em = timezone.now()
            self.save(update_fields=['lida', 'lida_em'])


# ─────────────────────────────────────────────────────────────────────────────
# PartnerAudit — trilha de auditoria completa
# ─────────────────────────────────────────────────────────────────────────────

class PartnerAudit(TimeStampedModel):
    """
    Registo imutável de todas as operações sensíveis do Portal de Parceiros.
    Exemplos de acções:
        PARTNER_CREATED, LICENSE_ACTIVATED, LICENSE_RENEWED, CLIENT_CREATED,
        CLIENT_TRANSFERRED, TOKEN_GENERATED, TOKEN_USED, REQUEST_APPROVED,
        BILLING_REGISTERED, BILLING_CONFIRMED.
    """

    partner       = models.ForeignKey(
        Partner, on_delete=models.CASCADE, related_name='auditorias',
    )
    acao          = models.CharField(max_length=100, help_text='Código da acção auditada.')
    objeto_tipo   = models.CharField(max_length=50, blank=True)
    objeto_id     = models.CharField(max_length=50, blank=True)
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_novo    = models.JSONField(null=True, blank=True)
    executado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='auditorias_parceiro',
    )
    ip_address    = models.GenericIPAddressField(null=True, blank=True)
    origem        = models.CharField(
        max_length=20, blank=True,
        help_text="'portal', 'admin', 'api' ou 'command'.",
    )

    class Meta:
        verbose_name = 'Auditoria de Parceiro'
        verbose_name_plural = 'Auditorias de Parceiro'
        ordering = ['-created_at']
        # Nunca permitir apagar auditorias
        default_permissions = ('add', 'view')

    def __str__(self):
        return f"{self.acao} | {self.partner.nome} | {self.created_at}"

    def delete(self, *args, **kwargs):
        raise Exception("Registos de auditoria são imutáveis e não podem ser apagados.")

# apps/vendas/migrations/0003_campos_certificacao_agt.py
"""
Migração de certificação AGT — adiciona os campos exigidos pelo
Decreto Executivo 683/25 (Anexo I) que estavam em falta:

  Venda:
    - motivo_cancelamento_codigo (documentCancelReason: I / N)

  FaturaCredito:
    - motivo_cancelamento_codigo

  NotaCredito:
    - motivo_cancelamento_codigo

  NotaDebito:
    - motivo_cancelamento_codigo

  ItemVenda:
    - operation_type  (operationType — obrigatório por linha)

  ItemFatura:
    - operation_type

  ItemNotaCredito:
    - operation_type
    - referencia_documento_origem  (referenceInfo.reference)
    - motivo_referencia            (referenceInfo.reason)
"""
from django.db import migrations, models


CANCEL_REASON_CHOICES = [
    ('I', 'I — Identificação incorrecta do adquirente'),
    ('N', 'N — Não enviado ao adquirente'),
]

OPERATION_TYPE_CHOICES = [
    ('SE',  'SE — Serviços em território nacional'),
    ('SS',  'SS — Serviços no estrangeiro'),
    ('STP', 'STP — Telecomunicações/via electrónica'),
    ('SR',  'SR — Serviços relacionados com imóveis'),
    ('SIF', 'SIF — Intermediação financeira'),
    ('SHS', 'SHS — Hotelaria e similares'),
    ('ST',  'ST — Transporte'),
    ('SG',  'SG — Serviços em geral'),
    ('TB',  'TB — Transmissão de bens'),
    ('AS',  'AS — Aquisição de serviços'),
    ('QT',  'QT — Outras operações tributáveis'),
    ('RD',  'RD — Regularizações e devoluções'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('vendas', '0002_fase2_documento_fiscal_onetone'),
    ]

    operations = [
        # ── Venda ────────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='motivo_cancelamento_codigo',
            field=models.CharField(
                max_length=1,
                choices=CANCEL_REASON_CHOICES,
                blank=True,
                default='',
                verbose_name='Código de Motivo de Anulação (documentCancelReason)',
            ),
            preserve_default=False,
        ),

        # ── FaturaCredito ─────────────────────────────────────────────────────
        migrations.AddField(
            model_name='faturacredito',
            name='motivo_cancelamento_codigo',
            field=models.CharField(
                max_length=1,
                choices=CANCEL_REASON_CHOICES,
                blank=True,
                default='',
                verbose_name='Código de Motivo de Anulação (documentCancelReason)',
            ),
            preserve_default=False,
        ),

        # ── NotaCredito ───────────────────────────────────────────────────────
        migrations.AddField(
            model_name='notacredito',
            name='motivo_cancelamento_codigo',
            field=models.CharField(
                max_length=1,
                choices=CANCEL_REASON_CHOICES,
                blank=True,
                default='',
                verbose_name='Código de Motivo de Anulação (documentCancelReason)',
            ),
            preserve_default=False,
        ),

        # ── NotaDebito ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='notadebito',
            name='motivo_cancelamento_codigo',
            field=models.CharField(
                max_length=1,
                choices=CANCEL_REASON_CHOICES,
                blank=True,
                default='',
                verbose_name='Código de Motivo de Anulação (documentCancelReason)',
            ),
            preserve_default=False,
        ),

        # ── ItemVenda ─────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='itemvenda',
            name='operation_type',
            field=models.CharField(
                max_length=3,
                choices=OPERATION_TYPE_CHOICES,
                default='TB',
                verbose_name='Tipo de Operação (operationType)',
            ),
        ),

        # ── ItemFatura ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='itemfatura',
            name='operation_type',
            field=models.CharField(
                max_length=3,
                choices=OPERATION_TYPE_CHOICES,
                default='TB',
                verbose_name='Tipo de Operação (operationType)',
            ),
        ),

        # ── ItemNotaCredito ───────────────────────────────────────────────────
        migrations.AddField(
            model_name='itemnotacredito',
            name='operation_type',
            field=models.CharField(
                max_length=3,
                choices=OPERATION_TYPE_CHOICES,
                default='RD',
                verbose_name='Tipo de Operação (operationType)',
            ),
        ),
        migrations.AddField(
            model_name='itemnotacredito',
            name='referencia_documento_origem',
            field=models.CharField(
                max_length=60,
                blank=True,
                default='',
                verbose_name='Referência do Documento de Origem',
                help_text='Número do documento (ex.: FT A/123) — referenceInfo.reference.',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='itemnotacredito',
            name='motivo_referencia',
            field=models.CharField(
                max_length=60,
                blank=True,
                default='',
                verbose_name='Motivo da Referência',
                help_text='Motivo opcional — referenceInfo.reason.',
            ),
            preserve_default=False,
        ),
    ]

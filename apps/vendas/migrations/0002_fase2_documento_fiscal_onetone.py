# apps/vendas/migrations/0002_fase2_documento_fiscal_onetone.py
"""
Migração manual — Fase 2 do PLANO_IMPLEMENTACAO.md:

1. Cria DocumentoTransporte (modelo que não estava em 0001_initial)
   já com o campo documento_fiscal incluído.

2. Adiciona documento_fiscal (OneToOneField → fiscal.DocumentoFiscal) aos
   6 modelos de vendas que geram documentos fiscais (Venda, FaturaCredito,
   Recibo, FaturaProforma, NotaCredito, NotaDebito).

Os campos hash_documento/atcud são mantidos como cache de leitura —
a geração passa a ser feita exclusivamente pelo DocumentoFiscalService
e os valores são copiados para cá a partir do DocumentoFiscal ligado.
"""
from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0001_initial'),
        ('fiscal', '0003_assinaturadigital_campos_v2'),
        ('funcionarios', '0001_initial'),
        ('vendas', '0001_initial'),
    ]

    operations = [
        # ── 1. Criar DocumentoTransporte (ausente do 0001) ───────────────────
        migrations.CreateModel(
            name='DocumentoTransporte',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),

                # ── Identificação ──────────────────────────────────────────
                ('numero_documento', models.CharField(
                    max_length=200, unique=True,
                    verbose_name='Nº Documento de Transporte',
                )),
                ('tipo_operacao', models.CharField(
                    max_length=20,
                    choices=[
                        ('venda', 'Venda de Mercadoria'),
                        ('transferencia', 'Transferência entre Lojas'),
                        ('consignacao', 'Consignação'),
                        ('demonstracao', 'Demonstração'),
                        ('devolucao', 'Devolução'),
                        ('garantia', 'Garantia'),
                        ('outros', 'Outros'),
                    ],
                    default='venda',
                )),
                ('tipo_transporte', models.CharField(
                    max_length=20,
                    choices=[
                        ('proprio', 'Transporte Próprio'),
                        ('terceirizado', 'Transporte Terceirizado'),
                        ('correios', 'Correios'),
                        ('transportadora', 'Transportadora'),
                        ('entrega_propria', 'Entrega Própria'),
                    ],
                    default='proprio',
                )),
                ('observacoes', models.TextField(blank=True, null=True)),

                # ── Valores ────────────────────────────────────────────────
                ('iva_valor', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    default=Decimal('0.00'),
                )),
                ('subtotal', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    default=Decimal('0.00'),
                )),
                ('desconto_valor', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    default=Decimal('0.00'),
                )),
                ('total', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    default=Decimal('0.00'),
                )),

                # ── Hashes / ATCUD (cache) ─────────────────────────────────
                ('hash_documento', models.CharField(
                    max_length=256, unique=True, null=True, blank=True,
                    help_text='Cache do hash gerado em DocumentoFiscal.',
                )),
                ('atcud', models.CharField(
                    max_length=100, null=True, blank=True,
                    help_text='Cache do ATCUD gerado em DocumentoFiscal.',
                )),

                # ── Documento Fiscal (AGT) ─────────────────────────────────
                ('documento_fiscal', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='documento_transporte',
                    to='fiscal.documentofiscal',
                    verbose_name='Documento Fiscal (AGT)',
                )),

                # ── Datas ──────────────────────────────────────────────────
                ('data_documento', models.DateTimeField(auto_now_add=True)),
                ('data_emissao', models.DateTimeField(auto_now_add=True)),
                ('data_inicio_transporte', models.DateTimeField(
                    verbose_name='Data/Hora de Início do Transporte',
                    null=True, blank=True,
                )),
                ('data_previsao_entrega', models.DateTimeField(
                    verbose_name='Previsão de Entrega',
                )),
                ('data_entrega_real', models.DateTimeField(
                    null=True, blank=True,
                )),

                # ── Status ─────────────────────────────────────────────────
                ('status', models.CharField(
                    max_length=20,
                    choices=[
                        ('preparando', 'Preparando Carga'),
                        ('em_transito', 'Em Trânsito'),
                        ('entregue', 'Entregue'),
                        ('devolvido', 'Devolvido'),
                        ('cancelado', 'Cancelado'),
                    ],
                    default='preparando',
                )),
                ('tem_fatura', models.BooleanField(default=False)),
                ('tem_recibo', models.BooleanField(default=False)),
                ('tem_nota_liquidacao', models.BooleanField(default=False)),
                ('tem_fatura_proforma', models.BooleanField(default=False)),

                # ── Remetente ──────────────────────────────────────────────
                ('remetente_nome', models.CharField(
                    max_length=200, verbose_name='Nome do Remetente', blank=True,
                )),
                ('remetente_nif', models.CharField(
                    max_length=20, verbose_name='NIF do Remetente', blank=True,
                )),
                ('remetente_endereco', models.CharField(
                    max_length=300, verbose_name='Endereço do Remetente', blank=True,
                )),
                ('remetente_telefone', models.CharField(
                    max_length=20, verbose_name='Telefone do Remetente', blank=True,
                )),
                ('remetente_provincia', models.CharField(
                    max_length=50, verbose_name='Província do Remetente', blank=True,
                )),

                # ── Destinatário (campos simples) ──────────────────────────
                ('destinatario_nome', models.CharField(
                    max_length=200, verbose_name='Nome do Destinatário',
                )),
                ('destinatario_nif', models.CharField(
                    max_length=20, blank=True,
                    verbose_name='NIF/BI do Destinatário',
                )),
                ('destinatario_endereco', models.CharField(
                    max_length=300, verbose_name='Endereço de Entrega',
                )),
                ('destinatario_telefone', models.CharField(
                    max_length=20, blank=True,
                    verbose_name='Telefone do Destinatário',
                )),
                ('destinatario_provincia', models.CharField(
                    max_length=50, blank=True,
                    verbose_name='Província do Destinatário',
                )),

                # ── Transportador ──────────────────────────────────────────
                ('transportador_nome', models.CharField(
                    max_length=200, blank=True,
                    verbose_name='Nome do Transportador',
                )),
                ('transportador_nif', models.CharField(
                    max_length=20, blank=True,
                    verbose_name='NIF do Transportador',
                )),
                ('transportador_telefone', models.CharField(
                    max_length=20, blank=True,
                    verbose_name='Telefone do Transportador',
                )),

                # ── Veículo / Condutor ─────────────────────────────────────
                ('veiculo_matricula', models.CharField(
                    max_length=20, verbose_name='Matrícula do Veículo',
                )),
                ('veiculo_modelo', models.CharField(
                    max_length=100, blank=True,
                    verbose_name='Modelo do Veículo',
                )),
                ('condutor_nome', models.CharField(
                    max_length=200, blank=True,
                    verbose_name='Nome do Condutor',
                )),
                ('condutor_carta', models.CharField(
                    max_length=20, blank=True,
                    verbose_name='Número da Carta de Condução',
                )),
            ],
            options={
                'verbose_name': 'Documento de Transporte',
                'verbose_name_plural': 'Documentos de Transporte',
                'ordering': ['-data_documento'],
            },
        ),

        # ── 2. FKs do DocumentoTransporte (adicionadas separadamente por
        #       dependência circular — cliente/vendedor/forma_pagamento/
        #       venda_origem/fatura_credito_origem/destinatario_cliente) ───────
        migrations.AddField(
            model_name='documentotransporte',
            name='cliente',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='documentos_transporte',
                to='clientes.cliente',
            ),
        ),
        migrations.AddField(
            model_name='documentotransporte',
            name='vendedor',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='documentos_transporte',
                to='funcionarios.funcionario',
            ),
        ),
        migrations.AddField(
            model_name='documentotransporte',
            name='forma_pagamento',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='vendas.formapagamento',
            ),
        ),
        migrations.AddField(
            model_name='documentotransporte',
            name='venda_origem',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='documentos_transporte',
                to='vendas.venda',
                verbose_name='Venda de Origem',
            ),
        ),
        migrations.AddField(
            model_name='documentotransporte',
            name='fatura_credito_origem',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='documentos_transporte',
                to='vendas.faturacredito',
                verbose_name='Fatura Crédito de Origem',
            ),
        ),
        migrations.AddField(
            model_name='documentotransporte',
            name='destinatario_cliente',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='documentos_transporte_destinatario',
                to='clientes.cliente',
            ),
        ),

        # ── 3. documento_fiscal nos outros modelos de venda ──────────────────
        migrations.AddField(
            model_name='venda',
            name='documento_fiscal',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='venda',
                to='fiscal.documentofiscal',
                verbose_name='Documento Fiscal (AGT)',
            ),
        ),
        migrations.AddField(
            model_name='faturacredito',
            name='documento_fiscal',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='fatura_credito',
                to='fiscal.documentofiscal',
                verbose_name='Documento Fiscal (AGT)',
            ),
        ),
        migrations.AddField(
            model_name='recibo',
            name='documento_fiscal',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='recibo',
                to='fiscal.documentofiscal',
                verbose_name='Documento Fiscal (AGT)',
            ),
        ),
        migrations.AddField(
            model_name='faturaproforma',
            name='documento_fiscal',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='fatura_proforma',
                to='fiscal.documentofiscal',
                verbose_name='Documento Fiscal (AGT)',
            ),
        ),
        migrations.AddField(
            model_name='notacredito',
            name='documento_fiscal',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='nota_credito',
                to='fiscal.documentofiscal',
                verbose_name='Documento Fiscal (AGT)',
            ),
        ),
        migrations.AddField(
            model_name='notadebito',
            name='documento_fiscal',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='nota_debito',
                to='fiscal.documentofiscal',
                verbose_name='Documento Fiscal (AGT)',
            ),
        ),
    ]

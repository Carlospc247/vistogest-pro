# apps/vendas/migrations/0004_faturagenerica_faturaautofacturacao_proxy.py
"""
Cria os modelos proxy FaturaGenerica (GF) e FaturaAutofacturacao (AF),
necessários para os pontos 12 e 13 da Notificação AGT de homologação.

Proxies não criam tabela nova — usam a tabela de FaturaCredito com
tipo_documento='GF' ou 'AF'.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('vendas', '0003_campos_certificacao_agt'),
    ]

    operations = [
        migrations.CreateModel(
            name='FaturaGenerica',
            fields=[],
            options={
                'proxy': True,
                'verbose_name': 'Factura Genérica (GF)',
                'verbose_name_plural': 'Facturas Genéricas (GF)',
                'indexes': [],
                'constraints': [],
            },
            bases=('vendas.faturacredito',),
        ),
        migrations.CreateModel(
            name='FaturaAutofacturacao',
            fields=[],
            options={
                'proxy': True,
                'verbose_name': 'Factura de Autofacturação (AF)',
                'verbose_name_plural': 'Facturas de Autofacturação (AF)',
                'indexes': [],
                'constraints': [],
            },
            bases=('vendas.faturacredito',),
        ),
    ]

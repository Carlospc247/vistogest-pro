# apps/fiscal/migrations/0004_documentofiscal_eac_code.py
"""
Migração de certificação AGT:

  DocumentoFiscal:
    - eac_code  (EACCode — Código de Actividade Económica, 5 dígitos)
      Obrigatório no payload /registarFactura (Decreto 683/25, Anexo I).

Nota: a expansão de TIPO_DOCUMENTO_CHOICES (de 10 para 20 valores) e a
correcção de TAX_CODE_CHOICES (NSU → NS) em TaxaIVAAGT são alterações
de opções (choices) apenas — não alteram a coluna no banco de dados,
portanto não precisam de operação DDL separada.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fiscal', '0003_assinaturadigital_campos_v2'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentofiscal',
            name='eac_code',
            field=models.CharField(
                max_length=5,
                blank=True,
                default='',
                verbose_name='Código CAE (EACCode)',
                help_text=(
                    'Código de Actividade Económica (5 dígitos, Tabela CAE). '
                    'Obrigatório no payload registarFactura (Decreto 683/25, Anexo I).'
                ),
            ),
            preserve_default=False,
        ),
    ]

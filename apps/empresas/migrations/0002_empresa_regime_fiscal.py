# apps/empresas/migrations/0002_empresa_regime_fiscal.py
"""
Adiciona o campo regime_fiscal à Empresa.

Contexto:
    O campo 'regime' já existente refere-se ao TIPO DE ACTIVIDADE
    (Comércio / Serviços / Misto) — não é o regime fiscal.

    O novo campo 'regime_fiscal' é o regime tributário AGT:
    Regime Geral, Simplificado, Exclusão ou Especial.
    É este que aparece nos documentos fiscais, PDFs e no SAF-T.

    Também corrige o verbose_name do campo 'regime' de
    "Regime Fiscal" para "Tipo de Actividade" para evitar confusão.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('empresas', '0001_initial'),
    ]

    operations = [
        # 1. Corrigir o verbose_name do campo existente 'regime' (alteração semântica)
        #    Esta operação não altera a coluna na BD — apenas o metadata do Django.
        migrations.AlterField(
            model_name='empresa',
            name='regime',
            field=models.CharField(
                verbose_name='Tipo de Actividade',
                max_length=20,
                choices=[
                    ('COMERCIO', 'Comércio (só produtos)'),
                    ('SERVICOS', 'Prestação de Serviços (só serviços)'),
                    ('MISTO',    'Misto (Comércio + Serviços)'),
                ],
                default='MISTO',
                help_text=(
                    'Define o tipo de actividade da empresa: Comércio, Serviços ou Misto. '
                    'Usado para controlar o que pode ser vendido. '
                    'NÃO é o regime fiscal AGT.'
                ),
            ),
        ),

        # 2. Adicionar o novo campo 'regime_fiscal' — regime tributário AGT
        migrations.AddField(
            model_name='empresa',
            name='regime_fiscal',
            field=models.CharField(
                verbose_name='Regime Fiscal (AGT)',
                max_length=20,
                choices=[
                    ('GERAL',        'Regime Geral'),
                    ('SIMPLIFICADO', 'Regime Simplificado'),
                    ('EXCLUSAO',     'Regime de Exclusão'),
                    ('ESPECIAL',     'Regime Especial'),
                ],
                default='GERAL',
                help_text=(
                    'Regime tributário AGT: Regime Geral, Simplificado, Exclusão ou Especial. '
                    'Aparece nos documentos fiscais, PDFs e no SAF-T. '
                    'Este é o regime fiscal — diferente do Tipo de Actividade acima.'
                ),
            ),
        ),
    ]

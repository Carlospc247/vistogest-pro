# apps/funcionarios/migrations/0003_cargo_permissoes_parceiros.py
"""
Adiciona campos de permissão para gestão de parceiros ao modelo Cargo.
Estes campos são para funcionários da SOTARQ que gerem o Portal de Parceiros.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('funcionarios', '0002_alter_funcionario_usuario'),
    ]

    operations = [
        migrations.AddField(
            model_name='cargo',
            name='pode_gerir_parceiros',
            field=models.BooleanField(
                default=False,
                verbose_name='Pode gerir parceiros',
                help_text='Pode cadastrar parceiros, criar licenças e gerar tokens.',
            ),
        ),
        migrations.AddField(
            model_name='cargo',
            name='pode_ver_parceiros',
            field=models.BooleanField(
                default=False,
                verbose_name='Pode ver parceiros',
            ),
        ),
        migrations.AddField(
            model_name='cargo',
            name='pode_aprovar_solicitacoes_parceiros',
            field=models.BooleanField(
                default=False,
                verbose_name='Pode aprovar solicitações de parceiros',
            ),
        ),
        migrations.AddField(
            model_name='cargo',
            name='pode_ver_faturamento_parceiros',
            field=models.BooleanField(
                default=False,
                verbose_name='Pode ver faturamento de parceiros',
            ),
        ),
    ]

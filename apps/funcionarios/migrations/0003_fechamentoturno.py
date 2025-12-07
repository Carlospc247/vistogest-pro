from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):

    dependencies = [
        ('funcionarios', '0002_auto_20251206_1234'),  # <--- colocar a última migração real
    ]

    operations = [
        migrations.CreateModel(
            name='FechamentoTurno',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('data_fechamento', models.DateTimeField(default=django.utils.timezone.now)),
                ('valor_informado_caixa', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('valor_informado_tpa', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('valor_informado_transferencia', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('valor_sistema_caixa', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('valor_sistema_tpa', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('valor_sistema_transferencia', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('observacoes', models.TextField(blank=True)),
                ('funcionario', models.ForeignKey(on_delete=models.CASCADE, to='funcionarios.funcionario', related_name='fechamentos_turno')),
            ],
        ),
    ]

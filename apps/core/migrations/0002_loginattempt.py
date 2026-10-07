# apps/core/migrations/0002_loginattempt.py
"""
Adiciona o modelo LoginAttempt para registo persistente de tentativas
de login falhadas (brute-force protection).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginAttempt',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('username_tentado', models.CharField(
                    blank=True, db_index=True, max_length=150,
                    verbose_name='Username tentado',
                )),
                ('ip_address', models.GenericIPAddressField(
                    db_index=True, verbose_name='Endereço IP',
                )),
                ('user_agent', models.TextField(
                    blank=True, verbose_name='User-Agent',
                )),
                ('timestamp', models.DateTimeField(
                    auto_now_add=True, db_index=True,
                )),
                ('bloqueado', models.BooleanField(
                    default=False,
                    verbose_name='Tentativa em modo bloqueado',
                )),
                ('schema_name', models.CharField(
                    blank=True, max_length=63,
                    verbose_name='Schema (Tenant)',
                )),
            ],
            options={
                'verbose_name': 'Tentativa de Login Falhada',
                'verbose_name_plural': 'Tentativas de Login Falhadas',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='loginattempt',
            index=models.Index(
                fields=['ip_address', 'timestamp'],
                name='loginattempt_ip_ts_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='loginattempt',
            index=models.Index(
                fields=['username_tentado', 'timestamp'],
                name='loginattempt_user_ts_idx',
            ),
        ),
    ]

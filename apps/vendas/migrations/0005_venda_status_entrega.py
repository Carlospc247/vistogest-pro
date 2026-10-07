# apps/vendas/migrations/0005_venda_status_entrega.py
"""
Adiciona campos ao modelo Venda que existiam em models.py
mas não tinham migração correspondente:

  - status_entrega         (CharField)
  - data_cancelamento      (DateTimeField)
  - motivo_cancelamento    (TextField)
  - usuario_cancelamento   (FK → AUTH_USER_MODEL)
  - usuario_criacao        (FK → AUTH_USER_MODEL)
  - usuario_modificacao    (FK → AUTH_USER_MODEL)
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('vendas', '0004_faturaGenerica_faturaAutofacturacao_proxy'),
    ]

    operations = [
        # ── status_entrega ────────────────────────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='status_entrega',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('nao_aplicavel', 'Não Aplicável'),
                    ('agendada', 'Agendada'),
                    ('em_rota', 'Em Rota'),
                    ('entregue', 'Entregue'),
                ],
                default='nao_aplicavel',
            ),
        ),

        # ── data_cancelamento ─────────────────────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='data_cancelamento',
            field=models.DateTimeField(null=True, blank=True),
        ),

        # ── motivo_cancelamento (texto livre) ─────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='motivo_cancelamento',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),

        # ── usuario_cancelamento ──────────────────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='usuario_cancelamento',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vendas_canceladas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # ── usuario_criacao ───────────────────────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='usuario_criacao',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vendas_criadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # ── usuario_modificacao ───────────────────────────────────────────────
        migrations.AddField(
            model_name='venda',
            name='usuario_modificacao',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vendas_modificadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

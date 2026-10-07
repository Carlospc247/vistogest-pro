# apps/fiscal/migrations/0006_documentofiscal_imutabilidade.py
"""
Secção 3 do PLANO_IMPLEMENTACAO.md — Imutabilidade dos documentos fiscais.

Adiciona ao modelo DocumentoFiscal:
  - comentarios          : campo operacional (não fiscal, pode editar após emissão)
  - motivo_cancelamento_codigo : motivo de anulação para API AGT (I/N)
  - documento_original   : auto-FK para rastrear cadeia documento → rectificativo
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fiscal', '0005_seriefiscalagt'),
    ]

    operations = [
        # Campo operacional — não fiscal; pode ser editado após emissão
        migrations.AddField(
            model_name='documentofiscal',
            name='comentarios',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Comentários / Observações',
                help_text=(
                    'Campo operacional — não fiscal. '
                    'Pode ser editado após emissão. '
                    'NÃO é incluído no hash do documento.'
                ),
            ),
            preserve_default=False,
        ),

        # Motivo de cancelamento — obrigatório quando documentStatus = A (anulado)
        migrations.AddField(
            model_name='documentofiscal',
            name='motivo_cancelamento_codigo',
            field=models.CharField(
                max_length=1,
                choices=[
                    ('I', 'I — Identificação incorrecta do adquirente'),
                    ('N', 'N — Não enviado ao adquirente'),
                ],
                blank=True,
                default='',
                verbose_name='Motivo de Cancelamento (documentCancelReason)',
                help_text=(
                    "Obrigatório quando documentStatus='A'. "
                    "Decreto 683/25, Anexo I."
                ),
            ),
            preserve_default=False,
        ),

        # Auto-FK para rastrear cadeia documento original → correctivo (NC/ND/RE)
        migrations.AddField(
            model_name='documentofiscal',
            name='documento_original',
            field=models.ForeignKey(
                to='fiscal.documentofiscal',
                on_delete=django.db.models.deletion.PROTECT,
                null=True,
                blank=True,
                related_name='documentos_correctivos',
                verbose_name='Documento Original',
                help_text=(
                    'Referência ao documento original que originou este rectificativo. '
                    'Preenchido em NC, ND e RE que derivem de outro documento.'
                ),
            ),
        ),
    ]

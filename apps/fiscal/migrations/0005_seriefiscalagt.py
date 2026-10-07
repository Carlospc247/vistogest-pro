# apps/fiscal/migrations/0005_seriefiscalagt.py
"""
Cria o modelo SerieFiscalAGT — espelho local das séries de numeração
registadas junto da AGT via solicitarSerie / listarSeries.
"""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('fiscal', '0004_documentofiscal_eac_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='SerieFiscalAGT',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('series_code', models.CharField(
                    max_length=60,
                    verbose_name='Código da Série',
                    help_text='Código alfanumérico único, contendo o ano. Ex.: FT2025A.',
                )),
                ('series_year', models.IntegerField(verbose_name='Ano da Série')),
                ('document_type', models.CharField(
                    max_length=3,
                    verbose_name='Tipo de Documento',
                )),
                ('series_status', models.CharField(
                    max_length=1,
                    choices=[('A', 'A — Aberta'), ('U', 'U — Em utilização'), ('F', 'F — Fechada')],
                    default='A',
                    verbose_name='Estado da Série',
                )),
                ('invoicing_method', models.CharField(
                    max_length=4,
                    choices=[
                        ('FEPC', 'FEPC — Portal do Contribuinte'),
                        ('FESF', 'FESF — Software de Facturação'),
                        ('SF',   'SF — Software (não electrónico)'),
                    ],
                    default='FESF',
                    verbose_name='Método de Facturação',
                )),
                ('contingency_indicator', models.CharField(
                    max_length=1,
                    choices=[('N', 'N — Normal'), ('C', 'C — Contingência')],
                    default='N',
                    verbose_name='Indicador de Contingência',
                )),
                ('first_document_no', models.CharField(
                    max_length=60, blank=True,
                    verbose_name='Primeiro Número Autorizado',
                )),
                ('last_document_no', models.CharField(
                    max_length=60, blank=True,
                    verbose_name='Último Número Autorizado',
                )),
                ('authorized_quantity', models.CharField(
                    max_length=30, blank=True,
                    verbose_name='Quantidade Autorizada pela AGT',
                )),
                ('first_document_created', models.CharField(
                    max_length=60, blank=True,
                    verbose_name='Primeiro Documento Criado',
                )),
                ('last_document_created', models.CharField(
                    max_length=60, blank=True,
                    verbose_name='Último Documento Criado',
                )),
                ('series_creation_date', models.DateField(
                    null=True, blank=True,
                    verbose_name='Data de Criação (AGT)',
                )),
                ('establishment_number', models.CharField(
                    max_length=200, default='SEDE',
                    verbose_name='Estabelecimento',
                )),
                ('contador', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='serie_agt',
                    to='fiscal.contadordocumento',
                    verbose_name='Contador Local',
                )),
            ],
            options={
                'verbose_name': 'Série Fiscal AGT',
                'verbose_name_plural': 'Séries Fiscais AGT',
                'ordering': ['-series_year', 'document_type', 'series_code'],
            },
        ),
        migrations.AddConstraint(
            model_name='seriefiscalagt',
            constraint=models.UniqueConstraint(
                fields=['series_code', 'series_year', 'document_type'],
                name='unique_serie_agt_code_year_type',
            ),
        ),
    ]

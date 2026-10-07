# apps/fiscal/migrations/0003_assinaturadigital_campos_v2.py
"""
Alinha o modelo AssinaturaDigital com o serviço de assinatura.

HISTÓRICO DO PROBLEMA (KeyError: 'chave_privada_contribuinte'):
  A versão anterior desta migração tentava fazer RemoveField de
  'chave_privada_contribuinte' e 'chave_publica_contribuinte', mas
  a migração 0001_initial criou o modelo com os campos 'chave_privada'
  e 'chave_publica' (nomes originais). Os nomes intermédios
  'chave_privada_contribuinte' nunca existiram na cadeia de migrações,
  causando KeyError ao construir o estado virtual.

SOLUÇÃO:
  1. Adicionar os novos campos corretos (nif_contribuinte,
     chave_contribuinte_privada, chave_contribuinte_publica,
     data_configuracao_chave, configurada_por, api_username, api_password).
  2. Copiar dados de 'chave_privada' → 'chave_contribuinte_privada'
     e 'chave_publica' → 'chave_contribuinte_publica' via RunSQL.
  3. Remover apenas os campos que REALMENTE existem no estado virtual:
     'chave_privada' e 'chave_publica' (nomes do 0001_initial).
  4. Usar SeparateDatabaseAndState para 'data_configuracao' e
     'configurado_por' — que podem ou não existir fisicamente
     dependendo de dados inseridos via shell, mas não estão no
     estado virtual das migrações.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fiscal', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── PASSO 1: Adicionar novos campos ──────────────────────────────────

        migrations.AddField(
            model_name='assinaturadigital',
            name='nif_contribuinte',
            field=models.CharField(
                blank=True, max_length=20,
                verbose_name='NIF do Contribuinte',
                help_text='NIF da empresa (tenant) tal como consta na chave emitida pela AGT.',
                default='',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='assinaturadigital',
            name='chave_contribuinte_privada',
            field=models.TextField(
                blank=True, null=True,
                help_text='Chave privada RSA do CONTRIBUINTE (emitida pela AGT), cifrada via AESService.',
            ),
        ),
        migrations.AddField(
            model_name='assinaturadigital',
            name='chave_contribuinte_publica',
            field=models.TextField(
                blank=True, null=True,
                help_text='Chave pública RSA do CONTRIBUINTE (emitida pela AGT), em PEM.',
            ),
        ),
        migrations.AddField(
            model_name='assinaturadigital',
            name='data_configuracao_chave',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Data de Configuração das Chaves',
            ),
        ),
        migrations.AddField(
            model_name='assinaturadigital',
            name='configurada_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assinaturas_fiscais_configuradas_v2',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Configurado por',
            ),
        ),
        migrations.AddField(
            model_name='assinaturadigital',
            name='api_username',
            field=models.CharField(
                blank=True, max_length=100,
                verbose_name='Username API AGT',
                help_text='Utilizador da Basic Auth emitido pela AGT.',
                default='',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='assinaturadigital',
            name='api_password',
            field=models.TextField(
                blank=True,
                verbose_name='Password API AGT (cifrada)',
                help_text='Password da Basic Auth cifrada via AESService.',
                default='',
            ),
            preserve_default=False,
        ),

        # ── PASSO 2: Copiar dados dos campos antigos para os novos ───────────
        # Os campos 'chave_privada' e 'chave_publica' existem desde o 0001_initial.
        # Copiamos o conteúdo para os novos campos antes de remover os antigos.

        migrations.RunSQL(
            sql="""
                UPDATE fiscal_assinaturadigital
                SET
                    chave_contribuinte_privada = chave_privada,
                    chave_contribuinte_publica = chave_publica
                WHERE chave_privada IS NOT NULL
                   OR chave_publica IS NOT NULL;
            """,
            reverse_sql="""
                UPDATE fiscal_assinaturadigital
                SET
                    chave_privada = chave_contribuinte_privada,
                    chave_publica = chave_contribuinte_publica
                WHERE chave_contribuinte_privada IS NOT NULL
                   OR chave_contribuinte_publica IS NOT NULL;
            """,
        ),

        # ── PASSO 3: Remover apenas os campos que EXISTEM no estado virtual ──
        # 'chave_privada' e 'chave_publica' foram criados no 0001_initial.
        # São os únicos que podemos remover com RemoveField.

        migrations.RemoveField(
            model_name='assinaturadigital',
            name='chave_privada',
        ),
        migrations.RemoveField(
            model_name='assinaturadigital',
            name='chave_publica',
        ),

        # ── PASSO 4: Campos 'data_configuracao' e 'configurado_por' ─────────
        # Estes campos não existem no estado virtual das migrações anteriores
        # (0001 e 0002 não os definem), mas podem existir fisicamente na BD
        # de instalações antigas que usaram o shell.
        # Usamos SeparateDatabaseAndState:
        #   - state_operations=[] : não altera o estado virtual (seguro)
        #   - database_operations: tenta a operação na BD; se falhar, ignora
        # Em instalações novas (sem esses campos) a SQL é simplesmente ignorada.

        migrations.SeparateDatabaseAndState(
            state_operations=[],    # nenhuma alteração ao estado virtual
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE fiscal_assinaturadigital DROP COLUMN IF EXISTS data_configuracao;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE fiscal_assinaturadigital DROP COLUMN IF EXISTS configurado_por_id;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]

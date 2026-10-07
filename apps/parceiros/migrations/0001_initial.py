# apps/parceiros/migrations/0001_initial.py
"""Migração inicial da app parceiros — cria todos os 10 modelos."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('empresas', '0002_empresa_regime_fiscal'),
        ('licenca',  '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── PartnerLicensePlan ────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerLicensePlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('nome',        models.CharField(max_length=100)),
                ('descricao',   models.TextField(blank=True)),
                ('preco',       models.DecimalField(max_digits=12, decimal_places=2)),
                ('moeda',       models.CharField(max_length=3, default='AOA')),
                ('duracao',     models.IntegerField(default=1)),
                ('unidade_duracao', models.CharField(max_length=6, choices=[('dias','Dias'),('meses','Meses'),('anos','Anos')], default='meses')),
                ('renovacao_automatica', models.BooleanField(default=False)),
                ('permite_renovacao',   models.BooleanField(default=True)),
                ('permite_upgrade',     models.BooleanField(default=True)),
                ('permite_downgrade',   models.BooleanField(default=False)),
                ('max_empresas_total',  models.IntegerField(default=0)),
                ('max_empresas_mes',    models.IntegerField(default=0)),
                ('ativo', models.BooleanField(default=True)),
                ('planos_cliente_autorizados', models.ManyToManyField(
                    to='licenca.PlanoLicenca', blank=True,
                    related_name='planos_parceiro_autorizados',
                )),
            ],
            options={'verbose_name': 'Plano de Licença de Parceiro', 'verbose_name_plural': 'Planos de Licença de Parceiro', 'ordering': ['preco']},
        ),

        # ── Partner ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('nome',     models.CharField(max_length=200)),
                ('tipo',     models.CharField(max_length=20, choices=[('pessoa_singular','Pessoa Singular'),('empresa','Empresa')], default='empresa')),
                ('nif',      models.CharField(max_length=20, blank=True)),
                ('telefone', models.CharField(max_length=20, blank=True)),
                ('email',    models.EmailField()),
                ('endereco', models.TextField(blank=True)),
                ('status',   models.CharField(max_length=15, choices=[('activo','Activo'),('suspenso','Suspenso'),('inactivo','Inactivo'),('cancelado','Cancelado')], default='activo')),
                ('observacoes', models.TextField(blank=True)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='partner_profile', to=settings.AUTH_USER_MODEL)),
                ('registado_por', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='parceiros_registados', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Parceiro', 'verbose_name_plural': 'Parceiros', 'ordering': ['nome']},
        ),

        # ── PartnerToken ──────────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tipo',       models.CharField(max_length=15, choices=[('activacao','Activação'),('renovacao','Renovação'),('upgrade','Upgrade')])),
                ('status',     models.CharField(max_length=15, choices=[('disponivel','Disponível'),('utilizado','Utilizado'),('expirado','Expirado'),('cancelado','Cancelado')], default='disponivel')),
                ('token_hash', models.CharField(max_length=256, unique=True)),
                ('utilizado_em', models.DateTimeField(null=True, blank=True)),
                ('expira_em',    models.DateTimeField(null=True, blank=True)),
                ('partner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tokens', to='parceiros.partner')),
                ('criado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tokens_parceiro_criados', to=settings.AUTH_USER_MODEL)),
                ('plano_destino', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='tokens_destino', to='parceiros.partnerlicenseplan')),
            ],
            options={'verbose_name': 'Token de Parceiro', 'verbose_name_plural': 'Tokens de Parceiro'},
        ),

        # ── PartnerLicense ────────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerLicense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status',     models.CharField(max_length=15, choices=[('pendente','Pendente Activação'),('activa','Activa'),('expirada','Expirada'),('suspensa','Suspensa'),('cancelada','Cancelada')], default='pendente')),
                ('data_inicio',     models.DateField(null=True, blank=True)),
                ('data_expiracao',  models.DateField(null=True, blank=True)),
                ('metodo_pagamento', models.CharField(max_length=15, choices=[('numerario','Numerário'),('transferencia','Transferência Bancária'),('tpa','TPA')], blank=True)),
                ('valor_pago',   models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)),
                ('observacoes',  models.TextField(blank=True)),
                ('partner',  models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='licencas', to='parceiros.partner')),
                ('plano',    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='parceiros.partnerlicenseplan')),
                ('registada_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='licencas_parceiro_registadas', to=settings.AUTH_USER_MODEL)),
                ('token_activacao', models.OneToOneField(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='licenca_activada', to='parceiros.partnertoken')),
            ],
            options={'verbose_name': 'Licença de Parceiro', 'verbose_name_plural': 'Licenças de Parceiro', 'ordering': ['-data_inicio']},
        ),

        # ── PartnerClient ─────────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status',     models.CharField(max_length=15, choices=[('activo','Activo'),('suspenso','Suspenso'),('expirado','Expirado'),('cancelado','Cancelado')], default='activo')),
                ('data_transferencia',    models.DateTimeField(null=True, blank=True)),
                ('motivo_transferencia',  models.TextField(blank=True)),
                ('partner',   models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='clientes', to='parceiros.partner')),
                ('empresa',   models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='partner_client', to='empresas.empresa')),
                ('licenca_cliente', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='partner_clients', to='licenca.licenca')),
                ('criado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='partner_clients_criados', to=settings.AUTH_USER_MODEL)),
                ('parceiro_anterior', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clientes_transferidos', to='parceiros.partner')),
            ],
            options={'verbose_name': 'Cliente de Parceiro', 'verbose_name_plural': 'Clientes de Parceiro', 'ordering': ['-created_at']},
        ),

        # ── PartnerQuotaUsage ─────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerQuotaUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('operation', models.CharField(max_length=15, choices=[('create','Criar cliente'),('cancel','Cancelar cliente'),('transfer','Transferir cliente')])),
                ('quantity',  models.IntegerField(default=1)),
                ('partner_license', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='quota_usages', to='parceiros.partnerlicense')),
                ('partner_client',  models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='quota_entries', to='parceiros.partnerclient')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quota_usages_criadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Uso de Quota de Parceiro', 'verbose_name_plural': 'Usos de Quota de Parceiro', 'ordering': ['-created_at']},
        ),

        # ── PartnerLicenseRequest ─────────────────────────────────────
        migrations.CreateModel(
            name='PartnerLicenseRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tipo',    models.CharField(max_length=15, choices=[('upgrade','Upgrade de Plano'),('downgrade','Downgrade de Plano'),('renovacao','Renovação'),('outro','Outro')], default='upgrade')),
                ('motivo',  models.TextField()),
                ('status',  models.CharField(max_length=15, choices=[('pendente','Pendente'),('em_analise','Em Análise'),('aprovado','Aprovado'),('rejeitado','Rejeitado'),('concluido','Concluído'),('cancelado','Cancelado')], default='pendente')),
                ('resposta', models.TextField(blank=True)),
                ('respondido_em', models.DateTimeField(null=True, blank=True)),
                ('partner',           models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='solicitacoes', to='parceiros.partner')),
                ('partner_client',    models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitacoes', to='parceiros.partnerclient')),
                ('plano_atual',       models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requests_origem', to='parceiros.partnerlicenseplan')),
                ('plano_solicitado',  models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requests_destino', to='parceiros.partnerlicenseplan')),
                ('respondido_por',    models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requests_parceiro_respondidos', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Solicitação de Licença de Parceiro', 'verbose_name_plural': 'Solicitações de Licença de Parceiro', 'ordering': ['-created_at']},
        ),

        # ── PartnerBilling ────────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerBilling',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('valor',    models.DecimalField(max_digits=12, decimal_places=2)),
                ('moeda',    models.CharField(max_length=3, default='AOA')),
                ('metodo',   models.CharField(max_length=15, choices=[('numerario','Numerário'),('transferencia','Transferência Bancária'),('tpa','TPA')])),
                ('status',   models.CharField(max_length=15, choices=[('pendente','Pendente'),('pago','Pago'),('cancelado','Cancelado'),('estornado','Estornado')], default='pendente')),
                ('referencia', models.CharField(max_length=100, blank=True)),
                ('data_pagamento', models.DateTimeField(null=True, blank=True)),
                ('observacoes',   models.TextField(blank=True)),
                ('partner',          models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagamentos', to='parceiros.partner')),
                ('partner_license',  models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagamentos', to='parceiros.partnerlicense')),
                ('registado_por',    models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='billing_parceiro_registados', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Pagamento de Parceiro', 'verbose_name_plural': 'Pagamentos de Parceiro', 'ordering': ['-created_at']},
        ),

        # ── PartnerNotification ───────────────────────────────────────
        migrations.CreateModel(
            name='PartnerNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tipo',     models.CharField(max_length=15, choices=[('info','Informação'),('aviso','Aviso'),('alerta','Alerta'),('aprovacao','Aprovação'),('rejeicao','Rejeição')], default='info')),
                ('titulo',   models.CharField(max_length=200)),
                ('mensagem', models.TextField()),
                ('lida',     models.BooleanField(default=False)),
                ('lida_em',  models.DateTimeField(null=True, blank=True)),
                ('partner',  models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notificacoes', to='parceiros.partner')),
            ],
            options={'verbose_name': 'Notificação de Parceiro', 'verbose_name_plural': 'Notificações de Parceiro', 'ordering': ['-created_at']},
        ),

        # ── PartnerAudit ──────────────────────────────────────────────
        migrations.CreateModel(
            name='PartnerAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('acao',        models.CharField(max_length=100)),
                ('objeto_tipo', models.CharField(max_length=50, blank=True)),
                ('objeto_id',   models.CharField(max_length=50, blank=True)),
                ('valor_anterior', models.JSONField(null=True, blank=True)),
                ('valor_novo',     models.JSONField(null=True, blank=True)),
                ('ip_address', models.GenericIPAddressField(null=True, blank=True)),
                ('origem',     models.CharField(max_length=20, blank=True)),
                ('partner',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='auditorias', to='parceiros.partner')),
                ('executado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='auditorias_parceiro', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Auditoria de Parceiro', 'verbose_name_plural': 'Auditorias de Parceiro', 'ordering': ['-created_at'], 'default_permissions': ('add', 'view')},
        ),
    ]

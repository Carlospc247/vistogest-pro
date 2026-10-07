# apps/site/migrations/0002_site_loja_completa.py
"""
S7 — Migração completa da app site:
  - ConfiguracaoSite (singleton: WhatsApp, loja, aparência)
  - Pagina: sem campo empresa (isolamento por schema), + meta SEO
  - ProdutoSite / ServicoSite: controlo de visibilidade e preço
  - ClienteSite: sem empresa=, + senha_hash
  - Carrinho + ItemCarrinho
  - PedidoOnline + ItemPedidoOnline
  - Concurso / Candidatura
  - SolicitacaoContato / Reclamacao / ComprovativoCompra
"""
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
import cloudinary.models


class Migration(migrations.Migration):

    dependencies = [
        ('site', '0001_initial'),
        ('produtos', '0001_initial'),
        ('servicos', '0001_initial'),
    ]

    operations = [
        # ── ConfiguracaoSite ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='ConfiguracaoSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('nome_exibicao', models.CharField(max_length=100, default='Minha Empresa')),
                ('logo', cloudinary.models.CloudinaryField(blank=True, null=True, verbose_name='logo')),
                ('favicon', cloudinary.models.CloudinaryField(blank=True, null=True, verbose_name='favicon')),
                ('slogan', models.CharField(max_length=200, blank=True)),
                ('cor_primaria', models.CharField(max_length=7, default='#1E40AF')),
                ('cor_secundaria', models.CharField(max_length=7, default='#F59E0B')),
                ('fonte', models.CharField(max_length=50, default='Inter')),
                ('email_publico', models.EmailField(blank=True)),
                ('telefone_publico', models.CharField(max_length=20, blank=True)),
                ('endereco_publico', models.TextField(blank=True)),
                ('numero_whatsapp', models.CharField(max_length=20, blank=True)),
                ('mensagem_whatsapp', models.CharField(max_length=200, default='Olá! Vim do vosso site.')),
                ('mostrar_whatsapp', models.BooleanField(default=True)),
                ('loja_activa', models.BooleanField(default=True)),
                ('aceita_pedidos', models.BooleanField(default=True)),
                ('moeda', models.CharField(max_length=3, default='AOA')),
                ('mensagem_confirmacao', models.TextField(blank=True, default='O seu pedido foi recebido.')),
                ('email_notificacao_pedidos', models.EmailField(blank=True)),
                ('facebook', models.URLField(blank=True)),
                ('instagram', models.URLField(blank=True)),
                ('linkedin', models.URLField(blank=True)),
                ('youtube', models.URLField(blank=True)),
                ('iframe_mapa', models.TextField(blank=True)),
            ],
            options={'verbose_name': 'Configuração do Site'},
        ),

        # ── Alterações à Pagina existente ────────────────────────────────────
        migrations.AddField(
            model_name='pagina',
            name='meta_descricao',
            field=models.CharField(max_length=160, blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pagina',
            name='meta_imagem',
            field=cloudinary.models.CloudinaryField(blank=True, null=True, verbose_name='meta_imagem'),
        ),
        # Remover campo 'nome_exibicao' que foi movido para ConfiguracaoSite
        migrations.RemoveField(model_name='pagina', name='nome_exibicao'),

        # ── ProdutoSite ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='ProdutoSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('visivel_na_loja', models.BooleanField(default=True)),
                ('preco_customizado', models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                ('destaque', models.BooleanField(default=False)),
                ('ordem_exibicao', models.IntegerField(default=0)),
                ('descricao_loja', models.TextField(blank=True)),
                ('produto', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='configuracao_site', to='produtos.produto')),
            ],
            options={'verbose_name': 'Produto na Loja', 'ordering': ['ordem_exibicao']},
        ),

        # ── ServicoSite ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='ServicoSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('visivel_na_loja', models.BooleanField(default=True)),
                ('preco_customizado', models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                ('destaque', models.BooleanField(default=False)),
                ('ordem_exibicao', models.IntegerField(default=0)),
                ('descricao_loja', models.TextField(blank=True)),
                ('servico', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='configuracao_site', to='servicos.servico')),
            ],
            options={'verbose_name': 'Serviço na Loja', 'ordering': ['ordem_exibicao']},
        ),

        # ── ClienteSite refactor ─────────────────────────────────────────────
        migrations.AddField(
            model_name='clientesite',
            name='senha_hash',
            field=models.CharField(max_length=256, blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='clientesite',
            name='ativo',
            field=models.BooleanField(default=True),
        ),
        migrations.RenameField(
            model_name='clientesite',
            old_name='registrado',
            new_name='registrado_no_sistema',
        ),

        # ── Carrinho e ItemCarrinho ───────────────────────────────────────────
        migrations.CreateModel(
            name='Carrinho',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session_key', models.CharField(max_length=100, blank=True, db_index=True)),
                ('ativo', models.BooleanField(default=True)),
                ('cliente_site', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='carrinhos', to='site.clientesite')),
            ],
            options={'verbose_name': 'Carrinho'},
        ),
        migrations.CreateModel(
            name='ItemCarrinho',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantidade', models.IntegerField(default=1)),
                ('preco_unitario', models.DecimalField(max_digits=10, decimal_places=2)),
                ('carrinho', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens', to='site.carrinho')),
                ('produto', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, to='produtos.produto')),
                ('servico', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, to='servicos.servico')),
            ],
            options={'verbose_name': 'Item do Carrinho'},
        ),

        # ── PedidoOnline e ItemPedidoOnline ───────────────────────────────────
        migrations.CreateModel(
            name='PedidoOnline',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('referencia', models.CharField(max_length=50, unique=True, db_index=True)),
                ('status', models.CharField(max_length=20, choices=[
                    ('pendente','Pendente'),('confirmado','Confirmado'),
                    ('em_preparacao','Em Preparação'),('enviado','Enviado / A Caminho'),
                    ('entregue','Entregue'),('cancelado','Cancelado'),
                ], default='pendente')),
                ('total', models.DecimalField(max_digits=12, decimal_places=2, default=0)),
                ('moeda', models.CharField(max_length=3, default='AOA')),
                ('nome_destinatario', models.CharField(max_length=200)),
                ('telefone_entrega', models.CharField(max_length=20, blank=True)),
                ('endereco_entrega', models.TextField()),
                ('notas', models.TextField(blank=True)),
                ('venda_id', models.IntegerField(null=True, blank=True)),
                ('cliente_site', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pedidos', to='site.clientesite')),
                ('processado_por', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pedidos_online_processados', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Pedido Online', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ItemPedidoOnline',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('nome_item', models.CharField(max_length=200)),
                ('quantidade', models.IntegerField(default=1)),
                ('preco_unitario', models.DecimalField(max_digits=10, decimal_places=2)),
                ('total_linha', models.DecimalField(max_digits=12, decimal_places=2)),
                ('pedido', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens', to='site.pedidoonline')),
                ('produto', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, to='produtos.produto')),
                ('servico', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, to='servicos.servico')),
            ],
            options={'verbose_name': 'Item do Pedido'},
        ),

        # ── ComprovativoCompra refactor ───────────────────────────────────────
        migrations.AddField(
            model_name='comprovativocompra',
            name='pedido',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='comprovativos', to='site.pedidoonline'),
        ),
        migrations.AddField(
            model_name='comprovativocompra',
            name='verificado',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='comprovativocompra',
            name='nome',
            field=models.CharField(max_length=200, blank=True, default=''),
            preserve_default=False,
        ),

        # ── Secao: novos tipos ────────────────────────────────────────────────
        migrations.AlterField(
            model_name='secao',
            name='tipo',
            field=models.CharField(max_length=20, choices=[
                ('carrossel','Carrossel de Imagens'),
                ('card','Cards de Destaque'),
                ('imagem_fixa','Imagem Fixa'),
                ('texto','Bloco de Texto'),
                ('localizacao','Mapa / Localização'),
                ('whatsapp','Botão WhatsApp'),
                ('produtos','Vitrine de Produtos'),
                ('servicos','Vitrine de Serviços'),
                ('depoimentos','Depoimentos / Testemunhos'),
                ('faq','Perguntas Frequentes'),
            ]),
        ),

        # ── Reclamacao: campo resposta ────────────────────────────────────────
        migrations.AddField(
            model_name='reclamacao',
            name='resposta',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
    ]

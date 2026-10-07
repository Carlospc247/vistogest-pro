# apps/site/migrations/0003_s12_site_builder.py
"""
S12 — Site Builder: campos de design por secção e configuração global do tema.

Secao: fundo, cor_fundo_custom, imagem_fundo, padding_vertical, classe_extra,
       animacao_entrada, largura_maxima, novos tipos de secção (hero, cta,
       galeria, contador, equipa, parceiros, video, formulario, divider).

ConfiguracaoSite: tema_layout, raio_bordas, fonte_titulos, fonte_corpo,
                  sombras_activas, animacoes_activas, header_transparente,
                  rodape_cor, rodape_texto_cor, texto_botao_primario,
                  texto_whatsapp_flutuante.
"""
import cloudinary.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('site', '0002_site_loja_completa'),
    ]

    operations = [
        # ── ConfiguracaoSite — campos de tema global ──────────────────────────
        migrations.AddField(
            model_name='configuracaosite',
            name='tema_layout',
            field=models.CharField(
                max_length=20, default='moderno',
                choices=[
                    ('moderno', 'Moderno / Limpo'), ('classico', 'Clássico / Elegante'),
                    ('minimalista', 'Minimalista'), ('arrojado', 'Arrojado / Vibrante'),
                    ('escuro', 'Escuro / Dark'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='raio_bordas',
            field=models.CharField(
                max_length=10, default='md',
                choices=[('none','Sem raio'),('sm','Pequeno'),('md','Médio'),('lg','Grande'),('full','Redondo')],
            ),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='fonte_titulos',
            field=models.CharField(max_length=50, default='Inter'),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='fonte_corpo',
            field=models.CharField(max_length=50, default='Inter'),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='sombras_activas',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='animacoes_activas',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='header_transparente',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='rodape_cor',
            field=models.CharField(max_length=7, default='#1E293B'),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='rodape_texto_cor',
            field=models.CharField(max_length=7, default='#FFFFFF'),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='texto_botao_primario',
            field=models.CharField(max_length=30, blank=True, default='Ver mais'),
        ),
        migrations.AddField(
            model_name='configuracaosite',
            name='texto_whatsapp_flutuante',
            field=models.CharField(max_length=60, blank=True, default='Falar no WhatsApp'),
        ),

        # ── Secao — campos de design por secção ───────────────────────────────
        migrations.AddField(
            model_name='secao',
            name='fundo',
            field=models.CharField(
                max_length=20, default='branco',
                choices=[
                    ('branco', 'Branco'), ('cinza_claro', 'Cinza Claro'),
                    ('cor_primaria', 'Cor Primária'), ('cor_secundaria', 'Cor Secundária'),
                    ('imagem', 'Imagem de Fundo (parallax)'), ('gradiente', 'Gradiente'),
                    ('escuro', 'Escuro / Noturno'), ('transparente', 'Transparente'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='secao',
            name='cor_fundo_custom',
            field=models.CharField(max_length=7, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='secao',
            name='imagem_fundo',
            field=cloudinary.models.CloudinaryField(blank=True, null=True, verbose_name='imagem_fundo'),
        ),
        migrations.AddField(
            model_name='secao',
            name='padding_vertical',
            field=models.CharField(
                max_length=10, default='md',
                choices=[('sm','Pequeno'),('md','Médio'),('lg','Grande'),('xl','Extra Grande'),('none','Nenhum')],
            ),
        ),
        migrations.AddField(
            model_name='secao',
            name='classe_extra',
            field=models.CharField(max_length=200, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='secao',
            name='animacao_entrada',
            field=models.CharField(
                max_length=15, default='nenhuma',
                choices=[
                    ('nenhuma', 'Sem Animação'), ('fade-in', 'Fade In'),
                    ('slide-up', 'Slide de Baixo para Cima'), ('slide-left', 'Slide da Esquerda'),
                    ('zoom', 'Zoom In'), ('bounce', 'Bounce'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='secao',
            name='largura_maxima',
            field=models.CharField(
                max_length=10, default='7xl',
                choices=[('sm','Estreito'),('3xl','Normal'),('5xl','Largo'),('7xl','Total'),('full','Sem limite')],
            ),
        ),
    ]

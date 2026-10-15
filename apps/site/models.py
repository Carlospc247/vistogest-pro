# apps/site/models.py
import uuid
from decimal import Decimal
from django.db import models
from django.utils.text import slugify
from apps.core.models import TimeStampedModel
from apps.produtos.models import Produto
from apps.servicos.models import Servico
from cloudinary.models import CloudinaryField
from django.urls import reverse
from django.conf import settings





def formatar_duracao(td):
    s = max(int(td.total_seconds()), 0)
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d: return f"{d}d {h}h"
    if h: return f"{h}h {m}min"
    if m: return f"{m}min"
    return "menos de 1 min"


class RastreioAtendimento(models.Model):
    """Quem atendeu, quando, e o feedback para o cliente."""
    atendido_em     = models.DateTimeField(null=True, blank=True)
    atendido_por    = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    feedback_gestor = models.TextField(blank=True)

    class Meta:
        abstract = True

    @property
    def tempo_resposta(self):
        if self.atendido_em and getattr(self, 'created_at', None):
            return self.atendido_em - self.created_at
        return None

    @property
    def tempo_resposta_fmt(self):
        t = self.tempo_resposta
        return formatar_duracao(t) if t is not None else ''


# ──────────────────────────────────────────────────────────────────────────────
# Configurações globais do site/loja
# ──────────────────────────────────────────────────────────────────────────────

class ConfiguracaoSite(TimeStampedModel):
    """
    Configuração global do site da empresa.
    Singleton por tenant — uma linha por schema.
    Contém configurações do site institucional e da loja online.
    """
    # Identidade
    nome_exibicao    = models.CharField(max_length=100, default='Minha Empresa')
    logo             = CloudinaryField('logo', blank=True, null=True)
    favicon          = CloudinaryField('favicon', blank=True, null=True)
    slogan           = models.CharField(max_length=200, blank=True)

    # Aparência
    cor_primaria     = models.CharField(max_length=7, default='#1E40AF')
    cor_secundaria   = models.CharField(max_length=7, default='#F59E0B')
    fonte            = models.CharField(max_length=50, default='Inter')

    # Contactos públicos
    email_publico    = models.EmailField(blank=True)
    telefone_publico = models.CharField(max_length=20, blank=True)
    endereco_publico = models.TextField(blank=True)

    # WhatsApp (obrigatório para atendimento e notificação de pedidos)
    numero_whatsapp      = models.CharField(
        max_length=20, blank=True,
        help_text='Formato internacional sem +. Ex.: 244923456789'
    )
    mensagem_whatsapp    = models.CharField(
        max_length=200, default='Olá! Vim do vosso site.',
        help_text='Mensagem pré-definida que abre no WhatsApp do cliente.'
    )
    mostrar_whatsapp     = models.BooleanField(default=True)

    # Loja online
    loja_activa          = models.BooleanField(
        default=True,
        help_text='Activar loja online. Só disponível se a licença incluir o módulo site.'
    )
    aceita_pedidos       = models.BooleanField(default=True)
    moeda                = models.CharField(max_length=3, default='AOA')
    mensagem_confirmacao = models.TextField(
        blank=True,
        default='O seu pedido foi recebido. Entraremos em contacto em breve.'
    )
    email_notificacao_pedidos = models.EmailField(
        blank=True,
        help_text='Email interno para notificar a empresa quando chega um novo pedido.'
    )

    # Redes sociais
    facebook  = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    linkedin  = models.URLField(blank=True)
    youtube   = models.URLField(blank=True)

    # Mapa / localização
    iframe_mapa = models.TextField(
        blank=True,
        help_text='iframe do Google Maps (copiar o código de incorporação).'
    )

    # S12 — Site Builder: Estilo global da loja/site
    tema_layout = models.CharField(
        max_length=20, default='moderno',
        choices=[
            ('moderno',    'Moderno / Limpo'),
            ('classico',   'Clássico / Elegante'),
            ('minimalista','Minimalista'),
            ('arrojado',   'Arrojado / Vibrante'),
            ('escuro',     'Escuro / Dark'),
        ],
        help_text='Tema visual global do site'
    )
    raio_bordas = models.CharField(
        max_length=10, default='md',
        choices=[('none','Sem raio'),('sm','Pequeno'),('md','Médio'),('lg','Grande'),('full','Redondo')],
    )
    fonte_titulos = models.CharField(
        max_length=50, default='Inter',
        choices=[
            ('Inter','Inter'),('Poppins','Poppins'),('Montserrat','Montserrat'),
            ('Roboto','Roboto'),('Playfair Display','Playfair Display'),
            ('Lato','Lato'),('Open Sans','Open Sans'),
        ],
    )
    fonte_corpo = models.CharField(
        max_length=50, default='Inter',
        choices=[
            ('Inter','Inter'),('Roboto','Roboto'),('Lato','Lato'),
            ('Open Sans','Open Sans'),('Nunito','Nunito'),
        ],
    )
    sombras_activas = models.BooleanField(default=True, help_text='Activar sombras nos cards')
    animacoes_activas = models.BooleanField(default=True, help_text='Activar animações de entrada')
    header_transparente = models.BooleanField(default=False, help_text='Header transparente sobre o hero')
    rodape_cor = models.CharField(max_length=7, default='#1E293B', help_text='Cor de fundo do rodapé')
    rodape_texto_cor = models.CharField(max_length=7, default='#FFFFFF')
    texto_botao_primario = models.CharField(max_length=30, blank=True, default='Ver mais')
    texto_whatsapp_flutuante = models.CharField(max_length=60, blank=True, default='Falar no WhatsApp')

    class Meta:
        verbose_name = 'Configuração do Site'
        verbose_name_plural = 'Configuração do Site'

    def __str__(self):
        return f"Configuração do Site — {self.nome_exibicao}"

    @classmethod
    def obter(cls):
        """Obtém (ou cria vazia) a configuração singleton do tenant activo."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def salvar(self):
        self.pk = 1
        self.save()

    def url_whatsapp(self, mensagem_extra: str = '') -> str:
        """Gera o link de WhatsApp com mensagem pré-definida."""
        import urllib.parse
        if not self.numero_whatsapp:
            return ''
        msg = f"{self.mensagem_whatsapp} {mensagem_extra}".strip()
        return f"https://wa.me/{self.numero_whatsapp}?text={urllib.parse.quote(msg)}"


# ──────────────────────────────────────────────────────────────────────────────
# Página institucional
# ──────────────────────────────────────────────────────────────────────────────
class Pagina(TimeStampedModel):
    """
    Página pública do site institucional do tenant.

    O isolamento por empresa é garantido pelo schema do django-tenants.
    Não é necessário armazenar uma FK para Empresa neste modelo.
    """

    titulo = models.CharField(max_length=200)

    slug = models.SlugField(unique=True)

    conteudo_json = models.JSONField(default=dict)

    ativo = models.BooleanField(default=True)

    em_rascunho = models.BooleanField(default=True)

    preview_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False
    )

    meta_descricao = models.CharField(
        max_length=160,
        blank=True,
        help_text='Descrição para SEO (max 160 chars).'
    )

    meta_imagem = CloudinaryField(
        'meta_imagem',
        blank=True,
        null=True,
        help_text='Imagem Open Graph (partilha em redes sociais).'
    )

    class Meta:
        verbose_name = 'Página'
        verbose_name_plural = 'Páginas'

    def __str__(self):
        return self.titulo

    def reset_preview_token(self):
        self.preview_token = uuid.uuid4()
        self.save(update_fields=['preview_token'])

    def get_absolute_url(self):
        """
        Retorna a URL pública da página.

        A primeira página criada no tenant é considerada a Home.
        """
        principal_pk = (
            type(self)
            .objects
            .order_by('pk')
            .values_list('pk', flat=True)
            .first()
        )

        if principal_pk == self.pk:
            return reverse('site:pagina_home')

        return reverse(
            'site:pagina_detalhe',
            kwargs={'slug': self.slug}
        )

    @classmethod
    def obter_principal(cls, apenas_publicada=True):
        """
        Retorna a página principal do tenant.

        A primeira página criada é considerada a Home.
        Caso esteja em rascunho ou inativa, retorna None
        quando apenas_publicada=True.
        """
        pagina = cls.objects.order_by('pk').first()

        if pagina is None:
            return None

        if (
            apenas_publicada
            and (pagina.em_rascunho or not pagina.ativo)
        ):
            return None

        return pagina
    

# ── 4. Novo modelo: eventos do público (visitas, cliques no WhatsApp, etc.) ──
class EventoSite(TimeStampedModel):
    """Interação anónima do público. Não guarda IP nem dados pessoais."""
    TIPO_CHOICES = [
        ('visita',   'Visita à página'),
        ('whatsapp', 'Clique no WhatsApp'),
        ('produto',  'Visualização de produto'),
        ('carrinho', 'Item adicionado ao carrinho'),
    ]
    tipo        = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    caminho     = models.CharField(max_length=300, blank=True)
    referencia  = models.CharField(max_length=120, blank=True)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    dispositivo = models.CharField(max_length=10, blank=True)
 
    class Meta:
        verbose_name = 'Evento do Site'
        verbose_name_plural = 'Eventos do Site'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['tipo', 'created_at'])]
 
    def __str__(self):
        return f"{self.get_tipo_display()} — {self.caminho or self.referencia}"
    

class Secao(TimeStampedModel):
    """Secção customizável de uma página (editor no-code / drag-and-drop)."""
    TIPO_CHOICES = [
        ('hero',        'Hero / Banner Principal'),
        ('carrossel',   'Carrossel de Imagens'),
        ('card',        'Cards de Destaque'),
        ('imagem_fixa', 'Imagem Fixa com Texto'),
        ('texto',       'Bloco de Texto Rico'),
        ('localizacao', 'Mapa / Localização'),
        ('whatsapp',    'Botão WhatsApp Flutuante'),
        ('produtos',    'Vitrine de Produtos'),
        ('servicos',    'Vitrine de Serviços'),
        ('depoimentos', 'Depoimentos / Testemunhos'),
        ('faq',         'Perguntas Frequentes'),
        ('cta',         'Call-to-Action'),
        ('galeria',     'Galeria de Imagens'),
        ('contador',    'Contadores Animados'),
        ('equipa',      'Equipa / Sobre Nós'),
        ('parceiros',   'Logos de Parceiros / Clientes'),
        ('video',       'Vídeo Incorporado'),
        ('formulario',  'Formulário de Contacto'),
        ('agendamento', 'Agendamento de Servico'),
        ('divider',     'Separador / Espaço'),
    ]

    # Layout de fundo
    FUNDO_CHOICES = [
        ('branco',      'Branco'),
        ('cinza_claro', 'Cinza Claro'),
        ('cor_primaria','Cor Primária'),
        ('cor_secundaria','Cor Secundária'),
        ('imagem',      'Imagem de Fundo (parallax)'),
        ('gradiente',   'Gradiente'),
        ('escuro',      'Escuro / Noturno'),
        ('transparente','Transparente'),
    ]

    ANIMACAO_CHOICES = [
        ('nenhuma',    'Sem Animação'),
        ('fade-in',    'Fade In'),
        ('slide-up',   'Slide de Baixo para Cima'),
        ('slide-left', 'Slide da Esquerda'),
        ('zoom',       'Zoom In'),
        ('bounce',     'Bounce'),
    ]

    pagina    = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name='secoes')
    tipo      = models.CharField(max_length=20, choices=TIPO_CHOICES)
    dados     = models.JSONField(default=dict, help_text='Conteúdo da secção em JSON')
    ordem     = models.IntegerField(default=0)
    ativo     = models.BooleanField(default=True)

    # S12 — Site Builder: campos de design por secção
    fundo              = models.CharField(max_length=20, choices=FUNDO_CHOICES, default='branco')
    cor_fundo_custom   = models.CharField(max_length=7, blank=True,
                          help_text='Cor hexadecimal personalizada (ex: #F3F4F6)')
    imagem_fundo       = CloudinaryField('imagem_fundo', blank=True, null=True,
                          help_text='Imagem de fundo (parallax) para esta secção')
    padding_vertical   = models.CharField(
        max_length=10, default='md',
        choices=[('sm','Pequeno'),('md','Médio'),('lg','Grande'),('xl','Extra Grande'),('none','Nenhum')],
        help_text='Espaçamento vertical interno'
    )
    classe_extra       = models.CharField(max_length=200, blank=True,
                          help_text='Classes CSS Tailwind adicionais (para utilizadores avançados)')
    animacao_entrada   = models.CharField(max_length=15, choices=ANIMACAO_CHOICES, default='nenhuma')
    largura_maxima     = models.CharField(
        max_length=10, default='7xl',
        choices=[('sm','Estreito'),('3xl','Normal'),('5xl','Largo'),('7xl','Total'),('full','Sem limite')],
        help_text='Largura máxima do conteúdo desta secção'
    )

    class Meta:
        ordering = ['ordem']
        verbose_name = 'Secção'
        verbose_name_plural = 'Secções'

    def __str__(self):
        return f"{self.pagina.titulo} — {self.get_tipo_display()}"


# ──────────────────────────────────────────────────────────────────────────────
# Loja online — catálogo (automático via Produto/Servico)
# ──────────────────────────────────────────────────────────────────────────────

class ProdutoSite(TimeStampedModel):
    """
    Controlo de visibilidade de um Produto na loja online.
    Por defeito, TODOS os Produto activos são visíveis.
    Este modelo permite ocultar ou personalizar um produto específico.

    Regra de negócio: se não existir entrada aqui para um produto,
    o produto está visível com o preço original.
    """
    produto           = models.OneToOneField(Produto, on_delete=models.CASCADE, related_name='configuracao_site')
    visivel_na_loja   = models.BooleanField(default=True)
    preco_customizado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Deixar em branco para usar o preço original do produto.')
    destaque          = models.BooleanField(default=False,
                        help_text='Mostrar em destaque na página inicial da loja.')
    ordem_exibicao    = models.IntegerField(default=0)
    descricao_loja    = models.TextField(blank=True,
                        help_text='Descrição complementar apenas para a loja online.')

    class Meta:
        verbose_name = 'Produto na Loja'
        verbose_name_plural = 'Produtos na Loja'
        ordering = ['ordem_exibicao', 'produto__nome_produto']

    def __str__(self):
        return f"{self.produto.nome_produto} ({'visível' if self.visivel_na_loja else 'oculto'})"

    @property
    def preco_final(self):
        """Preço a exibir: customizado se definido, senão preço do produto."""
        if self.preco_customizado is not None:
            return self.preco_customizado
        return getattr(self.produto, 'preco_venda', Decimal('0.00'))


class ServicoSite(TimeStampedModel):
    """
    Controlo de visibilidade de um Servico na loja online.
    Mesma lógica de ProdutoSite — por defeito, todos os serviços activos são visíveis.
    """
    servico           = models.OneToOneField(
        Servico, on_delete=models.CASCADE, related_name='configuracao_site'
    )
    visivel_na_loja   = models.BooleanField(default=True)
    preco_customizado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    destaque          = models.BooleanField(default=False)
    ordem_exibicao    = models.IntegerField(default=0)
    descricao_loja    = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Serviço na Loja'
        verbose_name_plural = 'Serviços na Loja'
        ordering = ['ordem_exibicao', 'servico__nome']

    def __str__(self):
        return f"{self.servico.nome} ({'visível' if self.visivel_na_loja else 'oculto'})"

    @property
    def preco_final(self):
        if self.preco_customizado is not None:
            return self.preco_customizado
        return getattr(self.servico, 'preco', Decimal('0.00'))


# ──────────────────────────────────────────────────────────────────────────────
# Clientes do site (auto-cadastro)
# ──────────────────────────────────────────────────────────────────────────────

class ClienteSite(TimeStampedModel):
    """
    Cliente que se registou através do site público.
    Bug 2 corrigido: não passa 'empresa=' ao criar Cliente interno
    — o schema do tenant já isola por empresa.
    """
    nome            = models.CharField(max_length=200)
    email           = models.EmailField(unique=True)
    telefone        = models.CharField(max_length=50, blank=True)
    pessoa_juridica = models.BooleanField(default=False)
    senha_hash      = models.CharField(max_length=256, blank=True,
                      help_text='Hash da senha para autenticação no portal do cliente.')
    ativo           = models.BooleanField(default=True)
    registrado_no_sistema = models.BooleanField(default=False,
                            help_text='True quando já foi criado como Cliente interno.')

    class Meta:
        verbose_name = 'Cliente do Site'
        verbose_name_plural = 'Clientes do Site'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nome} <{self.email}>"

    def sincronizar_com_sistema(self):
        """
        Cria ou actualiza o Cliente interno correspondente.

        O isolamento por empresa já é garantido pelo django-tenants,
        portanto não existe campo empresa aqui.
        """
        if self.registrado_no_sistema:
            return

        try:
            from apps.clientes.models import Cliente

            tipo_cliente = (
                'pessoa_juridica'
                if self.pessoa_juridica
                else 'pessoa_fisica'
            )

            cliente = Cliente.objects.filter(
                email=self.email
            ).order_by('pk').first()

            if cliente is None:
                cliente = Cliente.objects.create(
                    nome_completo=self.nome,
                    email=self.email,
                    telefone=self.telefone,
                    tipo_cliente=tipo_cliente,
                )
            else:
                cliente.nome_completo = self.nome
                cliente.telefone = self.telefone
                cliente.tipo_cliente = tipo_cliente
                cliente.save(
                    update_fields=[
                        'nome_completo',
                        'telefone',
                        'tipo_cliente',
                        'updated_at',
                    ]
                )
            self.registrado_no_sistema = True
            self.save(update_fields=['registrado_no_sistema'])

        except Exception as exc:
            import logging

            logging.getLogger('site').exception(
                "Não foi possível sincronizar ClienteSite %s com Cliente.",
                self.email,
            )
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.registrado_no_sistema:
            self.sincronizar_com_sistema()


# ──────────────────────────────────────────────────────────────────────────────
# Carrinho de compras
# ──────────────────────────────────────────────────────────────────────────────

class Carrinho(TimeStampedModel):
    """Carrinho de compras por sessão ou cliente autenticado."""
    session_key  = models.CharField(max_length=100, blank=True, db_index=True)
    cliente_site = models.ForeignKey(
        ClienteSite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='carrinhos'
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Carrinho'
        verbose_name_plural = 'Carrinhos'

    def __str__(self):
        if self.cliente_site:
            return f"Carrinho de {self.cliente_site.nome}"
        return f"Carrinho sessão {self.session_key[:12]}"

    @property
    def total(self):
        return sum(item.total_linha for item in self.itens.all())

    @property
    def total_itens(self):
        return sum(item.quantidade for item in self.itens.all())

    @staticmethod
    def obter_ou_criar(session_key, cliente_site=None):
        """Obtém o carrinho activo ou cria um novo."""
        if cliente_site:
            cart, _ = Carrinho.objects.get_or_create(
                cliente_site=cliente_site,
                ativo=True,
                defaults={
                    'session_key': session_key or ''
                }
            )
        else:
            cart, _ = Carrinho.objects.get_or_create(
                session_key=session_key,
                ativo=True
            )

        return cart


class ItemCarrinho(TimeStampedModel):
    """Linha do carrinho — pode ser Produto ou Serviço."""
    carrinho       = models.ForeignKey(Carrinho, on_delete=models.CASCADE, related_name='itens')
    # Produto ou Serviço (um dos dois é preenchido)
    produto        = models.ForeignKey(Produto, on_delete=models.CASCADE, null=True, blank=True)
    servico        = models.ForeignKey(Servico, on_delete=models.CASCADE, null=True, blank=True)
    quantidade     = models.IntegerField(default=1)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Item do Carrinho'
        verbose_name_plural = 'Itens do Carrinho'

    def __str__(self):
        nome = self.produto.nome_produto if self.produto else (self.servico.nome if self.servico else '?')
        return f"{nome} × {self.quantidade}"

    @property
    def total_linha(self):
        return self.preco_unitario * self.quantidade

    @property
    def nome(self):
        if self.produto:
            return self.produto.nome_produto
        if self.servico:
            return self.servico.nome
        return '—'

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.produto and not self.servico:
            raise ValidationError("Item do carrinho deve ter Produto ou Serviço.")
        if self.produto and self.servico:
            raise ValidationError("Item do carrinho não pode ter Produto e Serviço simultaneamente.")


# ──────────────────────────────────────────────────────────────────────────────
# Pedido Online
# ──────────────────────────────────────────────────────────────────────────────

class PedidoOnline(TimeStampedModel):
    """
    Encomenda feita pelo visitante/cliente através da loja online.

    Fluxo:
      1. Cliente submete pedido → status='pendente'
      2. Operador vê no painel → confirma → status='confirmado'
      3. Operador cria Venda no sistema principal a partir do pedido
      4. Entrega efectuada → status='entregue'
      5. Atendimento complementar via WhatsApp
    """
    STATUS_CHOICES = [
        ('pendente',       'Pendente'),
        ('confirmado',     'Confirmado'),
        ('em_preparacao',  'Em Preparação'),
        ('enviado',        'Enviado / A Caminho'),
        ('entregue',       'Entregue'),
        ('cancelado',      'Cancelado'),
    ]

    cliente_site      = models.ForeignKey(
        ClienteSite, on_delete=models.PROTECT, related_name='pedidos'
    )
    referencia        = models.CharField(
        max_length=50, unique=True, db_index=True,
        help_text='Código único do pedido (ex.: PED-2026-0001). Gerado automaticamente.'
    )
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    total             = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    moeda             = models.CharField(max_length=3, default='AOA')

    # Entrega
    nome_destinatario = models.CharField(max_length=200)
    telefone_entrega  = models.CharField(max_length=20, blank=True)
    endereco_entrega  = models.TextField()
    notas             = models.TextField(blank=True)

    # Ligação com sistema principal (criada pelo operador após confirmar)
    venda_id          = models.IntegerField(
        null=True, blank=True,
        help_text='ID da Venda criada no sistema principal a partir deste pedido.'
    )
    processado_por    = models.ForeignKey(
        'core.Usuario',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos_online_processados',
        help_text='Funcionário que confirmou e processou o pedido.'
    )

    class Meta:
        verbose_name = 'Pedido Online'
        verbose_name_plural = 'Pedidos Online'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.referencia} — {self.cliente_site.nome} [{self.get_status_display()}]"

    def save(self, *args, **kwargs):
        if not self.referencia:
            self.referencia = self._gerar_referencia()
        if not self.total:
            self.total = sum(i.total_linha for i in self.itens.all()) if self.pk else Decimal('0.00')
        super().save(*args, **kwargs)

    @staticmethod
    def _gerar_referencia() -> str:
        from django.utils import timezone
        import random, string
        ano = timezone.now().year
        sufixo = ''.join(random.choices(string.digits, k=5))
        return f"PED-{ano}-{sufixo}"

    def url_whatsapp_pedido(self) -> str:
        """Gera link WhatsApp com a referência do pedido pré-preenchida."""
        config = ConfiguracaoSite.obter()
        if not config.numero_whatsapp:
            return ''
        msg = f"Olá! O meu pedido é o {self.referencia}. Quero acompanhar o estado."
        import urllib.parse
        return f"https://wa.me/{config.numero_whatsapp}?text={urllib.parse.quote(msg)}"

    def recalcular_total(self):
        self.total = sum(i.total_linha for i in self.itens.all())
        self.save(update_fields=['total'])


class ItemPedidoOnline(TimeStampedModel):
    """Linha de um pedido online — produto ou serviço."""
    pedido         = models.ForeignKey(PedidoOnline, on_delete=models.CASCADE, related_name='itens')
    produto        = models.ForeignKey(Produto, on_delete=models.PROTECT, null=True, blank=True)
    servico        = models.ForeignKey(Servico, on_delete=models.PROTECT, null=True, blank=True)
    nome_item      = models.CharField(max_length=200, help_text='Snapshot do nome no momento do pedido.')
    quantidade     = models.IntegerField(default=1)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total_linha    = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Item do Pedido'
        verbose_name_plural = 'Itens do Pedido'

    def __str__(self):
        return f"{self.nome_item} × {self.quantidade} ({self.pedido.referencia})"

    def save(self, *args, **kwargs):
        self.total_linha = self.preco_unitario * self.quantidade
        if not self.nome_item:
            if self.produto:
                self.nome_item = self.produto.nome_produto
            elif self.servico:
                self.nome_item = self.servico.nome
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# Concursos / Recrutamento
# ──────────────────────────────────────────────────────────────────────────────

class Concurso(TimeStampedModel):
    titulo      = models.CharField(max_length=200)
    descricao   = models.TextField()
    ativo       = models.BooleanField(default=False)
    data_inicio = models.DateField(null=True, blank=True)
    data_fim    = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Concurso / Vaga'
        verbose_name_plural = 'Concursos / Vagas'

    def __str__(self):
        return self.titulo


class Candidatura(TimeStampedModel):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'), ('avaliada', 'Avaliada'),
        ('rejeitada', 'Rejeitada'), ('aceita', 'Aceita'),
    ]
    concurso     = models.ForeignKey(Concurso, on_delete=models.CASCADE, related_name='candidaturas')
    nome         = models.CharField(max_length=200)
    email        = models.EmailField()
    telefone     = models.CharField(max_length=50, blank=True)
    cv           = models.FileField(upload_to='candidaturas/')
    observacoes  = models.TextField(blank=True)
    status       = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')

    class Meta:
        verbose_name = 'Candidatura'
        verbose_name_plural = 'Candidaturas'

    def __str__(self):
        return f"{self.nome} — {self.concurso.titulo}"


# ──────────────────────────────────────────────────────────────────────────────
# Contacto / Reclamações
# ──────────────────────────────────────────────────────────────────────────────

class SolicitacaoContato(TimeStampedModel, RastreioAtendimento):
    TIPO_CHOICES = [
        ('contato', 'Contacto Geral'),
        ('compra_produto', 'Compra de Produto'),
        ('compra_servico', 'Compra de Serviço'),
        ('suporte', 'Suporte Pós-Venda'),
    ]
    nome      = models.CharField(max_length=200)
    email     = models.EmailField()
    telefone  = models.CharField(max_length=50, blank=True)
    mensagem  = models.TextField()
    tipo      = models.CharField(max_length=20, choices=TIPO_CHOICES, default='contato')
    atendido  = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Solicitação de Contacto'
        verbose_name_plural = 'Solicitações de Contacto'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nome} — {self.get_tipo_display()}"


class Reclamacao(TimeStampedModel, RastreioAtendimento):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('em_analise', 'Em Análise'),
        ('resolvida', 'Resolvida'),
    ]
    cliente_nome     = models.CharField(max_length=200)
    cliente_email    = models.EmailField()
    cliente_telefone = models.CharField(max_length=50, blank=True)
    assunto          = models.CharField(max_length=200)
    mensagem         = models.TextField()
    documentos       = models.FileField(upload_to='reclamacoes/', blank=True, null=True)
    imagens          = CloudinaryField('imagens', blank=True, null=True)
    status           = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    atendido         = models.BooleanField(default=False)
    resposta         = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Reclamação'
        verbose_name_plural = 'Reclamações'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.cliente_nome} — {self.assunto}"


# ──────────────────────────────────────────────────────────────────────────────
# Comprovativo de compra (para upload pelo cliente)
# ──────────────────────────────────────────────────────────────────────────────

class ComprovativoCompra(TimeStampedModel):
    """Cliente envia comprovativo de pagamento (ex.: transferência bancária)."""
    pedido      = models.ForeignKey(
        PedidoOnline, on_delete=models.CASCADE, related_name='comprovativos',
        null=True, blank=True
    )
    nome        = models.CharField(max_length=200, blank=True)
    descricao   = models.CharField(max_length=255, blank=True)
    imagem      = CloudinaryField('imagem', blank=True, null=True)
    verificado  = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Comprovativo de Compra'
        verbose_name_plural = 'Comprovativos de Compra'
        ordering = ['-created_at']

    def __str__(self):
        ref = self.pedido.referencia if self.pedido else 'sem pedido'
        return f"Comprovativo {ref} — {self.created_at.strftime('%d/%m/%Y')}"




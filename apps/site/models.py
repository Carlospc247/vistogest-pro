# apps/site/models.py
import uuid
from django.db import models
from apps.core.models import TimeStampedModel
from apps.empresas.models import Empresa
from apps.produtos.models import Produto
from apps.clientes.models import Cliente  # para criar automaticamente novos clientes
from cloudinary.models import CloudinaryField


# ==========================================
# Página principal da empresa
# ==========================================
class Pagina(TimeStampedModel):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="paginas")
    titulo = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    conteudo_json = models.JSONField(default=dict)  # Estrutura no-code
    nome_exibicao = models.CharField(max_length=100, default="Minha Empresa")  # Personalização
    ativo = models.BooleanField(default=True)
    em_rascunho = models.BooleanField(default=True)
    preview_token = models.UUIDField(default=uuid.uuid4, editable=False)
    
    
    def reset_preview_token(self):
        self.preview_token = uuid.uuid4()
        self.save()

    class Meta:
        verbose_name = "Página"
        verbose_name_plural = "Páginas"

    def __str__(self):
        return f"{self.empresa.nome} - {self.titulo}"

# ==========================================
# Seções customizáveis
# ==========================================
class Secao(TimeStampedModel):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="secoes")
    tipo = models.CharField(max_length=50, choices=[
        ("carrossel", "Carrossel"),
        ("card", "Card"),
        ("imagem_fixa", "Imagem Fixa"),
        ("texto", "Texto"),
    ])
    dados = models.JSONField(default=dict)
    ordem = models.IntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem"]
        verbose_name = "Seção"
        verbose_name_plural = "Seções"

    def __str__(self):
        return f"{self.pagina.titulo} - {self.tipo}"

# ==========================================
# Candidaturas online (concursos)
# ==========================================
class Concurso(TimeStampedModel):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="concursos")
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    ativo = models.BooleanField(default=False)
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Concurso"
        verbose_name_plural = "Concursos"

    def __str__(self):
        return f"{self.pagina.empresa.nome} - {self.titulo}"

class Candidatura(TimeStampedModel):
    concurso = models.ForeignKey(Concurso, on_delete=models.CASCADE, related_name="candidaturas")
    nome = models.CharField(max_length=200)
    email = models.EmailField()
    telefone = models.CharField(max_length=50, blank=True)
    cv = models.FileField(upload_to="candidaturas/")
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=50, choices=[
        ("pendente", "Pendente"),
        ("avaliada", "Avaliadas"),
        ("rejeitada", "Rejeitada"),
        ("aceita", "Aceita"),
    ], default="pendente")

    class Meta:
        verbose_name = "Candidatura"
        verbose_name_plural = "Candidaturas"

    def __str__(self):
        return f"{self.nome} - {self.concurso.titulo}"

# ==========================================
# Produtos do sistema disponíveis no site
# ==========================================
class ProdutoSite(TimeStampedModel):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="produtos_site")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    ativo = models.BooleanField(default=True)
    permitir_entrega = models.BooleanField(default=True)
    preco_customizado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Produto no Site"
        verbose_name_plural = "Produtos no Site"

    def __str__(self):
        return f"{self.produto.nome_comercial} - {self.pagina.empresa.nome}"

# ==========================================
# Contato ou solicitações de compras via site
# ==========================================
class SolicitacaoContato(TimeStampedModel):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="solicitacoes_contato")
    nome = models.CharField(max_length=200)
    email = models.EmailField()
    telefone = models.CharField(max_length=50, blank=True)
    mensagem = models.TextField()
    tipo = models.CharField(max_length=50, choices=[
        ("contato", "Contato"),
        ("compra_produto", "Compra de Produto"),
        ("compra_servico", "Compra de Serviço"),
    ], default="contato")
    atendido = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Solicitação de Contato"
        verbose_name_plural = "Solicitações de Contato"

    def __str__(self):
        return f"{self.nome} - {self.tipo}"

# ==========================================
# Reclamações de clientes
# ==========================================
class Reclamacao(TimeStampedModel):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="reclamacoes")
    cliente_nome = models.CharField(max_length=200)
    cliente_email = models.EmailField()
    cliente_telefone = models.CharField(max_length=50, blank=True)
    assunto = models.CharField(max_length=200)
    mensagem = models.TextField()
    documentos = models.FileField(upload_to="reclamacoes/", blank=True, null=True)
    imagens = CloudinaryField('imagens', blank=True, null=True)
    status = models.CharField(max_length=50, choices=[
        ("pendente", "Pendente"),
        ("em_analise", "Em Análise"),
        ("resolvida", "Resolvida"),
    ], default="pendente")
    atendido = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Reclamação"
        verbose_name_plural = "Reclamações"

    def __str__(self):
        return f"{self.cliente_nome} - {self.assunto}"

# ==========================================
# Cadastro automático de clientes via site
# ==========================================
class ClienteSite(TimeStampedModel):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="clientes_site")
    nome = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    telefone = models.CharField(max_length=50, blank=True)
    pessoa_juridica = models.BooleanField(default=False)
    registrado = models.BooleanField(default=False)  # se já foi registrado no sistema

    class Meta:
        verbose_name = "Cliente Site"
        verbose_name_plural = "Clientes Site"

    def save(self, *args, **kwargs):
        # Ao criar, também cria automaticamente no sistema como Cliente real
        super().save(*args, **kwargs)
        if not self.registrado:
            from apps.clientes.models import Cliente
            cliente, created = Cliente.objects.get_or_create(
                email=self.email,
                defaults={
                    "nome": self.nome,
                    "telefone": self.telefone,
                    "pessoa_juridica": self.pessoa_juridica,
                    "empresa": self.pagina.empresa
                }
            )
            self.registrado = True
            super().save(update_fields=["registrado"])

    def __str__(self):
        return f"{self.nome} - {self.email}"


class ComprovativoCompra(models.Model):
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.CASCADE, 
        related_name='comprovativos'
    )
    descricao = models.CharField(max_length=255, blank=True, null=True)
    imagem = CloudinaryField('imagem', blank=True, null=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comprovativo de Compra"
        verbose_name_plural = "Comprovativos de Compra"
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.cliente.nome} - {self.data_criacao.strftime('%d/%m/%Y %H:%M')}"



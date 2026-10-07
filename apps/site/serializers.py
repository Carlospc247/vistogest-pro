# apps/site/serializers.py
from rest_framework import serializers
from .models import (
    ConfiguracaoSite, Pagina, Secao,
    ProdutoSite, ServicoSite, ClienteSite,
    Carrinho, ItemCarrinho,
    PedidoOnline, ItemPedidoOnline,
    Concurso, Candidatura,
    SolicitacaoContato, Reclamacao, ComprovativoCompra,
)


class ConfiguracaoSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ConfiguracaoSite
        fields = '__all__'


class SecaoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Secao
        fields = '__all__'


class PaginaSerializer(serializers.ModelSerializer):
    # Bug 5 corrigido: 'empresa' já não está em read_only_fields pois o modelo
    # não tem esse campo directamente (o isolamento é feito pelo schema).
    secoes = SecaoSerializer(many=True, read_only=True)

    class Meta:
        model  = Pagina
        fields = '__all__'


class ProdutoSiteSerializer(serializers.ModelSerializer):
    preco_final     = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    nome_produto    = serializers.CharField(source='produto.nome_produto', read_only=True)
    descricao       = serializers.CharField(source='produto.descricao', read_only=True)
    imagem_url      = serializers.SerializerMethodField()

    class Meta:
        model  = ProdutoSite
        fields = '__all__'

    def get_imagem_url(self, obj):
        try:
            return obj.produto.imagem.url if obj.produto.imagem else None
        except Exception:
            return None


class ServicoSiteSerializer(serializers.ModelSerializer):
    preco_final  = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    nome_servico = serializers.CharField(source='servico.nome', read_only=True)
    descricao    = serializers.CharField(source='servico.descricao', read_only=True)

    class Meta:
        model  = ServicoSite
        fields = '__all__'


class ClienteSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ClienteSite
        fields = ['id', 'nome', 'email', 'telefone', 'pessoa_juridica', 'ativo', 'created_at']
        extra_kwargs = {'senha_hash': {'write_only': True}}


class ItemCarrinhoSerializer(serializers.ModelSerializer):
    nome       = serializers.CharField(read_only=True)
    total_linha = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model  = ItemCarrinho
        fields = '__all__'


class CarrinhoSerializer(serializers.ModelSerializer):
    itens = ItemCarrinhoSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_itens = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Carrinho
        fields = '__all__'


class ItemPedidoOnlineSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ItemPedidoOnline
        fields = '__all__'
        read_only_fields = ['total_linha', 'nome_item']


class PedidoOnlineSerializer(serializers.ModelSerializer):
    itens             = ItemPedidoOnlineSerializer(many=True, read_only=True)
    status_display    = serializers.CharField(source='get_status_display', read_only=True)
    url_whatsapp      = serializers.CharField(source='url_whatsapp_pedido', read_only=True)

    class Meta:
        model  = PedidoOnline
        fields = '__all__'
        read_only_fields = ['referencia', 'total', 'venda_id']


class ConcursoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Concurso
        fields = '__all__'


class CandidaturaSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Candidatura
        fields = '__all__'


class SolicitacaoContatoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SolicitacaoContato
        fields = '__all__'


class ReclamacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Reclamacao
        fields = '__all__'


class ComprovativoCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ComprovativoCompra
        fields = '__all__'
        read_only_fields = ['created_at']

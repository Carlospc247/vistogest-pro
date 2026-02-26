from rest_framework import serializers
from apps.site.models import (
    Pagina, Secao, Concurso, Candidatura, ProdutoSite,
    SolicitacaoContato, Reclamacao, ClienteSite, ComprovativoCompra
)

class PaginaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        fields = "__all__"
        read_only_fields = ["empresa"]

class SecaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Secao
        fields = "__all__"

class ConcursoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Concurso
        fields = "__all__"

class CandidaturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidatura
        fields = "__all__"

class ProdutoSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProdutoSite
        fields = "__all__"

class SolicitacaoContatoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitacaoContato
        fields = "__all__"

class ReclamacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reclamacao
        fields = "__all__"

class ClienteSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteSite
        fields = "__all__"

class ComprovativoCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComprovativoCompra
        fields = "__all__"
        read_only_fields = ["data_criacao"]
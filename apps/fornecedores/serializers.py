# apps/fornecedores/serializers.py
from rest_framework import serializers
from .models import Fornecedor, Pedido, AvaliacaoFornecedor

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = '__all__'

class PedidoCompraSerializer(serializers.ModelSerializer):
    fornecedor_nome = serializers.ReadOnlyField(source='fornecedor.razao_social')

    class Meta:
        model = Pedido
        fields = '__all__'

class AvaliacaoFornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvaliacaoFornecedor
        fields = '__all__'
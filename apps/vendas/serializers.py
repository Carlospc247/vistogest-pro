# apps/vendas/serializers.py
"""
Serializers de Vendas.

Isolamento físico via django-tenants: nada aqui referencia `empresa`
(o campo não existe mais em Venda). O contexto do request continua a
ser usado para saber QUEM criou/assinou o documento (usuário), não
para filtrar por empresa.
"""

from rest_framework import serializers

from .models import FaturaProforma, ItemProforma, ItemVenda, Venda


class ItemVendaSerializer(serializers.ModelSerializer):
    """Serializer para itens de venda (FR/VD)."""

    iva_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    tipo_item = serializers.ReadOnlyField(source='tipo')  # usa a property 'tipo' do model

    class Meta:
        model = ItemVenda
        fields = [
            'id', 'produto', 'servico', 'nome_produto', 'nome_servico',
            'quantidade', 'preco_unitario', 'desconto_item',
            'taxa_iva', 'iva_percentual', 'iva_valor',
            'subtotal_sem_iva', 'total', 'tipo_item'
        ]
        read_only_fields = ['iva_valor', 'subtotal_sem_iva', 'total']


class VendaSerializer(serializers.ModelSerializer):
    """Serializer principal de Vendas. Gerencia a criação atómica de Venda + Itens."""

    itens = ItemVendaSerializer(many=True)
    cliente_nome = serializers.ReadOnlyField(source='cliente.nome_completo')
    vendedor_nome = serializers.ReadOnlyField(source='vendedor.nome_completo')
    forma_pagamento_nome = serializers.ReadOnlyField(source='forma_pagamento.nome')

    class Meta:
        model = Venda
        fields = [
            'id', 'numero_documento', 'cliente', 'cliente_nome',
            'vendedor', 'vendedor_nome', 'forma_pagamento',
            'forma_pagamento_nome', 'tipo_venda', 'status',
            'subtotal', 'desconto_valor', 'iva_valor', 'total',
            'valor_pago', 'troco', 'hash_documento', 'atcud',
            'observacoes', 'data_venda', 'itens'
        ]
        read_only_fields = ['numero_documento', 'hash_documento', 'atcud', 'troco']

    def create(self, validated_data):
        """
        Criação atómica: os cálculos de impostos e totais são disparados
        pelo próprio ItemVenda.save() / Venda.gerar_documento_fiscal().
        """
        itens_data = validated_data.pop('itens')

        venda = Venda.objects.create(**validated_data)

        for item_data in itens_data:
            ItemVenda.objects.create(venda=venda, **item_data)

        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            venda.gerar_documento_fiscal(request.user)

        return venda


class ItemProformaSerializer(serializers.ModelSerializer):
    """Serializer para itens de orçamentos (FP)."""

    class Meta:
        model = ItemProforma
        fields = '__all__'


class FaturaProformaSerializer(serializers.ModelSerializer):
    """Serializer para Fatura Proforma (FP)."""

    itens = ItemProformaSerializer(many=True, read_only=True)

    class Meta:
        model = FaturaProforma
        fields = '__all__'
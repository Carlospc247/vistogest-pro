#apps/vendas/services.py

from apps.core.services import gerar_numero_documento
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from apps.core.services import gerar_numero_documento
from apps.fiscal.utility import gerar_atcud_documento, gerar_hash_anterior
from apps.vendas.models import FormaPagamento, Venda, ItemVenda
from apps.fiscal.services import DocumentoFiscalService



def criar_venda(empresa, cliente, vendedor, itens_data, forma_pagamento=None):
    """
    Cria uma venda (Fatura-Recibo, FR) de forma segura e transacional.
    """
    tipo_documento = "FR"
    forma_pagamento = forma_pagamento or FormaPagamento.objects.first()
    if not forma_pagamento:
        raise ValueError("Nenhuma forma de pagamento configurada no sistema.")

    with transaction.atomic():
        # 🔐 Gera número de documento com controle de concorrência
        numero_documento = gerar_numero_documento(empresa, tipo_documento)

        # 🧾 Inicializa objeto em memória (não salva ainda)
        venda = Venda(
            empresa=empresa,
            cliente=cliente,
            vendedor=vendedor,
            forma_pagamento=forma_pagamento,
            tipo_venda="fatura_recibo",
            status="finalizada",
            numero_documento=numero_documento,
        )

        subtotal = total_iva = total_final = Decimal("0.00")

        # 🧮 Calcula e cria itens da venda
        for item in itens_data:
            qtd = Decimal(item["quantidade"])
            preco = Decimal(item["preco_unitario"])
            desconto = Decimal(item.get("desconto_item", "0.00"))
            taxa_iva = item.get("taxa_iva")
            iva_percentual = getattr(taxa_iva, "tax_percentage", Decimal("0.00")) if taxa_iva else Decimal("0.00")

            subtotal_item = preco * qtd
            total_iva_item = (subtotal_item - desconto) * iva_percentual / Decimal("100.00")
            total_item = subtotal_item - desconto + total_iva_item

            subtotal += subtotal_item
            total_iva += total_iva_item
            total_final += total_item

        # 🧾 Preenche totais
        venda.subtotal = subtotal
        venda.iva_valor = total_iva
        venda.total = total_final
        venda.valor_pago = total_final
        venda.troco = Decimal("0.00")

        # 💾 Só agora salva a venda no banco
        venda.save()

        # 🧱 Cria itens vinculados
        for item in itens_data:
            ItemVenda.objects.create(
                venda=venda,
                produto=item.get("produto"),
                servico=item.get("servico"),
                nome_produto=item.get("produto").nome_produto if item.get("produto") else item.get("servico").nome,
                quantidade=item["quantidade"],
                preco_unitario=item["preco_unitario"],
                desconto_item=item.get("desconto_item", Decimal("0.00")),
                taxa_iva=item.get("taxa_iva"),
                iva_valor=(item["preco_unitario"] * item["quantidade"] - item.get("desconto_item", Decimal("0.00")))
                          * getattr(item.get("taxa_iva", None), "tax_percentage", 0) / Decimal("100.00"),
                subtotal_sem_iva=item["preco_unitario"] * item["quantidade"],
                total=(item["preco_unitario"] * item["quantidade"] - item.get("desconto_item", Decimal("0.00")))
                      * (1 + getattr(item.get("taxa_iva", None), "tax_percentage", 0) / Decimal("100.00")),
            )

        # 🧾 Cria documento fiscal SAF-T AO
        service = DocumentoFiscalService()
        documento = service.criar_documento(
            empresa=empresa,
            tipo_documento=tipo_documento,
            cliente=cliente,
            usuario=vendedor.usuario,
            linhas=[
                {
                    "produto": item.get("produto"),
                    "servico": item.get("servico"),
                    "quantidade": item["quantidade"],
                    "preco_unitario": item["preco_unitario"],
                    "desconto": item.get("desconto_item", Decimal("0.00")),
                    "iva_valor": (item["preco_unitario"] * item["quantidade"] - item.get("desconto_item", Decimal("0.00")))
                                 * getattr(item.get("taxa_iva", None), "tax_percentage", 0) / Decimal("100.00"),
                }
                for item in itens_data
            ],
            dados_extra={
                "data_emissao": timezone.now(),
                "valor_total": venda.total,
                "numero": numero_documento,
            },
        )

        # 🔑 Atualiza venda com hash e ATCUD
        documento.hash_documento = gerar_hash_anterior(documento)
        documento.atcud = gerar_atcud_documento(documento)
        documento.save(update_fields=["hash_documento", "atcud"])

        return venda


def criar_fatura_credito(empresa, cliente, vendedor, itens_data, forma_pagamento=None, data_vencimento=None):
    """
    Cria uma fatura de crédito com itens e gera Documento Fiscal.
    itens_data = [
        {"produto": produto_obj, "quantidade": 2, "preco_unitario": 100, "desconto_item": 10, "taxa_iva": taxa_iva_obj},
        ...
    ]
    """
    from apps.fiscal.services import DocumentoFiscalService
    from apps.vendas.models import FaturaCredito, ItemFatura
    from decimal import Decimal

    forma_pagamento = forma_pagamento or FormaPagamento.objects.first()
    data_vencimento = data_vencimento or timezone.now().date() + timezone.timedelta(days=30)

    tipo_documento = "FT"
    numero_documento = gerar_numero_documento(empresa, tipo_documento)

    # 1️⃣ Criar fatura
    fatura = FaturaCredito(
        empresa=empresa,
        cliente=cliente,
        vendedor=vendedor,
        forma_pagamento=forma_pagamento,
        data_vencimento=data_vencimento,
        status='emitida',
        subtotal=Decimal('0.00'),
        total=Decimal('0.00'),
        iva_valor=Decimal('0.00'),
        numero_documento=numero_documento,
    )
    
    fatura.save()  # Salva antes de adicionar itens

    # 2️⃣ Adicionar itens e calcular totais
    subtotal = Decimal('0.00')
    total_iva = Decimal('0.00')
    total_final = Decimal('0.00')

    for item in itens_data:
        qtd = item['quantidade']
        preco = item['preco_unitario']
        desconto = item.get('desconto_item', Decimal('0.00'))
        taxa_iva = item.get('taxa_iva')
        iva_percentual = getattr(taxa_iva, 'tax_percentage', Decimal('0.00')) if taxa_iva else Decimal('0.00')

        subtotal_item = preco * qtd
        total_iva_item = (subtotal_item - desconto) * iva_percentual / Decimal('100.00')
        total_item = subtotal_item - desconto + total_iva_item

        ItemFatura.objects.create(
            fatura=fatura,
            produto=item.get('produto'),
            servico=item.get('servico'),
            nome_item=item.get('produto').nome if item.get('produto') else item.get('servico').nome,
            quantidade=qtd,
            preco_unitario=preco,
            desconto_item=desconto,
            taxa_iva=taxa_iva,
            iva_percentual=iva_percentual,
            iva_valor=total_iva_item,
            subtotal=subtotal_item,
            total=total_item,
        )

        subtotal += subtotal_item
        total_iva += total_iva_item
        total_final += total_item

    # Atualizar totais da fatura
    fatura.subtotal = subtotal
    fatura.iva_valor = total_iva
    fatura.total = total_final
    fatura.save(update_fields=['subtotal', 'iva_valor', 'total'])

    # 3️⃣ Gerar documento fiscal
    service = DocumentoFiscalService()
    documento = service.criar_documento(
        empresa=empresa,
        tipo_documento='FT',
        cliente=cliente,
        usuario=vendedor.user,
        linhas=[{
            'produto': item.get('produto'),
            'servico': item.get('servico'),
            'quantidade': item['quantidade'],
            'preco_unitario': item['preco_unitario'],
            'desconto': item.get('desconto_item', Decimal('0.00')),
            'iva_valor': (item['preco_unitario'] * item['quantidade'] - item.get('desconto_item', Decimal('0.00'))) * getattr(item.get('taxa_iva', None), 'tax_percentage', 0) / Decimal('100.00'),
        } for item in itens_data],
        dados_extra={
            'data_emissao': fatura.data_vencimento,
            'valor_total': fatura.total,
            'numero': numero_documento,
        },
    )

    fatura.hash_documento = documento.hash_documento
    fatura.atcud = documento.atcud
    fatura.save(update_fields=['hash_documento', 'atcud'])

    return fatura



def criar_recibo(empresa, cliente, vendedor, itens_data, forma_pagamento=None):
    """
    Cria um recibo e gera Documento Fiscal.
    itens_data = [
        {"produto": produto_obj, "quantidade": 2, "preco_unitario": 100, "desconto_item": 10, "taxa_iva": taxa_iva_obj},
        ...
    ]
    """
    from apps.fiscal.services import DocumentoFiscalService
    from apps.vendas.models import Recibo, ItemRecibo  # Alterado para usar ItemRecibo
    from decimal import Decimal

    forma_pagamento = forma_pagamento or FormaPagamento.objects.first()

    # 1️⃣ Criar recibo
    recibo = Recibo(
        empresa=empresa,
        cliente=cliente,
        vendedor=vendedor,
        forma_pagamento=forma_pagamento,
        status='emitido',
        subtotal=Decimal('0.00'),
        total=Decimal('0.00'),
        iva_valor=Decimal('0.00'),
    )

    recibo.save()  # Salva antes de adicionar itens

    # 2️⃣ Adicionar itens e calcular totais
    subtotal = Decimal('0.00')
    total_iva = Decimal('0.00')
    total_final = Decimal('0.00')

    for item in itens_data:
        qtd = item['quantidade']
        preco = item['preco_unitario']
        desconto = item.get('desconto_item', Decimal('0.00'))
        taxa_iva = item.get('taxa_iva')
        iva_percentual = getattr(taxa_iva, 'tax_percentage', Decimal('0.00')) if taxa_iva else Decimal('0.00')

        subtotal_item = preco * qtd
        total_iva_item = (subtotal_item - desconto) * iva_percentual / Decimal('100.00')
        total_item = subtotal_item - desconto + total_iva_item

        ItemRecibo.objects.create(  # Alterado para criar ItemRecibo
            recibo=recibo,
            produto=item.get('produto'),
            servico=item.get('servico'),
            nome_produto=item.get('produto').nome if item.get('produto') else item.get('servico').nome,
            quantidade=qtd,
            preco_unitario=preco,
            desconto_item=desconto,
            taxa_iva=taxa_iva,
            iva_valor=total_iva_item,
            subtotal_sem_iva=subtotal_item,
            total=total_item,
        )

        subtotal += subtotal_item
        total_iva += total_iva_item
        total_final += total_item

    # Atualiza os totais do recibo
    recibo.subtotal = subtotal
    recibo.iva_valor = total_iva
    recibo.total = total_final
    recibo.save(update_fields=['subtotal', 'iva_valor', 'total'])

    # 3️⃣ Gerar documento fiscal
    service = DocumentoFiscalService()
    documento = service.criar_documento(
        empresa=empresa,
        tipo_documento='REC',
        cliente=cliente,
        usuario=vendedor.user,
        linhas=[{
            'produto': item.get('produto'),
            'servico': item.get('servico'),
            'quantidade': item['quantidade'],
            'preco_unitario': item['preco_unitario'],
            'desconto': item.get('desconto_item', Decimal('0.00')),
            'iva_valor': (item['preco_unitario'] * item['quantidade'] - item.get('desconto_item', Decimal('0.00'))) * getattr(item.get('taxa_iva', None), 'tax_percentage', 0) / Decimal('100.00'),
        } for item in itens_data],
        dados_extra={
            'data_emissao': timezone.now(),
            'valor_total': recibo.total,
            'numero': gerar_numero_documento(empresa, 'REC'),  # Gera número do recibo
        },
    )

    recibo.numero_recibo = documento.numero
    recibo.hash_documento = documento.hash_documento
    recibo.atcud = documento.atcud
    recibo.save(update_fields=['numero_recibo', 'hash_documento', 'atcud'])

    return recibo



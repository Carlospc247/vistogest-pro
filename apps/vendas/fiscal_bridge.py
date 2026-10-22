# apps/vendas/fiscal_bridge.py
"""Ponte transaccional entre os documentos comerciais de Vendas e Fiscal.

Os modelos de Vendas são criados primeiro porque os seus itens dependem do
registo pai. Só depois de os itens estarem persistidos este serviço gera as
linhas fiscais, reserva o número oficial e confirma o DocumentoFiscal.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal, DocumentoFiscalLinha, TaxaIVAAGT
from apps.fiscal.services import DocumentoFiscalService
from apps.fiscal.services.utils import FiscalServiceError

CENTIMO = Decimal("0.01")

NUMERO_FIELD_BY_CLASS = {
    "Venda": "numero_documento",
    "FaturaCredito": "numero_documento",
    "FaturaGenerica": "numero_documento",
    "FaturaAutofacturacao": "numero_documento",
    "FaturaProforma": "numero_documento",
    "Recibo": "numero_recibo",
    "NotaCredito": "numero_nota",
    "NotaDebito": "numero_nota",
    "DocumentoTransporte": "numero_documento",
}

TIPO_POR_CLASSE = {
    "Venda": "FR",
    "FaturaCredito": "FT",
    "FaturaGenerica": "GF",
    "FaturaAutofacturacao": "AF",
    "FaturaProforma": "FP",
    "Recibo": "RC",
    "NotaCredito": "NC",
    "NotaDebito": "ND",
    "DocumentoTransporte": "DT",
}

def _date_field(value):
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    if isinstance(value, date):
        return value
    return timezone.localdate()

def _decimal(value):
    try:
        return Decimal(str(value or 0)).quantize(CENTIMO, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise ValidationError("Valor monetário inválido ao preparar o documento fiscal.") from exc

def _total_origem(origem):
    if origem.__class__.__name__ == "Recibo":
        return _decimal(getattr(origem, "valor_pago", 0))
    return _decimal(getattr(origem, "total", 0))

def _obter_items(origem):
    if origem.__class__.__name__ == "DocumentoTransporte":
        # GT/DT é documento de movimentação; os seus itens não são linhas de factura.
        return []
    rel = getattr(origem, "itens", None)
    if rel is None:
        return []
    try:
        return list(rel.select_related("produto", "servico", "taxa_iva").all())
    except (AttributeError, TypeError):
        return list(rel.all())

def _taxa_do_item(item):
    taxa = getattr(item, "taxa_iva", None)
    if taxa is not None:
        return taxa

    percentual = getattr(item, "iva_percentual", None)
    if percentual is None:
        percentual = Decimal("0.00")
    try:
        percentual = Decimal(str(percentual)).quantize(CENTIMO)
    except Exception as exc:
        raise ValidationError("Não foi possível determinar a taxa de IVA de uma linha.") from exc

    taxas = TaxaIVAAGT.objects.filter(ativo=True, tax_percentage=percentual).order_by("tax_type", "tax_code", "pk")
    taxa = taxas.first()
    if taxa is None:
        raise ValidationError(
            f"Não existe uma taxa fiscal activa configurada para {percentual}% . "
            "Configure a TaxaIVAAGT e associe-a ao item antes de emitir o documento."
        )
    return taxa

def _valor_item(item, *nomes, default=None):
    for nome in nomes:
        valor = getattr(item, nome, None)
        if valor is not None:
            return valor
    return default

def _dados_item(item, indice, origem):
    produto = getattr(item, "produto", None)
    servico = getattr(item, "servico", None)
    quantidade = _valor_item(item, "quantidade", "quantidade_creditada", "quantidade_enviada", default=1)
    preco = _valor_item(item, "preco_unitario", "valor_unitario_credito", "valor_unitario", default=0)
    try:
        quantidade = Decimal(str(quantidade))
        preco = Decimal(str(preco))
    except Exception as exc:
        raise ValidationError(f"Quantidade ou preço inválido na linha {indice}.") from exc
    if not quantidade.is_finite() or quantidade <= 0:
        raise ValidationError(f"A quantidade da linha {indice} deve ser superior a zero.")
    if not preco.is_finite() or preco < 0:
        raise ValidationError(f"O preço da linha {indice} não pode ser negativo.")

    if produto:
        descricao = (
            getattr(item, "nome_item", None)
            or getattr(item, "nome_produto", None)
            or getattr(produto, "nome_produto", None)
            or str(produto)
        )
        codigo = (
            getattr(produto, "codigo_interno", None)
            or getattr(produto, "codigo", None)
            or getattr(produto, "sku", None)
            or f"PROD-{produto.pk}"
        )
        unidade = getattr(produto, "unidade_medida", None) or "UN"
    elif servico:
        descricao = (
            getattr(item, "nome_item", None)
            or getattr(item, "nome_servico", None)
            or getattr(servico, "nome", None)
            or str(servico)
        )
        codigo = (
            getattr(servico, "codigo_interno", None)
            or getattr(servico, "codigo", None)
            or f"SERV-{servico.pk}"
        )
        unidade = getattr(servico, "unidade_medida", None) or "UN"
    else:
        descricao = (
            getattr(item, "nome_item", None)
            or getattr(item, "descricao_item", None)
            or getattr(item, "descricao_produto", None)
            or f"Item {indice}"
        )
        codigo = f"ITEM-{indice}"
        unidade = "UN"

    taxa = _taxa_do_item(item)
    # ItemVenda guarda desconto por unidade; ItemFatura/ItemProforma guardam
    # desconto total da linha. As notas de crédito/débito não têm esse campo.
    desconto = _valor_item(item, "desconto_item", default=0) or 0
    if item.__class__.__name__ == "ItemVenda":
        desconto = Decimal(str(desconto)) * quantidade
    else:
        desconto = Decimal(str(desconto))
    desconto = _decimal(desconto)
    bruto = (quantidade * preco).quantize(CENTIMO, rounding=ROUND_HALF_UP)
    if desconto < 0 or desconto > bruto:
        raise ValidationError(f"O desconto da linha {indice} é inválido ou excede o valor bruto.")

    return {
        "item": item,
        "produto": produto,
        "codigo_produto": str(codigo)[:50],
        "descricao": str(descricao)[:200],
        "unidade": str(unidade)[:10],
        "quantidade": quantidade,
        "preco_unitario": preco,
        "desconto_base": desconto,
        "bruto": bruto,
        "taxa_iva": taxa,
    }

def _distribuir_desconto_extra(linhas, desconto_extra):
    """Distribui desconto de cabeçalho não reflectido nos itens, ao cêntimo."""
    desconto_extra = _decimal(desconto_extra)
    if desconto_extra <= 0 or not linhas:
        return [Decimal("0.00") for _ in linhas]
    bruto_total = sum((l["bruto"] for l in linhas), Decimal("0.00"))
    if bruto_total <= 0 or desconto_extra > bruto_total:
        raise ValidationError("O desconto global do documento excede a base tributável.")
    total_centimos = int((desconto_extra * 100).to_integral_value(rounding=ROUND_HALF_UP))
    restante = total_centimos
    alocacoes = []
    for i, linha in enumerate(linhas):
        if i == len(linhas) - 1:
            # A última linha recebe o resto para que a soma seja exactamente
            # igual ao desconto do cabeçalho, sem acumular diferenças de arredondamento.
            centimos = restante
        else:
            fracao = linha["bruto"] / bruto_total
            centimos = int((Decimal(total_centimos) * fracao).to_integral_value(rounding=ROUND_HALF_UP))
            centimos = max(0, min(centimos, restante))
        alocacao = (Decimal(centimos) / Decimal("100")).quantize(CENTIMO)
        alocacoes.append(alocacao)
        restante -= centimos
    return alocacoes

def _construir_linhas_fiscais(origem, items):
    if not items:
        return []
    linhas = [_dados_item(item, i, origem) for i, item in enumerate(items, start=1)]
    desconto_itens = sum((l["desconto_base"] for l in linhas), Decimal("0.00"))
    desconto_cabecalho = _decimal(getattr(origem, "desconto_valor", 0))
    # Em Vendas/Proforma/FaturaCredito, desconto_valor é frequentemente o
    # total dos descontos de linha. Só distribuímos a diferença excedente.
    desconto_extra = max(Decimal("0.00"), desconto_cabecalho - desconto_itens)
    alocacoes = _distribuir_desconto_extra(linhas, desconto_extra)

    payload = []
    for i, (linha, extra) in enumerate(zip(linhas, alocacoes), start=1):
        desconto_total = (linha["desconto_base"] + extra).quantize(CENTIMO)
        if desconto_total > linha["bruto"]:
            raise ValidationError(f"O desconto atribuído à linha {i} excede o valor bruto.")
        item = linha["item"]
        operation_type = getattr(item, "operation_type", None)
        if not operation_type:
            if item.__class__.__name__ == "ItemNotaCredito":
                operation_type = "RD"
            elif item.__class__.__name__ == "ItemNotaDebito":
                operation_type = "QT"
            else:
                operation_type = "TB" if linha["produto"] else "SE"
        payload.append({
            "numero_linha": i,
            "produto": linha["produto"],
            "codigo_produto": linha["codigo_produto"],
            "descricao": linha["descricao"],
            "unidade": linha["unidade"],
            "quantidade": linha["quantidade"],
            "preco_unitario": linha["preco_unitario"],
            "valor_desconto_linha": desconto_total,
            "taxa_iva": linha["taxa_iva"],
            "operation_type": operation_type,
        })
    return payload

def _obter_usuario(origem, usuario):
    if usuario is not None:
        return usuario
    vendedor = getattr(origem, "vendedor", None)
    if vendedor is not None:
        utilizador = getattr(vendedor, "usuario", None)
        if utilizador is not None:
            return utilizador
    for nome in ("emitida_por", "usuario_criacao", "emitido_por"):
        utilizador = getattr(origem, nome, None)
        if utilizador is not None:
            return utilizador
    raise ValidationError("É necessário indicar o utilizador responsável pela emissão fiscal.")

def _campos_cabecalho(origem, tipo_documento, linhas_payload):
    total = _total_origem(origem)
    if linhas_payload:
        # Serviço recalcula a partir das linhas; estes valores são ignorados
        # por DocumentoFiscalService quando recebe linhas.
        extras = {
            "data_emissao": _date_field(
                getattr(origem, "data_venda", None)
                or getattr(origem, "data_fatura", None)
                or getattr(origem, "data_proforma", None)
                or getattr(origem, "data_nota", None)
                or getattr(origem, "data_documento", None)
                or timezone.now()
            ),
            "observacoes": getattr(origem, "observacoes", "") or "",
        }
        data_vencimento = getattr(origem, "data_vencimento", None)
        if data_vencimento is not None:
            extras["data_vencimento"] = _date_field(data_vencimento)
        return extras

    # Para recibos e documentos de transporte sem linhas de factura, os
    # totais precisam de ser coerentes já na primeira gravação fiscal.
    return {
        "data_emissao": _date_field(
            getattr(origem, "data_recibo", None)
            or getattr(origem, "data_documento", None)
            or getattr(origem, "data_nota", None)
            or timezone.now()
        ),
        "observacoes": getattr(origem, "observacoes", "") or "",
        "valor_base": total,
        "valor_iva": Decimal("0.00"),
        "valor_desconto": Decimal("0.00"),
        "valor_retencao": Decimal("0.00"),
        "valor_total": total,
    }

def _atualizar_caches_origem(origem, documento):
    model = origem.__class__
    numero_field = NUMERO_FIELD_BY_CLASS.get(model.__name__)
    if not numero_field:
        raise ValidationError(f"Modelo comercial sem campo de número configurado: {model.__name__}.")

    updates = {
        "documento_fiscal_id": documento.pk,
        numero_field: documento.numero_documento,
        # Os campos comerciais admitem NULL: não persistir string vazia num
        # campo unique, pois isso pode bloquear documentos antigos sem hash.
        "hash_documento": documento.hash_documento or None,
        "atcud": documento.atcud or None,
    }
    field_names = {f.name for f in model._meta.concrete_fields}
    updates = {k: v for k, v in updates.items() if k in field_names or k.endswith("_id") and k[:-3] in field_names}

    # Mantém os totais comerciais sincronizados com a fonte fiscal de verdade.
    if "subtotal" in field_names:
        updates["subtotal"] = documento.valor_base
    if "iva_valor" in field_names:
        updates["iva_valor"] = documento.valor_iva
    if "desconto_valor" in field_names:
        updates["desconto_valor"] = documento.valor_desconto
    if "total" in field_names:
        updates["total"] = documento.valor_total
    if model.__name__ == "Recibo":
        updates["valor_pago"] = documento.valor_total

    model.objects.filter(pk=origem.pk).update(**updates)
    for nome, valor in updates.items():
        if nome.endswith("_id"):
            continue
        if hasattr(origem, nome):
            setattr(origem, nome, valor)
    origem.documento_fiscal = documento
    origem.numero_documento = getattr(origem, "numero_documento", None) or documento.numero_documento
    if hasattr(origem, "numero_nota"):
        origem.numero_nota = documento.numero_documento
    if hasattr(origem, "numero_recibo"):
        origem.numero_recibo = documento.numero_documento
    origem.hash_documento = documento.hash_documento or None
    origem.atcud = documento.atcud or None

@transaction.atomic
def emitir_documento_fiscal(origem, usuario=None, tipo_documento=None):
    """Cria/sincroniza e confirma o documento fiscal associado a uma origem comercial."""
    if not getattr(origem, "pk", None):
        raise ValidationError("Guarde o documento comercial antes de o emitir fiscalmente.")

    usuario = _obter_usuario(origem, usuario)
    tipo_documento = tipo_documento or TIPO_POR_CLASSE.get(origem.__class__.__name__)
    if not tipo_documento:
        raise ValidationError(f"Tipo fiscal não definido para {origem.__class__.__name__}.")

    empresa = getattr(connection, "tenant", None)
    if empresa is None or getattr(empresa, "schema_name", "public") == "public":
        raise ValidationError("A emissão fiscal só pode ocorrer dentro do schema de uma empresa.")

    nome_modelo = origem.__class__.__name__
    items = _obter_items(origem)
    if nome_modelo in {"Venda", "FaturaCredito", "FaturaGenerica", "FaturaAutofacturacao", "FaturaProforma", "NotaCredito", "NotaDebito"} and not items:
        raise ValidationError("Não é possível emitir o documento fiscal sem itens.")
    linhas_payload = _construir_linhas_fiscais(origem, items)
    extras = _campos_cabecalho(origem, tipo_documento, linhas_payload)

    documento = getattr(origem, "documento_fiscal", None)
    if documento is None:
        documento = DocumentoFiscalService.criar_documento(
            empresa=empresa,
            tipo_documento=tipo_documento,
            usuario=usuario,
            cliente=getattr(origem, "cliente", None) or getattr(origem, "destinatario_cliente", None),
            serie="A",
            dados_extra=extras,
            linhas=linhas_payload,
        )
    else:
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        if documento.status != "draft":
            if documento.status in {"confirmed", "posted", "paid"} and documento.linhas.exists():
                _atualizar_caches_origem(origem, documento)
                return documento
            raise ValidationError(
                "O documento fiscal associado já foi emitido e não pode ser reconstruído. "
                "Use o procedimento fiscal de rectificação."
            )

        # Documento draft de uma versão antiga: reconstruir as linhas sem
        # reservar um segundo número fiscal.
        documento.linhas.all().delete()
        if linhas_payload:
            documento.valor_base = Decimal("0.00")
            documento.valor_iva = Decimal("0.00")
            documento.valor_desconto = Decimal("0.00")
            documento.valor_retencao = Decimal("0.00")
            documento.valor_total = Decimal("0.00")
        else:
            for campo in ("valor_base", "valor_iva", "valor_desconto", "valor_retencao", "valor_total"):
                setattr(documento, campo, extras.get(campo, Decimal("0.00")))
        documento.data_emissao = extras.get("data_emissao", documento.data_emissao)
        documento.observacoes = extras.get("observacoes", documento.observacoes)
        documento.save(
            _skip_immutability_check=True,
            update_fields=["valor_base", "valor_iva", "valor_desconto", "valor_retencao", "valor_total", "data_emissao", "observacoes", "updated_at"],
        )
        for payload in linhas_payload:
            dados_linha = dict(payload)
            dados_linha["documento"] = documento
            DocumentoFiscalLinha.objects.create(**dados_linha)

    documento.refresh_from_db()
    documento.full_clean()
    if documento.status == "draft":
        documento = DocumentoFiscalService.emitir(documento, usuario)
    documento.refresh_from_db()
    _atualizar_caches_origem(origem, documento)
    return documento

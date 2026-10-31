# apps/fiscal/services/agt_payload_builder.py
"""Construção explícita do envelope ``registarFactura`` para AGT v2.0.

Este módulo não inventa dados fiscais: quando os dados persistidos são
insuficientes ou incompatíveis com o contrato AGT, levanta AGTPayloadBuildError.

Importante sobre reenvios: cada build novo é uma nova preparação. Depois de um
pedido cujo resultado de rede seja desconhecido, não se deve reconstruir o
payload; deve reutilizar-se o envelope exacto que foi capturado/persistido pelo
serviço de submissão, incluindo submissionUUID e assinaturas.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP
from typing import Any

from django.conf import settings
from django.db import connection
from django.utils import timezone

logger = logging.getLogger("fiscal.agt_payload_builder")

# Lista de tipos documentais publicada no serviço AGT registarFactura v2.0.
AGT_DOCUMENT_TYPES = frozenset({
    "FA", "FT", "FR", "FG", "GF", "AC", "AR", "TV", "RC", "RG",
    "RE", "ND", "NC", "AF", "RP", "RA", "CS", "LD",
})
# Na versão 2.0, só AR e RG usam paymentReceipt e não enviam lines.
AGT_RECEIPT_TYPES = frozenset({"AR", "RG"})
AGT_CREDIT_NOTE_TYPES = frozenset({"NC"})
AGT_OPERATION_TYPES = frozenset({
    "SE", "SS", "STP", "SR", "SIF", "SHS", "ST", "SG", "TB", "AS", "QT", "RD",
})
AGT_WITHHOLDING_TYPES = frozenset({"IRT", "II", "IS", "IVA", "IP", "IAC", "OU", "IRPC", "IRPS", "CFQA"})
AGT_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
AGT_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
AGT_EXEMPTION_RE = re.compile(r"^[A-Z0-9]{3}$")

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


class AGTPayloadBuildError(ValueError):
    """Dados em falta ou incompatíveis impedem a construção segura do payload AGT."""


def _d(value: Any, field_name: str) -> Decimal:
    """Converte um número em Decimal, recusando vazio, NaN e infinito."""
    if value is None or value == "":
        raise AGTPayloadBuildError(f"Campo numérico obrigatório sem valor: {field_name}.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AGTPayloadBuildError(f"Valor numérico inválido em {field_name}.") from exc
    if not result.is_finite():
        raise AGTPayloadBuildError(f"Valor numérico não finito em {field_name}.")
    return result


def _num(
    value: Decimal,
    *,
    rounding=ROUND_HALF_UP,
    places: int | None = 2,
) -> int | float:
    """Converte Decimal para número JSON.

    Montantes monetários usam duas casas por defeito. Quantidades e preços
    unitários podem usar ``places=None`` para não serem truncados a cêntimos.
    """
    value = _d(value, "valor JSON")
    if places is not None:
        quantum = Decimal("1").scaleb(-places)
        value = value.quantize(quantum, rounding=rounding)
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _money(value: Decimal, *, rounding=ROUND_HALF_UP) -> Decimal:
    return _d(value, "montante").quantize(CENTAVO, rounding=rounding)


def _positive_number(value: Decimal, name: str) -> Decimal:
    if value < ZERO:
        raise AGTPayloadBuildError(f"{name} não pode ser negativo.")
    return value


def _metadata(documento) -> dict:
    value = getattr(documento, "metadados", {}) or {}
    if not isinstance(value, dict):
        raise AGTPayloadBuildError("DocumentoFiscal.metadados deve ser um objecto JSON.")
    return value


def _required_text(value, field_name: str, *, max_length: int | None = None, min_length: int = 1) -> str:
    result = str(value or "").strip()
    if len(result) < min_length:
        raise AGTPayloadBuildError(f"Campo obrigatório em falta ou demasiado curto: {field_name}.")
    if max_length is not None and len(result) > max_length:
        raise AGTPayloadBuildError(f"{field_name} excede {max_length} caracteres.")
    return result


def _date_iso(value, field_name: str) -> str:
    """Serializa campos date/datetime como YYYY-MM-DD, conforme a AGT."""
    if isinstance(value, datetime):
        # data_emissao é uma data fiscal local. Se for datetime aware, converte
        # para o fuso horário Django activo antes de retirar a parte da data.
        if timezone.is_aware(value):
            value = timezone.localtime(value).date()
        else:
            value = value.date()
    if not isinstance(value, date):
        raise AGTPayloadBuildError(f"{field_name} tem de ser uma data válida.")
    return value.isoformat()


def _company_nif_and_name():
    from apps.empresas.services import obter_empresa_do_schema

    schema = getattr(connection, "schema_name", "public")
    public_schema = getattr(settings, "PUBLIC_SCHEMA_NAME", "public") or "public"
    if not schema or schema == public_schema:
        raise AGTPayloadBuildError("A submissão AGT só pode ocorrer no schema de um tenant.")
    try:
        empresa = obter_empresa_do_schema()
    except Exception as exc:
        raise AGTPayloadBuildError("Não foi possível obter a Empresa do tenant activo.") from exc
    nif = _required_text(getattr(empresa, "nif", ""), "Empresa.nif", max_length=15)
    nome = (
        getattr(empresa, "razao_social", None)
        or getattr(empresa, "nome", None)
        or getattr(empresa, "nome_fantasia", None)
    )
    return empresa, nif, _required_text(nome, "nome/denominação da Empresa", max_length=200)


def _get_lines(documento):
    try:
        return list(documento.linhas.all().order_by("numero_linha", "pk"))
    except Exception as exc:
        raise AGTPayloadBuildError("Não foi possível ler as linhas de DocumentoFiscal.") from exc


def _tax_node(linha) -> tuple[dict, Decimal]:
    """Cria o nó de imposto e devolve exactamente o imposto serializado."""
    taxa = getattr(linha, "taxa_iva", None)
    if taxa is None:
        raise AGTPayloadBuildError(f"Linha {getattr(linha, 'numero_linha', '?')}: falta TaxaIVAAGT.")

    linha_no = getattr(linha, "numero_linha", "?")
    tipo = str(getattr(taxa, "tax_type", "") or "").strip().upper()
    codigo = str(getattr(taxa, "tax_code", "") or "").strip().upper()
    percentagem = _d(getattr(taxa, "tax_percentage", None), f"linha {linha_no}.tax_percentage")
    if percentagem < ZERO:
        raise AGTPayloadBuildError(f"Linha {linha_no}: taxPercentage não pode ser negativo.")
    motivo = str(getattr(taxa, "exemption_reason", "") or "").strip().upper()
    pais = str(getattr(taxa, "codigo_pais", "AO") or "AO").strip().upper()

    if not (AGT_COUNTRY_RE.fullmatch(pais) or pais == "AO-CAB"):
        raise AGTPayloadBuildError(
            f"Linha {linha_no}: taxCountryRegion inválido {pais!r}; use código ISO de 2 letras ou AO-CAB."
        )

    payload: dict[str, Any] = {"taxType": tipo, "taxCountryRegion": pais}
    valor: Decimal

    # NS é um tipo fiscal próprio em AGT v2.0. Não converter silenciosamente
    # taxCode=NS/NA de uma taxa IVA para NS: isso esconde dados contraditórios.
    if tipo == "NS":
        if codigo not in {"", "NS", "NA"}:
            raise AGTPayloadBuildError(
                f"Linha {linha_no}: taxType=NS não admite taxCode={codigo!r} no payload AGT v2.0."
            )
        if percentagem != ZERO:
            raise AGTPayloadBuildError(f"Linha {linha_no}: taxPercentage tem de ser 0 para taxType=NS.")
        if not AGT_EXEMPTION_RE.fullmatch(motivo):
            raise AGTPayloadBuildError(
                f"Linha {linha_no}: taxType=NS exige taxExemptionCode de 3 caracteres (código fiscal)."
            )
        payload["taxPercentage"] = 0
        payload["taxExemptionCode"] = motivo
        return payload, ZERO

    if codigo in {"NS", "NA"}:
        raise AGTPayloadBuildError(
            f"Linha {linha_no}: taxCode={codigo!r} é incompatível com taxType={tipo!r}; "
            "corrija o cadastro fiscal em vez de converter automaticamente para NS."
        )

    if tipo == "IVA":
        if codigo not in {"NOR", "INT", "RED", "ISE", "OUT"}:
            raise AGTPayloadBuildError(f"Linha {linha_no}: taxCode IVA inválido: {codigo!r}.")
        raw_valor = getattr(linha, "valor_iva_linha", None)
        if raw_valor is None:
            raise AGTPayloadBuildError(f"Linha {linha_no}: falta valor_iva_linha persistido.")
        valor = _positive_number(_d(raw_valor, f"linha {linha_no}.valor_iva_linha"), "Imposto da linha")
    elif tipo == "CEOC":
        # A AGT v2.0 define CEOC, mas o TaxaIVAAGT actual do projecto usa
        # max_length=3 e não tem esta escolha. Não é seguro aceitar um valor
        # que o modelo/BD não consegue persistir correctamente.
        raise AGTPayloadBuildError(
            f"Linha {linha_no}: AGT v2.0 suporta CEOC, mas TaxaIVAAGT ainda não o suporta "
            "(tax_type max_length=3/choices). Actualize modelo e migração antes de usar CEOC."
        )
    elif tipo in {"IS", "IEC"}:
        if tipo == "IS" and codigo == "ISE":
            pass
        # Para IS/IEC, códigos de verba/código pautal são definidos nos anexos
        # AGT; não se valida uma lista incompleta neste construtor.
        aliases = (
            "valor_imposto_linha", "valor_selo_linha", "valor_iec_linha",
            "valor_ceoc_linha", "valor_imposto",
        )
        raw_valor = next(
            (getattr(linha, attr) for attr in aliases if getattr(linha, attr, None) is not None),
            None,
        )
        if codigo == "ISE":
            if not AGT_EXEMPTION_RE.fullmatch(motivo):
                raise AGTPayloadBuildError(
                    f"Linha {linha_no}: taxCode=ISE exige taxExemptionCode de 3 caracteres."
                )
            if percentagem != ZERO:
                raise AGTPayloadBuildError(f"Linha {linha_no}: taxPercentage tem de ser 0 para imposto isento.")
            valor = ZERO if raw_valor is None else _d(raw_valor, f"linha {linha_no}.imposto")
        else:
            if raw_valor is None:
                raise AGTPayloadBuildError(
                    f"Linha {linha_no}: o modelo actual não tem montante persistido de {tipo}. "
                    "Acrescente o campo/serviço fiscal correspondente antes de submeter este documento."
                )
            valor = _d(raw_valor, f"linha {linha_no}.imposto")
            # Se a verba de IS usa um montante fixo, esse valor tem de ser
            # persistido explicitamente; não se deduz do taxPercentage.
            if tipo == "IS":
                raw_tax_amount = next(
                    (
                        getattr(taxa, attr)
                        for attr in ("tax_amount", "valor_fixo", "montante_fixo")
                        if getattr(taxa, attr, None) is not None
                    ),
                    None,
                )
                if raw_tax_amount is not None:
                    tax_amount = _positive_number(_d(raw_tax_amount, f"linha {linha_no}.taxAmount"), "taxAmount")
                    payload["taxAmount"] = _num(tax_amount, places=None)
        valor = _positive_number(valor, f"Imposto {tipo} da linha")
    else:
        raise AGTPayloadBuildError(f"Linha {linha_no}: taxType AGT desconhecido: {tipo!r}.")

    if codigo:
        payload["taxCode"] = codigo
    if codigo == "ISE":
        if not AGT_EXEMPTION_RE.fullmatch(motivo):
            raise AGTPayloadBuildError(
                f"Linha {linha_no}: taxCode=ISE exige taxExemptionCode de 3 caracteres."
            )
        if percentagem != ZERO:
            raise AGTPayloadBuildError(f"Linha {linha_no}: taxPercentage tem de ser 0 para taxCode=ISE.")
        if valor != ZERO:
            raise AGTPayloadBuildError(f"Linha {linha_no}: imposto isento não pode ter contribuição positiva.")
    payload["taxPercentage"] = _num(percentagem, places=None)

    # O total tem de somar exactamente o valor enviado em taxContribution, já
    # arredondado por excesso por linha conforme as regras publicadas pela AGT.
    valor_serializado = _money(valor, rounding=ROUND_CEILING)
    if tipo in {"IVA", "IS", "IEC"}:
        payload["taxContribution"] = _num(valor_serializado)
    return payload, valor_serializado


def _build_line(documento, linha, index: int) -> tuple[dict, Decimal, Decimal]:
    codigo = _required_text(getattr(linha, "codigo_produto", ""), f"linha {index}.codigo_produto", max_length=60)
    descricao = _required_text(getattr(linha, "descricao", ""), f"linha {index}.descricao", max_length=200)
    unidade = _required_text(getattr(linha, "unidade", ""), f"linha {index}.unidade", max_length=20)
    operacao = _required_text(getattr(linha, "operation_type", ""), f"linha {index}.operation_type", max_length=3).upper()
    if operacao not in AGT_OPERATION_TYPES:
        raise AGTPayloadBuildError(f"Linha {index}: operationType inválido para AGT v2.0: {operacao!r}.")

    quantidade = _positive_number(_d(getattr(linha, "quantidade", None), f"linha {index}.quantidade"), "Quantidade")
    if quantidade <= ZERO:
        raise AGTPayloadBuildError(f"Linha {index}: quantidade deve ser superior a zero.")
    preco_base = _positive_number(
        _d(getattr(linha, "preco_unitario", None), f"linha {index}.preco_unitario"),
        "Preço unitário base",
    )
    desconto = _positive_number(
        _d(getattr(linha, "valor_desconto_linha", ZERO) or ZERO, f"linha {index}.valor_desconto_linha"),
        "Desconto",
    )
    liquido = _positive_number(
        _d(getattr(linha, "valor_liquido", None), f"linha {index}.valor_liquido"),
        "Valor líquido",
    )

    # O valor líquido persistido deve corresponder ao preço base x quantidade
    # menos desconto. Tolerância de 1 cêntimo para arredondamentos da aplicação.
    calculado = (preco_base * quantidade - desconto).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    liquido_centavos = liquido.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if abs(calculado - liquido_centavos) > CENTAVO:
        raise AGTPayloadBuildError(
            f"Linha {index}: preço base × quantidade − desconto ({calculado}) não coincide com "
            f"valor_liquido ({liquido_centavos}); reveja o cálculo persistido."
        )
    if desconto > (preco_base * quantidade) + CENTAVO:
        raise AGTPayloadBuildError(f"Linha {index}: desconto é superior ao valor bruto da linha.")

    operation_date = getattr(documento, "data_operacao", None)
    node: dict[str, Any] = {
        "lineNumber": index,
        "operationType": operacao,
        "productCode": codigo,
        "productDescription": descricao,
        "quantity": _num(quantidade, places=None),
        "unitOfMeasure": unidade,
        # Não limitar estes dois preços a 2 casas: o modelo aceita 4 casas.
        "unitPriceBase": _num(preco_base, places=None),
        "unitPrice": _num(liquido / quantidade, places=None),
        "settlementAmount": _num(_money(desconto)),
    }
    tipo_documento = str(getattr(documento, "tipo_documento", "") or "").upper()
    if tipo_documento in {"FG", "GF"}:
        if not operation_date:
            raise AGTPayloadBuildError(
                f"Documento {tipo_documento}: data_operacao é obrigatória para a AGT."
            )
        node["operationDate"] = _date_iso(operation_date, "DocumentoFiscal.data_operacao")

    if not getattr(linha, "taxa_iva_id", None) and getattr(linha, "taxa_iva", None) is None:
        raise AGTPayloadBuildError(f"Linha {index}: falta a relação de taxa fiscal.")
    tax_node, tax_amount = _tax_node(linha)
    node["taxes"] = [tax_node]

    # A AGT exige referenceInfo em cada linha de uma NC. No contrato v2.0,
    # NC compara montantes debit/credit; por isso esta linha usa debitAmount.
    if tipo_documento == "NC":
        original = getattr(documento, "documento_original", None)
        reference = _required_text(
            getattr(original, "numero_documento", "") if original else "",
            "NC.documento_original.numero_documento",
            max_length=60,
        )
        metadata = _metadata(documento)
        correction = metadata.get("rectificacao", {}) or {}
        if not isinstance(correction, dict):
            raise AGTPayloadBuildError("metadados['rectificacao'] tem de ser um objecto JSON.")
        reason = str(correction.get("motivo") or getattr(documento, "observacoes", "") or "").strip()[:60]
        node["referenceInfo"] = {"reference": reference}
        if reason:
            node["referenceInfo"]["reason"] = reason
        amount = _money(liquido, rounding=ROUND_CEILING)
        node["debitAmount"] = _num(amount)
    else:
        amount = _money(liquido, rounding=ROUND_DOWN)
        node["creditAmount"] = _num(amount)

    return node, amount, tax_amount


def _validate_withholding_list(documento) -> list[dict]:
    """Valida retenções de um documento normal, sem agregar recibos."""
    metadata = _metadata(documento)
    raw = metadata.get("withholdingTaxList", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise AGTPayloadBuildError("metadados['withholdingTaxList'] tem de ser uma lista.")
    out: list[dict] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise AGTPayloadBuildError(f"Retenção {index}: tem de ser um objecto JSON.")
        tipo = _required_text(
            item.get("withholdingTaxType"), f"retenção {index}.withholdingTaxType", max_length=4
        ).upper()
        if tipo not in AGT_WITHHOLDING_TYPES:
            raise AGTPayloadBuildError(f"Retenção {index}: tipo AGT inválido: {tipo!r}.")
        valor = _positive_number(
            _d(item.get("withholdingTaxAmount"), f"retenção {index}.withholdingTaxAmount"),
            "Retenção",
        )
        node: dict[str, Any] = {"withholdingTaxType": tipo, "withholdingTaxAmount": _num(_money(valor))}
        descricao = str(item.get("withholdingTaxDescription") or "").strip()
        if descricao:
            node["withholdingTaxDescription"] = descricao[:120]
        out.append(node)

    valor_retencao_raw = getattr(documento, "valor_retencao", ZERO)
    valor_retencao = _d(valor_retencao_raw or ZERO, "valor_retencao")
    if valor_retencao < ZERO:
        raise AGTPayloadBuildError("DocumentoFiscal.valor_retencao não pode ser negativo.")
    if valor_retencao > ZERO and not out:
        raise AGTPayloadBuildError(
            "valor_retencao é positivo, mas falta metadados['withholdingTaxList'] com o tipo fiscal e montante."
        )
    soma = sum((_d(x["withholdingTaxAmount"], "retenção") for x in out), ZERO)
    if out and abs(soma - valor_retencao) > CENTAVO:
        raise AGTPayloadBuildError(
            "A soma de withholdingTaxList não coincide com DocumentoFiscal.valor_retencao."
        )
    return out


def _document_rows_totals(documento) -> tuple[Decimal, Decimal, Decimal, list[dict]]:
    lines = _get_lines(documento)
    if not lines:
        raise AGTPayloadBuildError(f"Documento {getattr(documento, 'numero_documento', '?')}: não tem linhas fiscais.")
    nodes: list[dict] = []
    net = ZERO
    tax = ZERO
    for index, line in enumerate(lines, 1):
        node, line_net, line_tax = _build_line(documento, line, index)
        nodes.append(node)
        net += line_net
        # line_tax já contém o taxContribution arredondado que efectivamente
        # será enviado à AGT; não voltar a somar o valor bruto sem arredondar.
        tax += line_tax
    net = _money(net)
    tax = _money(tax)
    gross = _money(net + tax)
    header_total = _d(getattr(documento, "valor_total", None), "DocumentoFiscal.valor_total")
    header_total = _money(header_total)
    if abs(gross - header_total) > CENTAVO:
        raise AGTPayloadBuildError(
            f"Totais inconsistentes em {getattr(documento, 'numero_documento', '?')}: linhas dão {gross}, "
            f"mas DocumentoFiscal.valor_total contém {header_total}. Confirme arredondamentos e impostos por linha."
        )
    return net, tax, gross, nodes


def _receipt_sources(documento):
    """Resolve fontes de AR/RG no schema activo, sem aceitar origens ambíguas."""
    from apps.fiscal.models import DocumentoFiscal

    metadata = _metadata(documento)
    receipt = metadata.get("paymentReceipt") or {}
    if not isinstance(receipt, dict):
        raise AGTPayloadBuildError("metadados['paymentReceipt'] tem de ser um objecto JSON.")
    raw_sources = receipt.get("sourceDocuments")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise AGTPayloadBuildError(
            f"{documento.tipo_documento} exige metadados['paymentReceipt']['sourceDocuments'] "
            "com os documentos fiscais pagos/regularizados."
        )

    result: list[dict] = []
    origins: list[Any] = []
    seen_ids: set[Any] = set()
    net_sum = ZERO
    tax_sum = ZERO
    for index, item in enumerate(raw_sources, 1):
        source_index = index - 1
        if not isinstance(item, dict):
            raise AGTPayloadBuildError(f"sourceDocuments[{source_index}] tem de ser um objecto.")
        debit = item.get("debitAmount")
        credit = item.get("creditAmount")
        if (debit is None) == (credit is None):
            raise AGTPayloadBuildError(
                f"sourceDocuments[{source_index}]: preencher exactamente um de debitAmount ou creditAmount."
            )

        origin = None
        origin_id = item.get("documento_id")
        if origin_id is None:
            origin_id = item.get("documento_origem_id")
        if origin_id not in (None, ""):
            try:
                origin = DocumentoFiscal.objects.get(pk=origin_id)
            except (DocumentoFiscal.DoesNotExist, ValueError, TypeError) as exc:
                raise AGTPayloadBuildError(
                    f"Documento de origem id={origin_id!r} não encontrado neste tenant."
                ) from exc
        else:
            origin_no = str(item.get("OriginatingON") or "").strip()
            if origin_no:
                candidates = list(DocumentoFiscal.objects.filter(numero_documento=origin_no)[:2])
                if len(candidates) == 1:
                    origin = candidates[0]
                elif len(candidates) > 1:
                    raise AGTPayloadBuildError(
                        f"OriginatingON={origin_no!r} não é único neste tenant; informe documento_id."
                    )
        if origin is None:
            raise AGTPayloadBuildError(
                f"sourceDocuments[{source_index}]: o documento de origem tem de ser resolvido no tenant."
            )
        if origin.pk == getattr(documento, "pk", None):
            raise AGTPayloadBuildError("Um recibo não pode indicar a si próprio como documento de origem.")
        if origin.pk in seen_ids:
            raise AGTPayloadBuildError(
                f"Documento de origem {getattr(origin, 'numero_documento', origin.pk)!r} repetido em sourceDocuments."
            )
        seen_ids.add(origin.pk)
        origin_status = str(getattr(origin, "status", "") or "").lower()
        if origin_status not in {"confirmed", "posted", "paid"}:
            raise AGTPayloadBuildError(
                f"Documento de origem {getattr(origin, 'numero_documento', origin.pk)} não está emitido "
                f"(status={origin_status!r})."
            )

        origin_no = _required_text(
            getattr(origin, "numero_documento", ""), "documento origem.numero_documento", max_length=60
        )
        origin_date = getattr(origin, "data_emissao", None)
        if not origin_date:
            raise AGTPayloadBuildError(f"Documento de origem {origin_no} não tem data_emissao.")
        amount = _positive_number(
            _d(debit if debit is not None else credit, f"sourceDocuments[{source_index}].amount"),
            "Valor liquidado",
        )
        field_amount = "debitAmount" if debit is not None else "creditAmount"
        result.append({
            "lineNo": index,
            "sourceDocumentID": {
                "OriginatingON": origin_no,
                "documentDate": _date_iso(origin_date, f"{origin_no}.data_emissao"),
            },
            field_amount: _num(
                _money(amount, rounding=ROUND_CEILING if debit is not None else ROUND_DOWN)
            ),
        })
        origins.append(origin)

        origin_net, origin_tax, _origin_gross, _ = _document_rows_totals(origin)
        sign = Decimal("-1") if str(getattr(origin, "tipo_documento", "")).upper() in AGT_CREDIT_NOTE_TYPES else Decimal("1")
        net_sum += sign * origin_net
        tax_sum += sign * origin_tax

    net_sum = _money(net_sum)
    tax_sum = _money(tax_sum)
    gross = _money(net_sum + tax_sum)
    # Não impor sinal positivo aqui: o contrato v2.0 determina expressamente
    # que uma NC contribui com sinal negativo nos totais agregados do recibo.
    return {"sourceDocuments": result}, net_sum, tax_sum, gross, origins


def _receipt_withholding_list(origins: list[Any]) -> list[dict]:
    """Agrega retenções das origens de AR/RG; NC entra com sinal negativo."""
    totals: dict[str, Decimal] = {}
    descriptions: dict[str, list[str]] = {}
    for origin in origins:
        lines = _validate_withholding_list(origin)
        sign = Decimal("-1") if str(getattr(origin, "tipo_documento", "")).upper() in AGT_CREDIT_NOTE_TYPES else Decimal("1")
        for item in lines:
            tipo = item["withholdingTaxType"]
            amount = _d(item["withholdingTaxAmount"], "withholdingTaxAmount")
            totals[tipo] = totals.get(tipo, ZERO) + sign * amount
            description = str(item.get("withholdingTaxDescription") or "").strip()
            if description:
                descriptions.setdefault(tipo, [])
                if description not in descriptions[tipo]:
                    descriptions[tipo].append(description)

    result: list[dict] = []
    for tipo in sorted(totals):
        amount = _money(totals[tipo])
        if amount == ZERO:
            continue
        item: dict[str, Any] = {
            "withholdingTaxType": tipo,
            "withholdingTaxAmount": _num(amount),
        }
        joined_description = "; ".join(descriptions.get(tipo, []))[:120]
        if joined_description:
            item["withholdingTaxDescription"] = joined_description
        result.append(item)
    return result


def _document_totals(documento, net: Decimal, tax: Decimal, gross: Decimal) -> dict:
    result = {
        "taxPayable": _num(_money(tax)),
        "netTotal": _num(_money(net)),
        "grossTotal": _num(_money(gross)),
    }
    moeda = str(getattr(documento, "moeda", "AOA") or "AOA").strip().upper()
    if moeda != "AOA":
        if not AGT_CURRENCY_RE.fullmatch(moeda):
            raise AGTPayloadBuildError(f"Código de moeda inválido para ISO 4217: {moeda!r}.")
        cambio = _positive_number(_d(getattr(documento, "taxa_cambio", None), "taxa_cambio"), "taxa_cambio")
        if cambio <= ZERO:
            raise AGTPayloadBuildError("Para moeda diferente de AOA, taxa_cambio tem de ser positiva.")
        # AGT v2.0: com currencyCode != AOA, currencyAmount é o contra-valor em Kz.
        contra_valor = _money(gross * cambio, rounding=ROUND_HALF_UP)
        if contra_valor <= ZERO:
            raise AGTPayloadBuildError("currencyAmount deve ser superior a zero para moeda estrangeira.")
        result["currency"] = {
            "currencyCode": moeda,
            "currencyAmount": _num(contra_valor),
            "exchangeRate": _num(cambio, places=None),
        }
    return result


def _validate_software_info(software_info: Any) -> dict:
    if not isinstance(software_info, dict):
        raise AGTPayloadBuildError("AssinaturaSoftwareService.montar_software_info() não devolveu um objecto.")
    detail = software_info.get("softwareInfoDetail")
    if not isinstance(detail, dict):
        raise AGTPayloadBuildError("softwareInfo.softwareInfoDetail tem de ser um objecto.")
    required = {"productId", "productVersion", "softwareValidationNumber", "signatureVersion"}
    missing = sorted(required - set(detail))
    if missing:
        raise AGTPayloadBuildError(
            "softwareInfoDetail incompleto; falta(m): " + ", ".join(missing) +
            ". Actualize AssinaturaSoftwareService e configure os dados reais da certificação AGT."
        )
    for key in ("productId", "productVersion", "softwareValidationNumber"):
        _required_text(detail.get(key), f"softwareInfo.softwareInfoDetail.{key}")
    version = detail.get("signatureVersion")
    # bool é uma subclasse de int em Python; não é válido como versão numérica.
    if isinstance(version, bool) or not isinstance(version, int):
        raise AGTPayloadBuildError(
            "softwareInfoDetail.signatureVersion tem de ser um inteiro configurado conforme a certificação AGT; "
            "não use string nem valor presumido."
        )
    if "jwsSoftwareSignature" not in software_info or not str(software_info.get("jwsSoftwareSignature") or "").strip():
        raise AGTPayloadBuildError("softwareInfo.jwsSoftwareSignature está em falta.")
    return software_info


class AGTPayloadBuilder:
    """Monta um envelope ``registarFactura`` v2.0 para DocumentoFiscal emitido."""

    @classmethod
    def build(cls, documento, *, submission_uuid: str | uuid.UUID | None = None) -> dict:
        from apps.fiscal.models import AssinaturaDigital
        from apps.fiscal.services.assinatura_service import (
            AssinaturaDigitalService,
            AssinaturaSoftwareService,
        )

        schema_version = str(getattr(settings, "AGT_SCHEMA_VERSION", "2.0") or "2.0").strip()
        if schema_version != "2.0":
            raise AGTPayloadBuildError(
                f"Este builder implementa o contrato AGT v2.0; AGT_SCHEMA_VERSION={schema_version!r}."
            )

        tipo = str(getattr(documento, "tipo_documento", "") or "").strip().upper()
        numero = _required_text(
            getattr(documento, "numero_documento", ""), "numero_documento", max_length=60, min_length=8
        )
        if tipo not in AGT_DOCUMENT_TYPES:
            if tipo in {"DT", "FP"}:
                raise AGTPayloadBuildError(
                    f"O tipo {tipo} existe no modelo DocumentoFiscal, mas não consta dos tipos aceites "
                    "pelo serviço AGT registarFactura v2.0."
                )
            raise AGTPayloadBuildError(f"Tipo de documento {tipo!r} não suportado por registarFactura v2.0.")

        status = str(getattr(documento, "status", "") or "").lower()
        if status in {"cancelled", "rectified"}:
            raise AGTPayloadBuildError(f"Documento {numero} está {status!r} e não pode ser submetido como normal.")
        if status not in {"confirmed", "posted", "paid"}:
            raise AGTPayloadBuildError(
                f"Documento {numero} está em estado {status!r}; só documentos emitidos podem ser submetidos."
            )

        _empresa, nif, _nome_emissor = _company_nif_and_name()
        try:
            assinatura = AssinaturaDigital.get_solo()
        except Exception as exc:
            raise AGTPayloadBuildError("Não foi possível obter a configuração AssinaturaDigital deste tenant.") from exc
        if not getattr(assinatura, "esta_configurada", False):
            raise AGTPayloadBuildError("As chaves digitais do contribuinte não estão configuradas neste tenant.")

        # Validar softwareInfo antes de assinar documentos para evitar assinar um
        # documento que depois será recusado por falta de dados do software.
        try:
            software_info = _validate_software_info(AssinaturaSoftwareService.montar_software_info())
        except AGTPayloadBuildError:
            raise
        except Exception as exc:
            raise AGTPayloadBuildError("Não foi possível montar/validar softwareInfo da AGT.") from exc

        metadata = _metadata(documento)
        rejected_no = str(
            metadata.get("rejectedDocumentNo") or metadata.get("agt_rejected_document_no") or ""
        ).strip()
        document_status = str(metadata.get("agt_document_status") or "N").strip().upper()
        if document_status not in {"N", "C"}:
            raise AGTPayloadBuildError("documentStatus tem de ser N ou C conforme a documentação AGT v2.0.")
        if document_status == "C" and not rejected_no:
            raise AGTPayloadBuildError(
                "documentStatus=C exige rejectedDocumentNo do documento previamente rejeitado pela AGT."
            )
        if document_status == "N" and rejected_no:
            logger.warning("rejectedDocumentNo ignorado porque documentStatus=N; documento=%s", numero)
            rejected_no = ""
        if rejected_no:
            rejected_no = _required_text(rejected_no, "rejectedDocumentNo", max_length=60, min_length=8)

        data_emissao = getattr(documento, "data_emissao", None)
        if not data_emissao:
            raise AGTPayloadBuildError(f"Documento {numero} não tem data_emissao.")
        document_date = _date_iso(data_emissao, "DocumentoFiscal.data_emissao")
        cliente_nome = _required_text(getattr(documento, "cliente_nome", ""), "cliente_nome", max_length=200)

        country = str(metadata.get("customerCountry") or metadata.get("customer_country") or "").strip().upper()
        tipo_cliente = str(getattr(documento, "tipo_cliente", "particular") or "particular").strip().lower()
        if not country and tipo_cliente != "nao_residente":
            country = "AO"
        if not AGT_COUNTRY_RE.fullmatch(country):
            raise AGTPayloadBuildError(
                "Falta customerCountry ISO-3166-1-alpha-2 válido; para cliente não residente, "
                "guardar metadados['customerCountry']."
            )
        customer_tax_id = str(
            getattr(documento, "cliente_nif", "") or metadata.get("customerTaxID") or ""
        ).strip()
        if not customer_tax_id:
            if country == "AO":
                # Valor autorizado pela AGT apenas para cliente doméstico sem identificação.
                customer_tax_id = "999999999"
            else:
                raise AGTPayloadBuildError(
                    "Cliente estrangeiro sem NIF/identificador em metadados['customerTaxID']."
                )
        customer_tax_id = _required_text(customer_tax_id, "customerTaxID", max_length=50)

        if tipo in AGT_RECEIPT_TYPES:
            payment_receipt, net, tax, gross, receipt_origins = _receipt_sources(documento)
            lines = None
            withholding = _receipt_withholding_list(receipt_origins)
        else:
            net, tax, gross, lines = _document_rows_totals(documento)
            payment_receipt = None
            receipt_origins = []
            withholding = _validate_withholding_list(documento)

        totals = _document_totals(documento, net, tax, gross)
        document_node: dict[str, Any] = {
            "documentNo": numero,
            "documentStatus": document_status,
            "documentDate": document_date,
            "documentType": tipo,
            "systemEntryDate": timezone.now().isoformat(),
            "customerCountry": country,
            "customerTaxID": customer_tax_id,
            "companyName": cliente_nome,
            "documentTotals": totals,
        }
        if rejected_no:
            document_node["rejectedDocumentNo"] = rejected_no
        eac = str(getattr(documento, "eac_code", "") or "").strip()
        if eac:
            if len(eac) != 5:
                raise AGTPayloadBuildError("eac_code deve conter exactamente 5 caracteres quando preenchido.")
            document_node["eacCode"] = eac
        if lines is not None:
            document_node["lines"] = lines
        if payment_receipt is not None:
            document_node["paymentReceipt"] = payment_receipt
        if withholding:
            document_node["withholdingTaxList"] = withholding

        # Os campos e a ordem da assinatura JWS do documento seguem a AGT.
        assinatura_documento = {
            "documentNo": document_node["documentNo"],
            "taxRegistrationNumber": nif,
            "documentType": document_node["documentType"],
            "documentDate": document_node["documentDate"],
            "customerTaxID": document_node["customerTaxID"],
            "customerCountry": document_node["customerCountry"],
            "companyName": document_node["companyName"],
            "documentTotals": document_node["documentTotals"],
        }
        try:
            document_node["jwsDocumentSignature"] = AssinaturaDigitalService.assinar_documento(assinatura_documento)
        except Exception as exc:
            raise AGTPayloadBuildError(f"Falha ao gerar jwsDocumentSignature para {numero}.") from exc

        if submission_uuid is None:
            submission_uuid_normalized = str(uuid.uuid4())
        else:
            try:
                submission_uuid_normalized = str(uuid.UUID(str(submission_uuid)))
            except (ValueError, TypeError, AttributeError) as exc:
                raise AGTPayloadBuildError("submission_uuid fornecido não é um UUID válido.") from exc

        try:
            request_signature = AssinaturaDigitalService.assinar_requisicao({
                "taxRegistrationNumber": nif,
                "submissionUUID": submission_uuid_normalized,
            })
        except Exception as exc:
            raise AGTPayloadBuildError("Falha ao gerar jwsSignature do envelope AGT.") from exc

        payload = {
            "schemaVersion": schema_version,
            "submissionUUID": submission_uuid_normalized,
            "taxRegistrationNumber": nif,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": software_info,
            "numberOfEntries": 1,
            "documents": [document_node],
            "jwsSignature": request_signature,
        }
        return payload

"""Motor único de numeração fiscal do VistoGest Pro.

Para documentos electrónicos: usa exclusivamente o seriesCode recebido da AGT
(em SerieFiscalAGT), o tipo e o ano correspondentes e o intervalo autorizado.
Para FP/DT, que não integram a lista documentType do endpoint AGT registarFactura,
usa numeração interna separada. A criação/sincronização da série na AGT é outro serviço.

IMPORTANTE: este módulo reserva o número local. O chamador que cria DocumentoFiscal
DEVE manter a reserva e a gravação do documento na mesma transacção (save atómico).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

TIPOS_DOCUMENTO_AGT = frozenset({
    "FA", "FT", "FR", "FG", "GF", "AC", "AR", "TV", "RC", "RG",
    "RE", "ND", "NC", "AF", "RP", "RA", "CS", "LD",
})
TIPOS_DOCUMENTO_INTERNOS = frozenset({"FP", "DT"})
_RE_SERIE_ALFANUMERICA = re.compile(r"^[A-Za-z0-9]{3,60}$")
_RE_INTEIRO_POSITIVO = re.compile(r"^\d+$")


def _normalizar_tipo_documento(valor: str) -> str:
    tipo = str(valor or "").strip().upper()
    if tipo == "REC":
        raise ValidationError(
            "'REC' não é um documentType listado pela AGT. Use 'RC' para Recibo Emitido "
            "ou 'RG' para Outros Recibos, conforme a natureza do recibo."
        )
    if tipo not in TIPOS_DOCUMENTO_AGT and tipo not in TIPOS_DOCUMENTO_INTERNOS:
        raise ValidationError(f"Tipo de documento não suportado pelo motor: {tipo or '(vazio)'}. ")
    return tipo


def _normalizar_serie_solicitada(tipo: str, serie: Optional[str]) -> Optional[str]:
    """Normaliza o argumento legado; 'A' é só placeholder e nunca código AGT."""
    valor = str(serie or "").strip()
    prefixo = f"{tipo} "
    # Tolera argumentos antigos como "FR A" ou "FR FR6325S2C"; o código puro
    # recebido da AGT não deve conter espaços nem '/'.
    while valor.upper().startswith(prefixo.upper()):
        valor = valor[len(prefixo):].strip()
    if not valor or valor.upper() == "A":
        return None
    if any(ch.isspace() for ch in valor) or "/" in valor:
        raise ValidationError(
            f"Série '{serie}' inválida. Passe apenas o seriesCode, sem o tipo documental, "
            "espaços ou barra."
        )
    if len(valor) > 60:
        raise ValidationError("O seriesCode não pode exceder 60 caracteres.")
    return valor


def _obter_ano(data_emissao=None) -> int:
    if data_emissao is None:
        return timezone.localdate().year
    if isinstance(data_emissao, str):
        try:
            data_emissao = date.fromisoformat(data_emissao[:10])
        except ValueError as exc:
            raise ValidationError("Data de emissão inválida para a numeração fiscal.") from exc
    if not isinstance(data_emissao, (date, datetime)):
        raise ValidationError("A data de emissão deve ser date, datetime ou ISO yyyy-mm-dd.")
    return data_emissao.year


def _validar_empresa_tenant(empresa) -> None:
    schema_actual = getattr(connection, "schema_name", "public")
    if schema_actual == "public":
        raise ValidationError("A numeração fiscal tem de ocorrer no schema do tenant, não em public.")
    if empresa is None:
        raise ValidationError("A empresa é obrigatória para gerar o número fiscal.")
    schema_empresa = getattr(empresa, "schema_name", None)
    if not schema_empresa:
        raise ValidationError("A empresa não identifica um schema de tenant válido.")
    if schema_empresa != schema_actual:
        raise ValidationError(
            f"A empresa pertence ao schema '{schema_empresa}', mas o schema activo é '{schema_actual}'."
        )


def _ler_limite(valor, nome: str) -> int:
    texto = str(valor or "").strip()
    if not _RE_INTEIRO_POSITIVO.fullmatch(texto):
        raise ValidationError(
            f"A série AGT não tem {nome} numérico. Sincronize firstDocumentNo/lastDocumentNo "
            "a partir da resposta oficial da AGT antes de emitir."
        )
    numero = int(texto)
    if numero < 1:
        raise ValidationError(f"{nome} tem de ser maior do que zero.")
    return numero


def _validar_codigo_serie(codigo: str, ano: int, indicador_contingencia: str = "N") -> None:
    """Valida as regras publicadas: 3–60 alfanuméricos e ano com 2 ou 4 dígitos."""
    if not _RE_SERIE_ALFANUMERICA.fullmatch(codigo or ""):
        raise ValidationError(
            "O seriesCode AGT deve conter entre 3 e 60 caracteres alfanuméricos, sem espaços ou '/'."
        )
    ano_4, ano_2 = str(ano), str(ano)[-2:]
    if ano_4 not in codigo and ano_2 not in codigo:
        raise ValidationError(
            f"O seriesCode '{codigo}' não contém o ano de emissão {ano} (ou {ano_2}) conforme a regra AGT."
        )
    if str(indicador_contingencia or "N").upper() == "C":
        if f"{ano_4}C" not in codigo.upper() and f"{ano_2}C" not in codigo.upper():
            raise ValidationError(
                "A série marcada como contingência deve conter o ano seguido do indicador C "
                "(por exemplo 25C ou 2025C), conforme a documentação AGT."
            )


def _formatar_numero_documento(tipo: str, codigo_serie: str, sequencial: int) -> str:
    if not codigo_serie or any(ch.isspace() for ch in codigo_serie) or "/" in codigo_serie:
        raise ValidationError("O código da série é inválido para construir o número fiscal.")
    if isinstance(sequencial, bool) or int(sequencial) < 1:
        raise ValidationError("O sequencial deve ser um inteiro positivo.")
    resultado = f"{tipo} {codigo_serie}/{int(sequencial)}"
    # A documentação AGT admite documentNo até 60 caracteres e proíbe zeros à esquerda.
    if len(resultado) < 8 or len(resultado) > 60:
        raise ValidationError(
            f"O documentNo '{resultado}' não respeita o comprimento AGT de 8 a 60 caracteres."
        )
    return resultado


def _gerar_numero_interno(tipo, ano, serie_pedida, ContadorDocumento, DocumentoFiscal) -> dict:
    """Sequência interna para FP/DT; estes códigos não usam série FE da AGT."""
    sufixo = serie_pedida or "A"
    serie_local = f"{ano}{sufixo}"
    with transaction.atomic():
        contador, _ = ContadorDocumento.objects.select_for_update().get_or_create(
            tipo_documento=tipo,
            ano=ano,
            serie=serie_local,
            defaults={"ultimo_numero": 0},
        )
        maior_doc = DocumentoFiscal.objects.filter(
            tipo_documento=tipo, serie=serie_local
        ).aggregate(maior=Max("numero"))["maior"] or 0
        proximo = max(int(contador.ultimo_numero or 0), int(maior_doc)) + 1
        formato = _formatar_numero_documento(tipo, serie_local, proximo)
        contador.ultimo_numero = proximo
        contador.save(update_fields=["ultimo_numero"])
        return {
            "sequencial": proximo,
            "numero": proximo,
            "serie": serie_local,
            "series_code": serie_local,
            "ano": ano,
            "formatado": formato,
        }


@transaction.atomic
def gerar_numero_documento(empresa, tipo_documento, serie="A", data_emissao=None) -> dict:
    """Reserva o próximo número para uma série AGT activa e associada ao tipo/ano.

    Não cria séries AGT. A série tem de ser previamente solicitada à AGT e sincronizada
    em SerieFiscalAGT, incluindo código, método FESF e intervalo autorizado.
    """
    _validar_empresa_tenant(empresa)
    tipo = _normalizar_tipo_documento(tipo_documento)
    ano = _obter_ano(data_emissao)
    serie_pedida = _normalizar_serie_solicitada(tipo, serie)

    # Importações tardias evitam ciclos no carregamento dos modelos Django.
    from apps.fiscal.models import ContadorDocumento, DocumentoFiscal, SerieFiscalAGT

    if tipo in TIPOS_DOCUMENTO_INTERNOS:
        return _gerar_numero_interno(
            tipo, ano, serie_pedida, ContadorDocumento, DocumentoFiscal
        )

    # Para registarFactura electrónica, a série tem de ter sido criada para uso
    # via software (FESF), não pelo portal (FEPC) nem para facturação não electrónica (SF).
    utilizaveis = SerieFiscalAGT.objects.select_for_update().filter(
        document_type=tipo,
        series_year=ano,
        series_status__in=(SerieFiscalAGT.STATUS_ABERTA, SerieFiscalAGT.STATUS_UTILIZACAO),
        invoicing_method=SerieFiscalAGT.METODO_FESF,
    )

    if serie_pedida:
        serie_agt = utilizaveis.filter(series_code=serie_pedida).first()
        if serie_agt is None:
            raise ValidationError(
                f"A série AGT '{serie_pedida}' não está utilizável para {tipo}/{ano} com método FESF. "
                "Confirme o seriesCode, o tipo, o ano e o estado sincronizados a partir da AGT."
            )
    else:
        candidatas = list(utilizaveis.order_by("series_code")[:2])
        if not candidatas:
            raise ValidationError(
                f"Não existe série AGT aberta/em utilização, FESF, para {tipo}/{ano}. "
                "Use solicitarSerie/listarSeries e sincronize SerieFiscalAGT antes de emitir."
            )
        if len(candidatas) > 1:
            raise ValidationError(
                f"Existem várias séries AGT utilizáveis para {tipo}/{ano}. "
                "Indique explicitamente o seriesCode pretendido; não escolha uma série arbitrariamente."
            )
        serie_agt = candidatas[0]

    codigo_serie = str(serie_agt.series_code or "").strip()
    if serie_agt.document_type != tipo or int(serie_agt.series_year) != ano:
        raise ValidationError("A série AGT seleccionada não corresponde ao tipo e ano da emissão.")
    _validar_codigo_serie(codigo_serie, ano, serie_agt.contingency_indicator)

    primeiro = _ler_limite(serie_agt.first_document_no, "firstDocumentNo")
    ultimo_autorizado = _ler_limite(serie_agt.last_document_no, "lastDocumentNo")
    if ultimo_autorizado < primeiro:
        raise ValidationError("O intervalo autorizado da série AGT está invertido.")

    # A linha SerieFiscalAGT é bloqueada acima: serializa as emissões concorrentes
    # da mesma série. O contador local é cache/lock de sequência, não a autoridade da série.
    contador = ContadorDocumento.objects.select_for_update().filter(
        tipo_documento=tipo, ano=ano, serie=codigo_serie
    ).first()
    if contador is None:
        contador = ContadorDocumento.objects.create(
            tipo_documento=tipo,
            ano=ano,
            serie=codigo_serie,
            ultimo_numero=primeiro - 1,
        )

    maior_doc = DocumentoFiscal.objects.filter(
        tipo_documento=tipo, serie=codigo_serie
    ).aggregate(maior=Max("numero"))["maior"] or 0
    ultimo_usado = max(int(contador.ultimo_numero or 0), int(maior_doc), primeiro - 1)
    proximo = ultimo_usado + 1
    if proximo > ultimo_autorizado:
        raise ValidationError(
            f"A série AGT {codigo_serie} esgotou o intervalo autorizado até {ultimo_autorizado}. "
            "Solicite extensão à AGT; não reinicie o contador local."
        )

    formato = _formatar_numero_documento(tipo, codigo_serie, proximo)
    contador.ultimo_numero = proximo
    contador.save(update_fields=["ultimo_numero"])
    if serie_agt.contador_id != contador.pk:
        serie_agt.contador = contador
        serie_agt.save(update_fields=["contador", "updated_at"])

    return {
        "sequencial": proximo,
        "numero": proximo,
        "serie": codigo_serie,
        "series_code": codigo_serie,
        "ano": ano,
        "first_document_no": primeiro,
        "last_document_no": ultimo_autorizado,
        "formatado": formato,
    }

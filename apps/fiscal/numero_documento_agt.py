"""Geração centralizada do número de documento fiscal para VistoGest Pro.

Uso recomendado: guardar em apps/fiscal/services/numero_documento_agt.py.
Para documentos electrónicos AGT, usa exclusivamente uma SerieFiscalAGT activa
registada no tenant e respeita os limites firstDocumentNo/lastDocumentNo.
Documentos internos FP/DT recebem uma sequência local separada.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

logger = logging.getLogger("fiscal.numeracao")

# Tipos identificados na documentação oficial do serviço AGT registarFactura.
TIPOS_DOCUMENTO_AGT = frozenset({
    "FA", "FT", "FR", "FG", "GF", "AC", "AR", "TV", "RC", "RG",
    "RE", "ND", "NC", "AF", "RP", "RA", "CS", "LD",
})

# Documentos internos do sistema: não são tipos documentType do serviço AGT
# registarFactura e, por isso, não devem consumir uma série electrónica AGT.
TIPOS_DOCUMENTO_INTERNOS = frozenset({"FP", "DT"})


def _tipo_documento(valor: str) -> str:
    tipo = str(valor or "").strip().upper()
    if tipo == "REC":
        raise ValidationError(
            "'REC' não é um tipo documentType da AGT. Use 'RC' para Recibo Emitido "
            "ou 'RG' para Outros Recibos, conforme a natureza do documento."
        )
    if tipo not in TIPOS_DOCUMENTO_AGT and tipo not in TIPOS_DOCUMENTO_INTERNOS:
        raise ValidationError(
            f"Tipo de documento '{tipo or '(vazio)'}' não reconhecido para numeração. "
            "Use um tipo AGT suportado ou um tipo interno explicitamente configurado."
        )
    return tipo


def _normalizar_serie_solicitada(tipo: str, serie: Optional[str]) -> Optional[str]:
    """Aceita o código puro da série e corrige prefixos do tipo duplicados.

    O código de série AGT não deve conter espaços nem '/'. O valor histórico
    'A' é tratado como placeholder local e não como série electrónica AGT.
    """
    valor = str(serie or "").strip()
    prefixo = f"{tipo} "
    # Se foi passado por engano "FR FR ABC...", remove somente os prefixos
    # separados por espaço. Um seriesCode AGT, por si, não contém espaços.
    while valor.upper().startswith(prefixo.upper()):
        valor = valor[len(prefixo):].strip()

    if not valor or valor.upper() == "A":
        return None
    if any(ch.isspace() for ch in valor) or "/" in valor:
        raise ValidationError(
            f"Série '{serie}' inválida: passe apenas o código da série, sem o tipo "
            "de documento, espaços ou barra."
        )
    if len(valor) > 60:
        raise ValidationError("O código da série não pode exceder 60 caracteres.")
    return valor


def _ano_da_emissao(data_emissao=None) -> int:
    if data_emissao is None:
        return timezone.localdate().year
    if isinstance(data_emissao, str):
        try:
            data_emissao = date.fromisoformat(data_emissao[:10])
        except ValueError as exc:
            raise ValidationError("Data de emissão inválida para gerar o número fiscal.") from exc
    if not isinstance(data_emissao, (date, datetime)):
        raise ValidationError("A data de emissão deve ser uma data válida.")
    return data_emissao.year


def _limite_numerico(valor, nome: str) -> int:
    texto = str(valor or "").strip()
    if not texto or not re.fullmatch(r"\d+", texto):
        raise ValidationError(
            f"A série fiscal AGT não tem o campo {nome} numérico configurado. "
            "Sincronize firstDocumentNo/lastDocumentNo com a AGT antes de emitir."
        )
    numero = int(texto)
    if numero < 1:
        raise ValidationError(f"O campo {nome} da série AGT deve ser maior que zero.")
    return numero


def _formatar_numero_documento(tipo: str, serie: str, sequencial: int) -> str:
    """Formato: código do tipo + espaço + série + '/' + sequência sem zeros à esquerda."""
    if not serie or any(ch.isspace() for ch in serie) or "/" in serie:
        raise ValidationError("O código da série é inválido para compor numero_documento.")
    if isinstance(sequencial, bool) or int(sequencial) < 1:
        raise ValidationError("O número sequencial deve ser um inteiro positivo.")
    resultado = f"{tipo} {serie}/{int(sequencial)}"
    if len(resultado) > 60:
        raise ValidationError(
            "O número completo excede os 60 caracteres permitidos pela AGT. "
            "Verifique o código da série registada."
        )
    return resultado


def _validar_empresa_tenant(empresa) -> None:
    schema_actual = getattr(connection, "schema_name", "public")
    if schema_actual == "public":
        raise ValidationError("A numeração fiscal deve decorrer no schema do tenant, não em public.")
    if empresa is None:
        raise ValidationError("A empresa é obrigatória para gerar o número do documento fiscal.")
    schema_empresa = getattr(empresa, "schema_name", None)
    if not schema_empresa:
        raise ValidationError(
            "A empresa não identifica um schema de tenant válido para gerar o número fiscal."
        )
    if schema_empresa != schema_actual:
        raise ValidationError(
            f"A empresa pertence ao schema '{schema_empresa}', mas o schema activo é '{schema_actual}'."
        )


def _gerar_numero_interno(tipo: str, ano: int, serie_pedida: Optional[str],
                          ContadorDocumento, DocumentoFiscal) -> dict:
    """Sequência local exclusiva para FP/DT, que não são documentType do endpoint FE."""
    sufixo = serie_pedida or "A"
    # A constraint de DocumentoFiscal não inclui o ano; inclui-se o ano na série
    # local para evitar colisões entre 2026A/1 e 2027A/1.
    serie_local = f"{ano}{sufixo}"
    with transaction.atomic():
        contador, _ = ContadorDocumento.objects.select_for_update().get_or_create(
            tipo_documento=tipo,
            ano=ano,
            serie=serie_local,
            defaults={"ultimo_numero": 0},
        )
        maior_documento = DocumentoFiscal.objects.filter(
            tipo_documento=tipo, serie=serie_local
        ).aggregate(maior=Max("numero"))["maior"] or 0
        proximo = max(int(contador.ultimo_numero or 0), int(maior_documento)) + 1
        contador.ultimo_numero = proximo
        contador.save(update_fields=["ultimo_numero"])
        numero_formatado = _formatar_numero_documento(tipo, serie_local, proximo)
        return {
            "sequencial": proximo,
            "numero": proximo,
            "serie": serie_local,
            "series_code": serie_local,
            "ano": ano,
            "formatado": numero_formatado,
        }


@transaction.atomic
def gerar_numero_documento(empresa, tipo_documento, serie="A", data_emissao=None) -> dict:
    """Reserva o próximo número com transação e bloqueio da série AGT.

    Para tipos electrónicos AGT exige uma SerieFiscalAGT activa e aprovada para
    o tipo/ano do documento. A série é escolhida pelo código explícito; quando
    serie='A' (valor legado/default) é seleccionada automaticamente se existir
    exactamente uma série utilizável para o tipo e ano.

    Retorna sequencial, numero, serie/series_code, ano e formatado. O chamador
    deve persistir também o campo DocumentoFiscal.serie com o código retornado.
    """
    _validar_empresa_tenant(empresa)
    tipo = _tipo_documento(tipo_documento)
    ano = _ano_da_emissao(data_emissao)
    serie_pedida = _normalizar_serie_solicitada(tipo, serie)

    # Importação tardia: evita ciclo durante o carregamento dos modelos Django.
    from apps.fiscal.models import ContadorDocumento, DocumentoFiscal, SerieFiscalAGT

    if tipo in TIPOS_DOCUMENTO_INTERNOS:
        return _gerar_numero_interno(
            tipo, ano, serie_pedida, ContadorDocumento, DocumentoFiscal
        )

    estados_utilizaveis = (
        SerieFiscalAGT.STATUS_ABERTA,
        SerieFiscalAGT.STATUS_UTILIZACAO,
    )
    series_qs = SerieFiscalAGT.objects.select_for_update().filter(
        document_type=tipo,
        series_year=ano,
        series_status__in=estados_utilizaveis,
    )

    if serie_pedida:
        serie_agt = series_qs.filter(series_code=serie_pedida).first()
        if serie_agt is None:
            raise ValidationError(
                f"A série AGT '{serie_pedida}' não está registada/aberta para {tipo} no ano {ano}. "
                "Use o seriesCode devolvido pela AGT e sincronize o estado e o intervalo autorizado."
            )
    else:
        candidatas = list(series_qs.order_by("series_code")[:2])
        if not candidatas:
            raise ValidationError(
                f"Não existe série AGT aberta/em utilização para {tipo} no ano {ano}. "
                "Registe/sincronize a série no serviço solicitarSerie/listarSeries antes de emitir."
            )
        if len(candidatas) > 1:
            raise ValidationError(
                f"Existem várias séries AGT utilizáveis para {tipo}/{ano}. "
                "Indique explicitamente o seriesCode pretendido."
            )
        serie_agt = candidatas[0]

    codigo_serie = str(serie_agt.series_code or "").strip()
    if not codigo_serie or any(ch.isspace() for ch in codigo_serie) or "/" in codigo_serie:
        raise ValidationError("O seriesCode guardado da AGT está vazio ou tem um formato inválido.")
    if serie_agt.document_type != tipo or int(serie_agt.series_year) != ano:
        raise ValidationError("A série AGT seleccionada não corresponde ao tipo/ano da emissão.")

    primeiro = _limite_numerico(serie_agt.first_document_no, "firstDocumentNo")
    ultimo_autorizado = _limite_numerico(serie_agt.last_document_no, "lastDocumentNo")
    if ultimo_autorizado < primeiro:
        raise ValidationError("O intervalo autorizado da série AGT está invertido.")

    # O bloqueio da linha SerieFiscalAGT serializa emissões concorrentes da mesma
    # série, inclusive no caso da primeira criação de ContadorDocumento.
    contador = ContadorDocumento.objects.select_for_update().filter(
        tipo_documento=tipo,
        ano=ano,
        serie=codigo_serie,
    ).first()
    if contador is None:
        contador = ContadorDocumento.objects.create(
            tipo_documento=tipo,
            ano=ano,
            serie=codigo_serie,
            ultimo_numero=primeiro - 1,
        )

    maior_documento = DocumentoFiscal.objects.filter(
        tipo_documento=tipo,
        serie=codigo_serie,
    ).aggregate(maior=Max("numero"))["maior"] or 0
    ultimo_usado = max(int(contador.ultimo_numero or 0), int(maior_documento), primeiro - 1)
    proximo = ultimo_usado + 1

    if proximo > ultimo_autorizado:
        raise ValidationError(
            f"A série AGT {codigo_serie} esgotou o intervalo autorizado: "
            f"último número permitido {ultimo_autorizado}. Solicite extensão de série à AGT."
        )

    # Valida o tamanho/formato antes de reservar o número.
    numero_formatado = _formatar_numero_documento(tipo, codigo_serie, proximo)
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
        "formatado": numero_formatado,
    }

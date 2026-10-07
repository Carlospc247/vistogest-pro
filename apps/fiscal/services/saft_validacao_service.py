# apps/fiscal/services/saft_validacao_service.py
"""
SaftValidacaoService — validação do ficheiro SAF-T AO 1.01_01 contra o XSD.

Utiliza lxml para:
  1. Validar o XML gerado contra o schema SAFTAO1.01_01.xsd (fase 9.1 do plano).
  2. Devolver lista de erros formatada, pronta para apresentar na view ou log.

Uso típico:
    from apps.fiscal.services.saft_validacao_service import SaftValidacaoService

    xml_bytes = SaftXmlGeneratorService(empresa, inicio, fim).generate_xml()
    ok, erros = SaftValidacaoService.validar(xml_bytes)
    if not ok:
        for erro in erros:
            print(erro)
"""
import logging
import os
from pathlib import Path
from typing import List, Tuple

from lxml import etree

from .utils import FiscalServiceError

logger = logging.getLogger('fiscal.saft_validacao')

# Caminho absoluto para o XSD — independente do directório de trabalho
_XSD_PATH = Path(__file__).resolve().parent.parent / 'schemas' / 'SAFTAO1.01_01.xsd'


class SaftValidacaoService:
    """
    Valida um ficheiro SAF-T AO 1.01_01 (bytes XML) contra o XSD oficial
    fornecido pela AGT.

    Todos os métodos são estáticos — não é necessário instanciar a classe.
    """

    # Cache do schema compilado (carregado uma vez por processo)
    _schema: etree.XMLSchema | None = None

    @classmethod
    def _obter_schema(cls) -> etree.XMLSchema:
        """Carrega e compila o XSD, com cache de processo."""
        if cls._schema is None:
            if not _XSD_PATH.exists():
                raise FiscalServiceError(
                    f"XSD do SAF-T AO não encontrado em: {_XSD_PATH}\n"
                    "Coloque o ficheiro SAFTAO1.01_01.xsd em apps/fiscal/schemas/."
                )
            xsd_doc = etree.parse(str(_XSD_PATH))
            cls._schema = etree.XMLSchema(xsd_doc)
            logger.info(f"XSD SAF-T AO carregado: {_XSD_PATH}")
        return cls._schema

    @classmethod
    def validar(cls, xml_bytes: bytes) -> Tuple[bool, List[str]]:
        """
        Valida `xml_bytes` contra o XSD SAF-T AO 1.01_01.

        Devolve:
            (True, [])                   — XML válido
            (False, ["erro1", "erro2"])  — XML inválido, com lista de erros
        """
        if not xml_bytes:
            return False, ["XML vazio — nada para validar."]

        try:
            schema = cls._obter_schema()
        except FiscalServiceError as e:
            return False, [str(e)]
        except etree.XMLSchemaParseError as e:
            msg = f"Erro ao compilar o XSD: {e}"
            logger.error(msg)
            return False, [msg]

        try:
            xml_doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            msg = f"XML malformado: {e}"
            logger.warning(msg)
            return False, [msg]

        valido = schema.validate(xml_doc)

        if valido:
            logger.info("SAF-T AO validado com sucesso contra o XSD.")
            return True, []

        erros = cls._formatar_erros(schema.error_log)
        logger.warning(f"SAF-T AO inválido — {len(erros)} erro(s) encontrado(s).")
        return False, erros

    @staticmethod
    def _formatar_erros(error_log) -> List[str]:
        """
        Formata a lista de erros do lxml para strings legíveis.

        Cada entrada inclui: linha, coluna, nível e mensagem.
        """
        erros = []
        for erro in error_log:
            nivel = erro.level_name  # 'ERROR' | 'FATAL' | 'WARNING'
            linha = erro.line
            coluna = erro.column
            mensagem = erro.message
            erros.append(f"[{nivel}] Linha {linha}, Col {coluna}: {mensagem}")
        return erros

    @classmethod
    def validar_ficheiro(cls, caminho: str) -> Tuple[bool, List[str]]:
        """
        Conveniência: valida um ficheiro SAF-T em disco.

        Args:
            caminho: caminho absoluto ou relativo para o ficheiro XML.

        Devolve o mesmo formato que `validar()`.
        """
        try:
            xml_bytes = Path(caminho).read_bytes()
        except OSError as e:
            return False, [f"Não foi possível ler o ficheiro: {e}"]
        return cls.validar(xml_bytes)

    @classmethod
    def validar_e_lancar(cls, xml_bytes: bytes) -> None:
        """
        Valida e lança FiscalServiceError com todos os erros se inválido.
        Útil em contextos onde a excepção deve interromper o fluxo.
        """
        ok, erros = cls.validar(xml_bytes)
        if not ok:
            detalhe = "\n".join(f"  • {e}" for e in erros[:20])
            total = len(erros)
            sufixo = f"\n  ... e mais {total - 20} erro(s)." if total > 20 else ""
            raise FiscalServiceError(
                f"SAF-T AO inválido ({total} erro(s)):\n{detalhe}{sufixo}"
            )

    @classmethod
    def resumo(cls, xml_bytes: bytes) -> dict:
        """
        Devolve um dict com o resultado da validação, pronto para JSON.

        Estrutura:
        {
            "valido": bool,
            "total_erros": int,
            "erros": ["...", ...],   # máximo 50 entradas
        }
        """
        ok, erros = cls.validar(xml_bytes)
        return {
            "valido": ok,
            "total_erros": len(erros),
            "erros": erros[:50],
        }

# apps/fiscal/services/serie_fiscal_service.py
"""
SerieFiscalService — gestão das séries de numeração junto da AGT.

Implementa os dois serviços do Portal do Parceiro:
  - solicitarSerie  → criar série na AGT e persistir em SerieFiscalAGT
  - listarSeries    → sincronizar séries da AGT com o modelo local

Isolamento físico: não recebe `empresa` como parâmetro — lê AssinaturaDigital
do schema/tenant activo.

Toda a comunicação HTTP (Basic Auth do produtor, envelope, assinatura e retry)
está no AGTClient; este serviço só persiste o resultado em SerieFiscalAGT /
ContadorDocumento.

Regras críticas (Portal do Parceiro AGT):
  - De 1 Jan a 15 Dez: só pode criar série para o ano corrente.
  - Após 15 Dez: pode criar para o ano corrente e o imediatamente seguinte.
  - seriesCode deve conter o ano com 2 ou 4 dígitos.
  - establishmentNumber: estabelecimento registado no Portal do Contribuinte.
  - O mesmo software (softwareValidationNumber) que cria a série deve usá-la.

AGT_BASE_URL_* deve terminar em /sigt/fe/v1, por exemplo:
  https://sifphml.minfin.gov.ao/sigt/fe/v1   (homologação)
  https://sifp.minfin.gov.ao/sigt/fe/v1      (produção)
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Max

from apps.fiscal.models import (
    AssinaturaDigital,
    ContadorDocumento,
    DocumentoFiscal,
    SerieFiscalAGT,
)
from apps.fiscal.services.agt_client import AGTClient
from .utils import FiscalServiceError

logger = logging.getLogger('fiscal.serie')


class SerieFiscalService:
    """
    Gere séries de numeração junto da API da AGT e no modelo local.
    """

    def __init__(self, client: Optional[AGTClient] = None):
        # AGTClient valida o ambiente (HOMOLOGACAO/PRODUCTION) e a URL HTTPS.
        self.client = client or AGTClient()
        self.ambiente = self.client.ambiente
        self.base_url = self.client.base_url

    # ─────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────

    def solicitar_serie(
        self,
        document_type: str,
        series_year: int,
        establishment_number: str = "SEDE",
        contingency: bool = False,
    ) -> SerieFiscalAGT:
        """Solicita uma série à AGT e guarda o código efectivamente devolvido."""
        document_type = (document_type or "").strip().upper()
        establishment_number = (establishment_number or "").strip()

        tipos_agt = {
            "FA", "FT", "FR", "FG", "GF", "AC", "AR", "TV", "RC",
            "RG", "RE", "ND", "NC", "AF", "RP", "RA", "CS", "LD",
        }
        if document_type not in tipos_agt:
            raise FiscalServiceError(
                f"Tipo de documento AGT inválido: {document_type or '(vazio)'}."
            )
        if not establishment_number:
            raise FiscalServiceError(
                "Indique o estabelecimento que está registado no Portal do Contribuinte AGT."
            )

        SerieFiscalAGT.validar_ano_serie(series_year)
        contingency_indicator = "C" if contingency else "N"

        resultado = self.client.solicitar_serie(
            document_type=document_type,
            series_year=series_year,
            establishment_number=establishment_number,
            contingency=contingency,
        )
        # O código oficial vem da resposta AGT, nunca do formulário local.
        series_code = str(resultado.get("seriesCode") or "").strip()
        if not series_code:
            raise FiscalServiceError(
                "A AGT respondeu sem seriesFEResult.seriesCode. A série não foi guardada."
            )
        self._validar_series_code(series_code, series_year)

        try:
            primeiro = int(str(resultado.get("firstDocumentNo", "")).strip())
            quantidade = int(str(resultado.get("authorizedQuantity", "")).strip())
            ultimo_raw = resultado.get("lastDocumentNo")
            ultimo = (
                int(str(ultimo_raw).strip())
                if ultimo_raw not in (None, "")
                else primeiro + quantidade - 1
            )
        except (TypeError, ValueError) as exc:
            raise FiscalServiceError(
                "A resposta da AGT não contém firstDocumentNo/authorizedQuantity válidos."
            ) from exc

        if primeiro < 1 or quantidade < 1 or ultimo < primeiro:
            raise FiscalServiceError(
                "A AGT devolveu limites de numeração inválidos; a série não foi guardada."
            )

        with transaction.atomic():
            serie, criada = SerieFiscalAGT.objects.update_or_create(
                series_code=series_code,
                series_year=series_year,
                document_type=document_type,
                defaults={
                    "series_status": SerieFiscalAGT.STATUS_ABERTA,
                    "invoicing_method": SerieFiscalAGT.METODO_FESF,
                    "contingency_indicator": contingency_indicator,
                    "establishment_number": establishment_number,
                    "first_document_no": str(primeiro),
                    "last_document_no": str(ultimo),
                    "authorized_quantity": str(quantidade),
                    "series_creation_date": date.today(),
                },
            )

            contador, _ = ContadorDocumento.objects.get_or_create(
                tipo_documento=document_type,
                ano=series_year,
                serie=series_code,
                defaults={"ultimo_numero": max(0, primeiro - 1)},
            )
            # Nunca andar o contador para trás. Se a primeira gama autorizada
            # começar acima de 1, o contador começa antes desse primeiro número.
            minimo_contador = max(0, primeiro - 1)
            if contador.ultimo_numero < minimo_contador:
                contador.ultimo_numero = minimo_contador
                contador.save(update_fields=["ultimo_numero"])

            serie.contador = contador
            serie.save(update_fields=["contador"])

        logger.info(
            "Série AGT persistida: tipo=%s ano=%s criada=%s",
            document_type, series_year, criada,
        )
        return serie

    def sincronizar_series(
        self,
        series_year: Optional[int] = None,
        document_type: Optional[str] = None,
        series_status: Optional[str] = None,
        establishment_number: str = "SEDE",
    ) -> List[SerieFiscalAGT]:
        """
        Chama listarSeries na AGT e sincroniza o resultado com os registos locais.

        Args:
            series_year:          Filtrar por ano (opcional).
            document_type:        Filtrar por tipo de documento (opcional).
            series_status:        Filtrar por estado A/U/F (opcional).
            establishment_number: Estabelecimento registado no Portal do Contribuinte.

        Returns:
            Lista de SerieFiscalAGT criadas ou actualizadas.
        """
        logger.info("Sincronizando séries com a AGT (listarSeries).")
        series_info = self.client.listar_series(
            series_year=series_year,
            document_type=document_type,
            series_status=series_status,
            establishment_number=establishment_number,
        )

        series_actualizadas: List[SerieFiscalAGT] = []

        with transaction.atomic():
            for info in series_info:
                code = info.get('seriesCode', '')
                dtype = info.get('documentType', '')
                try:
                    year = int(info.get('seriesYear', 0))
                except (TypeError, ValueError):
                    year = 0
                if not (code and year and dtype):
                    continue

                serie, _ = SerieFiscalAGT.objects.update_or_create(
                    series_code=code,
                    series_year=year,
                    document_type=dtype,
                    defaults={
                        'series_status':          info.get('seriesStatus', SerieFiscalAGT.STATUS_ABERTA),
                        'invoicing_method':       info.get('invoicingMethod', SerieFiscalAGT.METODO_FESF),
                        'contingency_indicator':  info.get('seriesContingencyIndicator', 'N'),
                        'first_document_no':      info.get('firstDocumentApproved') or info.get('firstDocumentCreated', ''),
                        'last_document_no':       info.get('lastDocumentApproved') or info.get('lastDocumentCreated', ''),
                        'first_document_created': info.get('firstDocumentCreated', ''),
                        'last_document_created':  info.get('lastDocumentCreated', ''),
                        'series_creation_date':   self._parse_date(info.get('seriesCreationDate')),
                    },
                )

                try:
                    primeiro_autorizado = int(str(serie.first_document_no or "1").strip())
                except (TypeError, ValueError):
                    primeiro_autorizado = 1

                maior_documento_local = (
                    DocumentoFiscal.objects.filter(
                        tipo_documento=dtype,
                        serie=code,
                    ).aggregate(maior=Max("numero"))["maior"] or 0
                )

                minimo_contador = max(0, primeiro_autorizado - 1, maior_documento_local)
                contador, _ = ContadorDocumento.objects.get_or_create(
                    tipo_documento=dtype,
                    ano=year,
                    serie=code,
                    defaults={"ultimo_numero": minimo_contador},
                )
                if contador.ultimo_numero < minimo_contador:
                    contador.ultimo_numero = minimo_contador
                    contador.save(update_fields=["ultimo_numero"])

                serie.contador = contador
                serie.save(update_fields=["contador"])
                series_actualizadas.append(serie)

        logger.info("Sincronização concluída: %d série(s) actualizadas.", len(series_actualizadas))
        return series_actualizadas

    # ─────────────────────────────────────────────────────────────────────
    # Utilitários locais
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def obter_serie_para_documento(
        document_type: str,
        series_year: int,
    ) -> SerieFiscalAGT:
        """
        Devolve a série utilizável local para um tipo/ano.
        Lança FiscalServiceError se não existir nenhuma.
        """
        serie = SerieFiscalAGT.objects.filter(
            document_type=document_type,
            series_year=series_year,
            series_status__in=[SerieFiscalAGT.STATUS_ABERTA, SerieFiscalAGT.STATUS_UTILIZACAO],
        ).order_by('series_code').first()

        if not serie:
            raise FiscalServiceError(
                f"Nenhuma série utilizável encontrada para {document_type}/{series_year}. "
                "Solicite uma série junto da AGT em Configurações Fiscais → Séries."
            )
        return serie

    @staticmethod
    def proximo_numero(serie: SerieFiscalAGT) -> Tuple[int, str]:
        """
        Incrementa o ContadorDocumento da série e devolve (numero, numero_documento).
        Usa select_for_update para evitar concorrência.

        Returns:
            (numero_sequencial: int, numero_documento_formatado: str)
            Formato: "<document_type> <series_code>/<numero>"
            Exemplo:  "FT FT2025A/1"
        """
        if not serie.contador:
            raise FiscalServiceError(
                f"Série {serie.series_code} não tem ContadorDocumento associado."
            )
        with transaction.atomic():
            contador = ContadorDocumento.objects.select_for_update().get(pk=serie.contador_id)
            contador.ultimo_numero += 1
            contador.save(update_fields=['ultimo_numero'])

            # Actualizar estado da série para U (em utilização)
            if serie.series_status == SerieFiscalAGT.STATUS_ABERTA:
                serie.series_status = SerieFiscalAGT.STATUS_UTILIZACAO
                serie.save(update_fields=['series_status'])
                if not serie.first_document_created:
                    serie.first_document_created = str(contador.ultimo_numero)
                    serie.save(update_fields=['first_document_created'])

            serie.last_document_created = str(contador.ultimo_numero)
            serie.save(update_fields=['last_document_created'])

        numero_doc = f"{serie.document_type} {serie.series_code}/{contador.ultimo_numero}"
        return contador.ultimo_numero, numero_doc

    # ─────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _obter_config() -> AssinaturaDigital:
        config = AssinaturaDigital.obter_configuracao()
        if not config or not config.esta_configurada:
            raise FiscalServiceError(
                "Chave do contribuinte não configurada para este tenant. "
                "Configure-a em Configurações Fiscais."
            )
        if not config.nif_contribuinte:
            raise FiscalServiceError("NIF do contribuinte não definido em Configurações Fiscais.")
        return config

    @staticmethod
    def _validar_series_code(series_code: str, series_year: int) -> None:
        """
        O seriesCode deve:
          - Ter entre 3 e 60 caracteres.
          - Conter o ano com 2 ou 4 dígitos.
        """
        if not (3 <= len(series_code) <= 60):
            raise FiscalServiceError(
                f"seriesCode '{series_code}' inválido: deve ter entre 3 e 60 caracteres."
            )
        ano_2 = str(series_year)[-2:]  # ex.: "25"
        ano_4 = str(series_year)       # ex.: "2025"
        if ano_2 not in series_code and ano_4 not in series_code:
            raise FiscalServiceError(
                f"seriesCode '{series_code}' não contém o ano {series_year} "
                f"(nem '{ano_2}' nem '{ano_4}'). Regra AGT: o código deve incluir o ano de emissão."
            )

    @staticmethod
    def _parse_date(valor: Optional[str]) -> Optional[date]:
        if not valor:
            return None
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d'):
            try:
                return datetime.strptime(valor, fmt).date()
            except (ValueError, TypeError):
                continue
        return None
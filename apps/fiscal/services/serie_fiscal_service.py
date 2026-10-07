# apps/fiscal/services/serie_fiscal_service.py
"""
SerieFiscalService — gestão das séries de numeração junto da AGT.

Implementa os dois serviços do Decreto Executivo 683/25 / Portal do Parceiro:
  - solicitarSerie  → criar série na AGT e persistir em SerieFiscalAGT
  - listarSeries    → sincronizar séries da AGT com o modelo local

Isolamento físico: não recebe `empresa` como parâmetro — lê AssinaturaDigital
do schema/tenant activo.

Regras críticas (Portal do Parceiro AGT):
  - De 1 Jan a 15 Dez: só pode criar série para o ano corrente.
  - Após 15 Dez: pode criar para o ano corrente e o imediatamente seguinte.
  - seriesCode deve conter o ano com 2 ou 4 dígitos.
  - establishmentNumber: estabelecimento registado no Portal do Contribuinte.
  - O mesmo software (softwareValidationNumber) que cria a série deve usá-la.
"""

import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.fiscal.models import AssinaturaDigital, ContadorDocumento, SerieFiscalAGT
from apps.fiscal.services.assinatura_service import (
    AssinaturaDigitalService,
    AssinaturaSoftwareService,
)
from apps.fiscal.utility.crypto import AESService
from .utils import FiscalServiceError

logger = logging.getLogger('fiscal.serie')


class SerieFiscalService:
    """
    Gere séries de numeração junto da API da AGT e no modelo local.
    """

    def __init__(self):
        if settings.AGT_ENVIRONMENT == 'PRODUCTION':
            self._url_solicitar = f"{settings.AGT_BASE_URL_PRODUCAO}/solicitarSerie"
            self._url_listar    = f"{settings.AGT_BASE_URL_PRODUCAO}/listarSeries"
        else:
            self._url_solicitar = f"{settings.AGT_BASE_URL_HOMOLOGACAO}/solicitarSerie"
            self._url_listar    = f"{settings.AGT_BASE_URL_HOMOLOGACAO}/listarSeries"

    # ─────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────

    @transaction.atomic
    def solicitar_serie(
        self,
        document_type: str,
        series_year: int,
        series_code: str,
        establishment_number: str = 'SEDE',
        contingency: bool = False,
    ) -> SerieFiscalAGT:
        """
        Cria uma nova série junto da AGT e persiste o resultado.

        Args:
            document_type:        Código do tipo de documento (ex.: 'FT', 'NC').
            series_year:          Ano da série (ex.: 2025).
            series_code:          Código proposto (deve conter o ano).
            establishment_number: Estabelecimento registado no Portal.
            contingency:          True para série de contingência.

        Returns:
            SerieFiscalAGT criada/actualizada.

        Raises:
            FiscalServiceError: erro de validação ou de comunicação com a AGT.
        """
        # 1. Validações locais antes de chamar a API
        SerieFiscalAGT.validar_ano_serie(series_year)
        self._validar_series_code(series_code, series_year)

        config = self._obter_config()

        # 2. Montar payload de assinatura da requisição
        contingency_indicator = 'C' if contingency else 'N'
        payload_assinatura = {
            "taxRegistrationNumber": config.nif_contribuinte,
            "seriesYear": str(series_year),
            "documentType": document_type,
            "establishmentNumber": establishment_number,
            "seriesContingencyIndicator": contingency_indicator,
        }
        jws_signature = AssinaturaDigitalService.assinar_requisicao(payload_assinatura)

        # 3. Montar payload completo
        submission_uuid = str(uuid.uuid4())
        payload = {
            "schemaVersion": "2.0",
            "submissionUUID": submission_uuid,
            "taxRegistrationNumber": config.nif_contribuinte,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": AssinaturaSoftwareService.montar_software_info(),
            "seriesYear": series_year,
            "documentType": document_type,
            "establishmentNumber": establishment_number,
            "jwsSignature": jws_signature,
            "seriesContingencyIndicator": contingency_indicator,
        }

        # 4. Chamada à API AGT
        credenciais = self._obter_credenciais(config)
        logger.info(
            "Solicitando série à AGT: type=%s, year=%s, code=%s",
            document_type, series_year, series_code,
        )
        try:
            resp = requests.post(
                self._url_solicitar,
                json=payload,
                auth=(credenciais['username'], credenciais['password']),
                timeout=45,
            )
        except requests.RequestException as e:
            raise FiscalServiceError(f"Falha de rede ao contactar AGT (solicitarSerie): {e}")

        resultado = self._tratar_resposta_solicitar(resp, series_code)

        # 5. Persistir em SerieFiscalAGT
        serie, created = SerieFiscalAGT.objects.update_or_create(
            series_code=series_code,
            series_year=series_year,
            document_type=document_type,
            defaults={
                'series_status': SerieFiscalAGT.STATUS_ABERTA,
                'invoicing_method': SerieFiscalAGT.METODO_FESF,
                'contingency_indicator': contingency_indicator,
                'establishment_number': establishment_number,
                'first_document_no': resultado.get('firstDocumentNo', '1'),
                'last_document_no': resultado.get('lastDocumentNo', ''),
                'authorized_quantity': str(resultado.get('authorizedQuantity', '')),
                'series_creation_date': date.today(),
            },
        )

        # 6. Criar / ligar ContadorDocumento local
        contador, _ = ContadorDocumento.objects.get_or_create(
            tipo_documento=document_type,
            ano=series_year,
            serie=series_code,
            defaults={'ultimo_numero': 0},
        )
        serie.contador = contador
        serie.save(update_fields=['contador'])

        logger.info(
            "Série %s criada (AGT). first_doc=%s, action=%s",
            series_code, resultado.get('firstDocumentNo'), 'created' if created else 'updated',
        )
        return serie

    def sincronizar_series(
        self,
        series_year: Optional[int] = None,
        document_type: Optional[str] = None,
        series_status: Optional[str] = None,
    ) -> List[SerieFiscalAGT]:
        """
        Chama listarSeries na AGT e sincroniza o resultado com os registos locais.

        Args:
            series_year:   Filtrar por ano (opcional).
            document_type: Filtrar por tipo de documento (opcional).
            series_status: Filtrar por estado A/U/F (opcional).

        Returns:
            Lista de SerieFiscalAGT criadas ou actualizadas.
        """
        config = self._obter_config()

        payload_assinatura = {"taxRegistrationNumber": config.nif_contribuinte}
        jws_signature = AssinaturaDigitalService.assinar_requisicao(payload_assinatura)

        payload: Dict[str, Any] = {
            "schemaVersion": "2.0",
            "taxRegistrationNumber": config.nif_contribuinte,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": AssinaturaSoftwareService.montar_software_info(),
            "jwsSignature": jws_signature,
            "establishmentNumber": "SEDE",
        }
        if series_year:
            payload["seriesYear"] = series_year
        if document_type:
            payload["documentType"] = document_type
        if series_status:
            payload["seriesStatus"] = series_status

        credenciais = self._obter_credenciais(config)
        logger.info("Sincronizando séries com a AGT (listarSeries).")
        try:
            resp = requests.post(
                self._url_listar,
                json=payload,
                auth=(credenciais['username'], credenciais['password']),
                timeout=45,
            )
        except requests.RequestException as e:
            raise FiscalServiceError(f"Falha de rede ao contactar AGT (listarSeries): {e}")

        if resp.status_code not in (200, 422):
            raise FiscalServiceError(
                f"Erro inesperado da AGT (listarSeries): HTTP {resp.status_code} — {resp.text[:300]}"
            )

        try:
            data = resp.json()
        except Exception:
            raise FiscalServiceError(f"Resposta não-JSON da AGT (listarSeries): {resp.text[:300]}")

        series_info = data.get('seriesInfo') or data.get('seriresInfo', [])
        series_actualizadas = []

        with transaction.atomic():
            for info in series_info:
                code  = info.get('seriesCode', '')
                year  = int(info.get('seriesYear', 0))
                dtype = info.get('documentType', '')
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
                        'last_document_no':       info.get('lastDocumentApproved')  or info.get('lastDocumentCreated', ''),
                        'first_document_created': info.get('firstDocumentCreated', ''),
                        'last_document_created':  info.get('lastDocumentCreated', ''),
                        'series_creation_date':   self._parse_date(info.get('seriesCreationDate')),
                    },
                )
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
    def _obter_credenciais(config: AssinaturaDigital) -> Dict[str, str]:
        if not config.api_username or not config.api_password:
            raise FiscalServiceError(
                "Credenciais da API AGT não configuradas. "
                "Aceda a Configurações Fiscais e insira username/password emitidos pela AGT."
            )
        return {
            'username': config.api_username,
            'password': AESService.decrypt(config.api_password),
        }

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
        ano_2  = str(series_year)[-2:]  # ex.: "25"
        ano_4  = str(series_year)       # ex.: "2025"
        if ano_2 not in series_code and ano_4 not in series_code:
            raise FiscalServiceError(
                f"seriesCode '{series_code}' não contém o ano {series_year} "
                f"(nem '{ano_2}' nem '{ano_4}'). Regra AGT: o código deve incluir o ano de emissão."
            )

    @staticmethod
    def _tratar_resposta_solicitar(resp: requests.Response, series_code: str) -> Dict[str, Any]:
        """Trata a resposta de solicitarSerie e devolve seriesFEResult."""
        try:
            data = resp.json()
        except Exception:
            raise FiscalServiceError(
                f"Resposta não-JSON da AGT (solicitarSerie): {resp.text[:300]}"
            )

        if resp.status_code == 200:
            result_code = data.get('resultCode')
            if str(result_code) == '1':
                return data.get('seriesFEResult', {})
            erros = data.get('errorList', [])
            detalhe = '; '.join(
                f"E{e.get('idError','?')}: {e.get('descriptionError','')}" for e in erros
            )
            raise FiscalServiceError(
                f"AGT recusou a criação da série '{series_code}': {detalhe or 'sem detalhe'}"
            )

        erros = data.get('errorList', [])
        detalhe = '; '.join(
            f"E{e.get('idError','?')}: {e.get('descriptionError','')}" for e in erros
        )
        raise FiscalServiceError(
            f"Erro da AGT HTTP {resp.status_code} ao criar série '{series_code}': "
            f"{detalhe or resp.text[:200]}"
        )

    @staticmethod
    def _parse_date(valor: Optional[str]) -> Optional[date]:
        if not valor:
            return None
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d'):
            try:
                from datetime import datetime
                return datetime.strptime(valor, fmt).date()
            except (ValueError, TypeError):
                continue
        return None

# apps/fiscal/services/agt_client.py
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django_tenants.utils import get_public_schema_name

from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, AssinaturaSoftwareService
from apps.fiscal.services.payload_inspector import PayloadInspectorService
from apps.fiscal.services.utils import FiscalServiceError

logger = logging.getLogger("fiscal.agt")


class AGTError(FiscalServiceError):
    """Erro HTTP/AGT com contexto estruturado para tratamento no serviço chamador."""

    def __init__(self, message: str, *, servico: str = "", http_status: Optional[int] = None, result_code: str = "", erros: Optional[List[str]] = None, rede: bool = False,) -> None:
        super().__init__(message)
        self.servico = servico
        self.http_status = http_status
        self.result_code = result_code
        self.erros = erros or []
        # True indica que a comunicação falhou ou o resultado é incerto.
        self.rede = rede


class AGTClient:
    """Ponto único de transporte HTTP da API AGT."""

    SERVICOS = {
        "listarSeries": {"schema": "2.0", "timeout": (5, 30), "retry": True},
        "solicitarSerie": {"schema": "2.0", "timeout": (5, 30), "retry": False},
        "registarFactura": {"schema": "2.0", "timeout": (5, 45), "retry": False},
        "obterEstado": {"schema": "1.0", "timeout": (5, 30), "retry": True},
    }
    _HTTP_REPETIVEIS = {502, 503, 504}
    _MAX_TENTATIVAS = 3
    _MAX_DOCUMENTOS_POR_SUBMISSAO = 30

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        ambiente = str(getattr(settings, "AGT_ENVIRONMENT", "")).strip().upper()

        if ambiente == "PRODUCTION":
            base_url = getattr(settings, "AGT_BASE_URL_PRODUCAO", "")
        elif ambiente in {"HOMOLOGACAO", "HOMOLOGAÇÃO"}:
            base_url = getattr(settings, "AGT_BASE_URL_HOMOLOGACAO", "")
        else:
            raise FiscalServiceError(
                "AGT_ENVIRONMENT inválido. Defina explicitamente HOMOLOGACAO ou PRODUCTION."
            )

        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url.startswith("https://"):
            raise FiscalServiceError(
                "A URL base da AGT tem de estar configurada e usar HTTPS."
            )

        self.ambiente = "HOMOLOGACAO" if ambiente == "HOMOLOGAÇÃO" else ambiente
        self.base_url = base_url
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    # Configuração e pré-validações
    # ------------------------------------------------------------------
    @staticmethod
    def credenciais_configuradas() -> bool:
        username = getattr(settings, "AGT_API_USERNAME", "") or ""
        password = getattr(settings, "AGT_API_PASSWORD", "") or ""
        return bool(username.strip() and password.strip())

    @staticmethod
    def _credenciais() -> tuple[str, str]:
        username = str(getattr(settings, "AGT_API_USERNAME", "") or "").strip()
        password = str(getattr(settings, "AGT_API_PASSWORD", "") or "")

        if not username or not password.strip():
            raise FiscalServiceError(
                "Credenciais da API AGT não configuradas. Defina AGT_API_USERNAME e "
                "AGT_API_PASSWORD no ambiente do servidor."
            )
        if ":" in username:
            raise FiscalServiceError(
                "AGT_API_USERNAME não pode conter ':' por causa do Basic Auth."
            )
        return username, password

    @staticmethod
    def _config_tenant() -> AssinaturaDigital:
        schema = getattr(connection, "schema_name", "public")
        if not schema or schema == get_public_schema_name():
            raise FiscalServiceError(
                "O cliente AGT tem de ser chamado dentro do schema de um tenant, nunca em public."
            )

        config = AssinaturaDigital.obter_configuracao()
        if not config or not config.esta_configurada:
            raise FiscalServiceError(
                "As chaves digitais do contribuinte não estão configuradas neste tenant."
            )
        if not config.nif_contribuinte:
            raise FiscalServiceError("NIF do contribuinte não definido para este tenant.")

        # Não basta verificar se há PEMs: verificar o carimbo do tenant, NIF e par de chaves.
        try:
            problemas = config.verificar_integridade()
        except Exception as exc:
            raise FiscalServiceError(
                "Não foi possível verificar a integridade das chaves fiscais deste tenant."
            ) from exc
        if problemas:
            raise FiscalServiceError(
                "Chaves fiscais inconsistentes: " + "; ".join(problemas)
            )
        return config

    @staticmethod
    def _validar_software_info(payload: Dict[str, Any]) -> None:
        """Falha antes do HTTP se softwareInfoDetail não cumprir o envelope v2.0."""
        software = payload.get("softwareInfo")
        if not isinstance(software, dict):
            raise FiscalServiceError("O envelope AGT não contém softwareInfo válido.")

        detail = software.get("softwareInfoDetail")
        if not isinstance(detail, dict):
            raise FiscalServiceError("softwareInfo.softwareInfoDetail tem de ser um objecto.")

        obrigatorios = {
            "productId",
            "productVersion",
            "softwareValidationNumber",
            "signatureVersion",
        }
        em_falta = sorted(
            campo for campo in obrigatorios
            if campo not in detail or detail[campo] in (None, "")
        )
        if em_falta:
            raise FiscalServiceError(
                "softwareInfoDetail incompleto; falta(m): " + ", ".join(em_falta)
                + ". Actualize AssinaturaSoftwareService para incluir os campos exigidos pela AGT."
            )

        signature_version = detail["signatureVersion"]
        if isinstance(signature_version, bool) or not isinstance(signature_version, int):
            raise FiscalServiceError(
                "softwareInfoDetail.signatureVersion deve ser um inteiro conforme o esquema AGT."
            )
        if not str(software.get("jwsSoftwareSignature") or "").strip():
            raise FiscalServiceError("Falta softwareInfo.jwsSoftwareSignature.")

    def _validar_envelope_registar_factura(self, payload: Dict[str, Any]) -> None:
        """Valida o envelope mínimo antes da captura e do envio."""
        if not isinstance(payload, dict):
            raise FiscalServiceError("O payload registarFactura tem de ser um objecto JSON.")

        obrigatorios = (
            "schemaVersion",
            "submissionUUID",
            "taxRegistrationNumber",
            "submissionTimeStamp",
            "softwareInfo",
            "numberOfEntries",
            "documents",
            "jwsSignature",
        )
        em_falta = [campo for campo in obrigatorios if campo not in payload]
        if em_falta:
            raise FiscalServiceError(
                "Envelope registarFactura incompleto; falta(m): " + ", ".join(em_falta)
            )

        try:
            uuid.UUID(str(payload["submissionUUID"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise FiscalServiceError(
                "submissionUUID tem de ser um UUID válido e estável para esta submissão."
            ) from exc

        documents = payload.get("documents")
        if not isinstance(documents, list) or not documents:
            raise FiscalServiceError(
                "registarFactura exige uma lista não vazia no campo documents."
            )
        if len(documents) > self._MAX_DOCUMENTOS_POR_SUBMISSAO:
            raise FiscalServiceError(
                f"A AGT permite no máximo {self._MAX_DOCUMENTOS_POR_SUBMISSAO} documentos por pedido."
            )
        if isinstance(payload.get("numberOfEntries"), bool) or payload.get("numberOfEntries") != len(documents):
            raise FiscalServiceError(
                "numberOfEntries tem de coincidir com o número de elementos de documents."
            )
        if not str(payload.get("taxRegistrationNumber") or "").strip():
            raise FiscalServiceError("Falta taxRegistrationNumber no envelope AGT.")
        if not str(payload.get("jwsSignature") or "").strip():
            raise FiscalServiceError("Falta jwsSignature no envelope AGT.")

        self._validar_software_info(payload)

        for index, document in enumerate(documents, start=1):
            if not isinstance(document, dict):
                raise FiscalServiceError(f"documents[{index - 1}] tem de ser um objecto JSON.")
            if not str(document.get("documentNo") or "").strip():
                raise FiscalServiceError(f"documents[{index - 1}] não tem documentNo.")
            if not str(document.get("jwsDocumentSignature") or "").strip():
                raise FiscalServiceError(f"documents[{index - 1}] não tem jwsDocumentSignature.")

    # ------------------------------------------------------------------
    # Núcleo HTTP
    # ------------------------------------------------------------------
    def _chamar(self, servico: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Envia um pedido. Captura registarFactura uma única vez antes do HTTP."""
        try:
            meta = self.SERVICOS[servico]
        except KeyError as exc:
            raise FiscalServiceError(f"Serviço AGT não suportado: {servico!r}.") from exc

        if not isinstance(payload, dict):
            raise FiscalServiceError(f"O payload de {servico} tem de ser um objecto JSON.")

        url = f"{self.base_url}/{servico}"
        raw_json = None
        captura_payload = None

        if servico == "registarFactura":
            documents = payload.get("documents")

            if not isinstance(documents, list) or not documents:
                raise FiscalServiceError(
                    "registarFactura exige uma lista documents não vazia."
                )

            # Uma única serialização para captura, hash e transporte.
            raw_json = PayloadInspectorService.serializar_payload(payload)

            try:
                captura_payload = PayloadInspectorService.registar_payload(
                    payload=payload,
                    raw_json=raw_json,
                    endpoint=url,
                    ambiente=self.ambiente,
                )
            except Exception as exc:
                logger.exception(
                    "Falha ao persistir o payload AGT. Pedido bloqueado."
                )
                raise FiscalServiceError(
                    "O Inspector não conseguiu guardar o envelope. "
                    "O pedido não foi enviado."
                ) from exc

            try:
                self._validar_envelope_registar_factura(payload)

            except Exception as exc:
                PayloadInspectorService.marcar_falha(
                    captura_payload,
                    f"Payload inválido e não enviado: {exc}",
                    pedido_enviado=False,
                )
                raise

        try:
            auth = self._credenciais()
        except Exception as exc:
            if captura_payload is not None:
                try:
                    PayloadInspectorService.marcar_falha(
                        captura_payload,
                        str(exc),
                        pedido_enviado=False,
                    )
                except Exception:
                    logger.exception(
                        "Falha ao registar erro de autenticação no Inspector AGT."
                    )
            raise

        tentativas = self._MAX_TENTATIVAS if meta["retry"] else 1
        ultimo_erro: Optional[AGTError] = None

        for tentativa in range(1, tentativas + 1):
            try:
                if captura_payload is not None:
                    autorizado = PayloadInspectorService.marcar_enviado(
                        captura_payload
                    )

                    if not autorizado:
                        raise AGTError(
                            "O envio foi bloqueado porque este envelope já foi "
                            "reivindicado, enviado ou tem resultado indeterminado.",
                            servico="registarFactura",
                        )

                if servico == "registarFactura":
                    response = self._session.post(
                        url,
                        data=raw_json.encode("utf-8"),
                        auth=auth,
                        timeout=meta["timeout"],
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json; charset=utf-8",
                        },
                    )
                else:
                    response = self._session.post(
                        url,
                        json=payload,
                        auth=auth,
                        timeout=meta["timeout"],
                        headers={"Accept": "application/json"},
                    )

            except requests.RequestException as exc:
                if captura_payload is not None and tentativa >= tentativas:
                    try:
                        PayloadInspectorService.marcar_falha(
                            captura_payload,
                            (
                                "Falha de rede durante a submissão. Não é possível confirmar "
                                "se a AGT recebeu o pedido. Tipo de erro: "
                                f"{type(exc).__name__}."
                            ),
                            pedido_enviado=True,
                        )
                    except Exception:
                        logger.exception(
                            "Falha ao actualizar o estado de rede no Inspector AGT."
                        )

                ultimo_erro = AGTError(
                    f"Não foi possível contactar a AGT ({servico}): {exc}",
                    servico=servico,
                    rede=True,
                )
                logger.warning(
                    "AGT %s: falha de rede (tentativa %d/%d): %s",
                    servico,
                    tentativa,
                    tentativas,
                    type(exc).__name__,
                )

            else:
                if (
                    response.status_code in self._HTTP_REPETIVEIS
                    and meta["retry"]
                    and tentativa < tentativas
                ):
                    ultimo_erro = AGTError(
                        f"AGT indisponível (HTTP {response.status_code}) em {servico}.",
                        servico=servico,
                        http_status=response.status_code,
                        rede=True,
                    )
                else:
                    if captura_payload is not None:
                        try:
                            PayloadInspectorService.registar_resposta(
                                captura_payload,
                                response,
                            )
                        except Exception:
                            # Não lançar erro que incentive o chamador a repetir um POST
                            # cujo resultado remoto já pode existir.
                            logger.exception(
                                "Falha ao guardar a resposta HTTP no Inspector AGT."
                            )
                    return self._ler_resposta(response, servico)

            if tentativa < tentativas:
                time.sleep(2 ** (tentativa - 1))  # 1 s, 2 s

        if ultimo_erro is not None:
            raise ultimo_erro
        raise AGTError(f"A chamada ao serviço {servico} terminou sem resposta válida.", servico=servico)

    # ------------------------------------------------------------------
    # Interpretação de respostas
    # ------------------------------------------------------------------
    @classmethod
    def _ler_resposta(
        cls,
        resp: requests.Response,
        servico: str,
    ) -> Dict[str, Any]:
        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        corpo = (resp.text or "").strip()
        corpo_resumido = " ".join(corpo.split())[:300]

        if status == 401:
            challenge = resp.headers.get("WWW-Authenticate", "")
            logger.error(
                "AGT HTTP 401 em %s. URL=%s; Content-Type=%s; "
                "WWW-Authenticate=%s; corpo=%s",
                servico,
                resp.url,
                content_type or "(não indicado)",
                challenge[:200] or "(não indicado)",
                corpo_resumido or "(resposta vazia)",
            )
            raise AGTError(
                f"A AGT recusou a autenticação/autorização HTTP 401 no serviço {servico}. "
                "Verifique as credenciais Basic Auth do produtor de software, o ambiente "
                "e o endpoint configurado. Consulte o log técnico para mais detalhes.",
                servico=servico,
                http_status=status,
                result_code="HTTP_401",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error(
                "Resposta não JSON da AGT. Serviço=%s; HTTP=%s; Content-Type=%s; URL=%s; corpo=%s",
                servico,
                status,
                content_type or "(não indicado)",
                resp.url,
                corpo_resumido or "(resposta vazia)",
            )
            raise AGTError(
                f"A AGT devolveu uma resposta que não é JSON em {servico} (HTTP {status}).",
                servico=servico,
                http_status=status,
                result_code=f"HTTP_{status}",
            ) from exc

        if not isinstance(data, dict):
            raise AGTError(
                f"Resposta inesperada da AGT em {servico} (HTTP {status}).",
                servico=servico,
                http_status=status,
            )

        data["_http_status"] = status
        if status >= 400:
            erros = cls.detalhar_erros(data)
            detalhe = "; ".join(erros) or "sem detalhe fornecido pela AGT"
            logger.error(
                "AGT devolveu erro HTTP. Serviço=%s; HTTP=%s; detalhe=%s",
                servico,
                status,
                detalhe[:500],
            )
            raise AGTError(
                f"A AGT devolveu HTTP {status} em {servico}: {detalhe}",
                servico=servico,
                http_status=status,
                result_code=str(data.get("resultCode", "")),
                erros=erros,
            )
        return data

    @staticmethod
    def detalhar_erros(data: Dict[str, Any]) -> List[str]:
        erros = data.get("errorList") or data.get("requestErrorList") or []
        resultado = []
        for erro in erros:
            if isinstance(erro, dict):
                codigo = (
                    erro.get("idError")
                    or erro.get("errorCode")
                    or erro.get("code")
                    or "AGT"
                )
                descricao = (
                    erro.get("descriptionError")
                    or erro.get("errorDescription")
                    or erro.get("message")
                    or "sem detalhe"
                )
                resultado.append(f"{codigo}: {descricao}")
            else:
                resultado.append(str(erro))
        return resultado

    def _exigir_sucesso(
        self,
        data: Dict[str, Any],
        servico: str,
        mensagem: str,
    ) -> None:
        """Verifica HTTP 200 e resultCode == '1' nos serviços que usam esse contrato."""
        http = data.get("_http_status")
        code = str(data.get("resultCode", ""))
        if http == 200 and code == "1":
            return
        erros = self.detalhar_erros(data)
        raise AGTError(
            f"{mensagem} (HTTP {http}, resultCode={code or 'ausente'}): "
            f"{'; '.join(erros) or 'sem detalhe'}",
            servico=servico,
            http_status=http,
            result_code=code,
            erros=erros,
        )

    # ------------------------------------------------------------------
    # Envelope comum
    # ------------------------------------------------------------------
    def _envelope(
        self,
        servico: str,
        config: AssinaturaDigital,
        assinatura_campos: Dict[str, Any],
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        if servico not in self.SERVICOS:
            raise FiscalServiceError(f"Serviço AGT não suportado: {servico!r}.")

        software_info = AssinaturaSoftwareService.montar_software_info()
        payload = {
            "schemaVersion": self.SERVICOS[servico]["schema"],
            "taxRegistrationNumber": config.nif_contribuinte,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": software_info,
        }
        payload.update(extra)
        payload["jwsSignature"] = AssinaturaDigitalService.assinar_requisicao(
            assinatura_campos
        )
        return payload

    # ------------------------------------------------------------------
    # Serviços públicos AGT
    # ------------------------------------------------------------------
    def listar_series(
        self,
        *,
        series_year: Optional[int] = None,
        document_type: Optional[str] = None,
        series_status: Optional[str] = None,
        establishment_number: str = "SEDE",
    ) -> List[Dict[str, Any]]:
        config = self._config_tenant()
        extra: Dict[str, Any] = {"establishmentNumber": establishment_number}
        if series_year is not None:
            extra["seriesYear"] = series_year
        if document_type:
            extra["documentType"] = document_type
        if series_status:
            extra["seriesStatus"] = series_status

        payload = self._envelope(
            "listarSeries",
            config,
            {"taxRegistrationNumber": config.nif_contribuinte},
            extra,
        )
        data = self._chamar("listarSeries", payload)
        self._exigir_sucesso(
            data,
            "listarSeries",
            "listarSeries não confirmou sucesso",
        )
        # Mantém compatibilidade com a grafia presente em exemplos antigos da AGT.
        info = data.get("seriesInfo") or data.get("seriresInfo") or []
        if not isinstance(info, list):
            raise AGTError(
                "listarSeries sem lista de séries válida.",
                servico="listarSeries",
            )
        return info

    def solicitar_serie(
        self,
        *,
        document_type: str,
        series_year: int,
        establishment_number: str,
        contingency: bool = False,
    ) -> Dict[str, Any]:
        config = self._config_tenant()
        indicador = "C" if contingency else "N"
        assinatura_campos = {
            "taxRegistrationNumber": config.nif_contribuinte,
            "seriesYear": str(series_year),
            "documentType": document_type,
            "establishmentNumber": establishment_number,
            "seriesContingencyIndicator": indicador,
        }
        extra = {
            "submissionUUID": str(uuid.uuid4()),
            "seriesYear": series_year,
            "documentType": document_type,
            "establishmentNumber": establishment_number,
            "seriesContingencyIndicator": indicador,
        }
        payload = self._envelope(
            "solicitarSerie", config, assinatura_campos, extra
        )
        data = self._chamar("solicitarSerie", payload)
        self._exigir_sucesso(
            data,
            "solicitarSerie",
            "A AGT não autorizou a criação da série",
        )
        resultado = data.get("seriesFEResult")
        if not isinstance(resultado, dict):
            raise AGTError(
                "A AGT indicou sucesso mas sem seriesFEResult válido.",
                servico="solicitarSerie",
            )
        return resultado

    def registar_documento_fiscal(self, payload: Dict[str, Any],) -> Dict[str, Any]:
        """
        Submete um envelope completo.

        O Inspector captura o payload em _chamar().
        Só devolvemos sucesso quando a resposta contém HTTP 200,
        requestID e não apresenta erros comunicados pela AGT.
        """

        data = self._chamar("registarFactura", payload)

        http_status = data.get("_http_status")
        request_id = data.get("requestID")
        erros = self.detalhar_erros(data)

        if http_status == 200 and request_id and not erros:
            return data

        detalhe = "; ".join(erros) or "sem requestID devolvido pela AGT"

        raise AGTError(
            (
                "A AGT não confirmou a recepção da submissão "
                f"(HTTP {http_status}): {detalhe}"
            ),
            servico="registarFactura",
            http_status=http_status,
            result_code=str(data.get("resultCode", "")),
            erros=erros,
        )

    def registar_factura(self, documents: List[Dict[str, Any]], *, submission_uuid: Optional[str] = None,) -> Dict[str, Any]:
        """Constrói e submete um envelope a partir de documentos já assinados.

        O chamador deve persistir submission_uuid antes de enviar e reutilizar o
        mesmo UUID/payload ao reconciliar um timeout de resultado desconhecido.
        Não há retry automático para registarFactura.
        """
        if not isinstance(documents, list) or not documents:
            raise FiscalServiceError("registarFactura exige uma lista de documentos não vazia.")

        config = self._config_tenant()
        sub_uuid = str(submission_uuid or uuid.uuid4())
        try:
            uuid.UUID(sub_uuid)
        except (ValueError, TypeError, AttributeError) as exc:
            raise FiscalServiceError("submission_uuid tem de ser um UUID válido.") from exc

        extra = {
            "submissionUUID": sub_uuid,
            "numberOfEntries": len(documents),
            "documents": documents,
        }
        assinatura_campos = {
            "taxRegistrationNumber": config.nif_contribuinte,
            "submissionUUID": sub_uuid,
        }
        payload = self._envelope(
            "registarFactura", config, assinatura_campos, extra
        )
        data = self._chamar("registarFactura", payload)

        http = data.get("_http_status")
        request_id = data.get("requestID")
        erros = self.detalhar_erros(data)
        if http == 200 and request_id and not erros:
            return {"requestID": request_id, "submissionUUID": sub_uuid}

        raise AGTError(
            f"A AGT não confirmou a submissão (HTTP {http}): "
            f"{'; '.join(erros) or 'sem requestID'}",
            servico="registarFactura",
            http_status=http,
            result_code=str(data.get("resultCode", "")),
            erros=erros,
        )

    def obter_estado(self, request_id: str) -> Dict[str, Any]:
        if not request_id:
            raise FiscalServiceError("obterEstado exige requestID.")
        config = self._config_tenant()
        assinatura_campos = {
            "taxRegistrationNumber": config.nif_contribuinte,
            "requestID": request_id,
        }
        payload = self._envelope(
            "obterEstado",
            config,
            assinatura_campos,
            {"requestID": request_id},
        )
        data = self._chamar("obterEstado", payload)
        if data.get("_http_status") != 200:
            erros = self.detalhar_erros(data)
            raise AGTError(
                f"obterEstado falhou (HTTP {data.get('_http_status')}): "
                f"{'; '.join(erros) or 'sem detalhe'}",
                servico="obterEstado",
                http_status=data.get("_http_status"),
                result_code=str(data.get("resultCode", "")),
                erros=erros,
            )
        return data

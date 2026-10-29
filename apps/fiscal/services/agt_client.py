# apps/fiscal/services/agt_client.py
"""
AGTClient — ÚNICO ponto de comunicação HTTP com a API de Facturação
Electrónica da AGT.

Responsabilidades (e só estas):
  * Resolver o ambiente (HOMOLOGACAO / PRODUCTION) de forma EXPLÍCITA.
  * Basic Auth do PRODUTOR do software (SOTARQ), lido do ambiente
    (settings.AGT_API_USERNAME / AGT_API_PASSWORD). Nunca vem da base de dados
    nem de um tenant.
  * Montar o envelope comum (schemaVersion, NIF, timestamp, softwareInfo com
    jwsSoftwareSignature) e assinar a requisição com a chave do CONTRIBUINTE
    do tenant activo (jwsSignature).
  * Timeouts, retry controlado, leitura segura da resposta, erros tipados.

O que NÃO faz: persistir séries/documentos. Isso fica nos serviços de domínio
(SerieFiscalService, SubmissaoFaturaService, FiscalPollingService), que passam
a usar este cliente em vez de chamarem `requests` directamente.

Isolamento físico: não recebe `empresa`; lê AssinaturaDigital do schema activo.
Logo, tem de ser chamado dentro de um schema de tenant (schema_context).

Retry: só para serviços de LEITURA (listarSeries, obterEstado) e só perante
erros de rede/timeout ou HTTP 502/503/504. registarFactura e solicitarSerie
NUNCA são repetidos automaticamente (não são idempotentes por defeito); para os
repetir com segurança, o chamador persiste o `submission_uuid` e volta a
passá-lo.
"""
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.utils import timezone

from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.services.assinatura_service import (
    AssinaturaDigitalService,
    AssinaturaSoftwareService,
)
from apps.fiscal.services.payload_inspector import PayloadInspectorService
from apps.fiscal.services.utils import FiscalServiceError

logger = logging.getLogger("fiscal.agt")


class AGTError(FiscalServiceError):
    """Erro devolvido pela AGT (ou falha de comunicação com ela)."""

    def __init__(self, message, *, servico="", http_status=None, result_code="",
                 erros=None, rede=False):
        super().__init__(message)
        self.servico = servico
        self.http_status = http_status
        self.result_code = result_code
        self.erros = erros or []
        self.rede = rede  # True = falha de rede/timeout (resultado desconhecido)


class AGTClient:
    # Serviço -> (versão do schema, timeout (ligar, ler), repetível?)
    # ATENÇÃO: confirmar as versões na documentação AGT vigente.
    SERVICOS = {
        "listarSeries":   {"schema": "2.0", "timeout": (5, 30), "retry": True},
        "solicitarSerie": {"schema": "2.0", "timeout": (5, 30), "retry": False},
        "registarFactura": {"schema": "2.0", "timeout": (5, 45), "retry": False},
        "obterEstado":    {"schema": "1.0", "timeout": (5, 30), "retry": True},
    }
    _HTTP_REPETIVEIS = {502, 503, 504}
    _MAX_TENTATIVAS = 3

    def __init__(self, session: Optional[requests.Session] = None):
        ambiente = str(getattr(settings, "AGT_ENVIRONMENT", "")).strip().upper()
        if ambiente == "PRODUCTION":
            base_url = getattr(settings, "AGT_BASE_URL_PRODUCAO", "")
        elif ambiente in {"HOMOLOGACAO", "HOMOLOGAÇÃO"}:
            base_url = getattr(settings, "AGT_BASE_URL_HOMOLOGACAO", "")
        else:
            raise FiscalServiceError(
                "AGT_ENVIRONMENT inválido. Defina explicitamente HOMOLOGACAO ou "
                "PRODUCTION nas configurações do ambiente."
            )
        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url.startswith("https://"):
            raise FiscalServiceError("A URL base da AGT tem de estar configurada e usar HTTPS.")

        self.ambiente = ambiente
        self.base_url = base_url
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    # Configuração
    # ------------------------------------------------------------------
    @staticmethod
    def credenciais_configuradas() -> bool:
        return bool((getattr(settings, "AGT_API_USERNAME", "") or "").strip()
                    and (getattr(settings, "AGT_API_PASSWORD", "") or "").strip())

    @staticmethod
    def _credenciais() -> tuple:
        username = (getattr(settings, "AGT_API_USERNAME", "") or "").strip()
        password = getattr(settings, "AGT_API_PASSWORD", "") or ""
        if not username or not password.strip():
            raise FiscalServiceError(
                "Credenciais da API AGT não configuradas no ambiente. Defina "
                "AGT_API_USERNAME e AGT_API_PASSWORD no .env (emitidas pela AGT "
                "ao produtor do software)."
            )
        if ":" in username:
            raise FiscalServiceError("AGT_API_USERNAME não pode conter ':' (Basic Auth).")
        return username, password

    @staticmethod
    def _config_tenant() -> AssinaturaDigital:
        config = AssinaturaDigital.obter_configuracao()
        if not config or not config.esta_configurada:
            raise FiscalServiceError(
                "Chave do contribuinte não configurada para este tenant. "
                "Configure-a no admin global (Fiscal → Chaves fiscais das empresas)."
            )
        if not config.nif_contribuinte:
            raise FiscalServiceError("NIF do contribuinte não definido para este tenant.")
        return config

    # ------------------------------------------------------------------
    # Núcleo HTTP
    # ------------------------------------------------------------------
    def _chamar(self, servico: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        meta = self.SERVICOS[servico]
        url = f"{self.base_url}/{servico}"

        # Inicializar sempre: os outros serviços também passam por _chamar().
        captura_payload = None

        if (
            servico == "registarFactura"
            and isinstance(payload, dict)
            and isinstance(payload.get("documents"), list)
        ):
            try:
                captura_payload = PayloadInspectorService.registar_payload(
                    payload=payload,
                    endpoint=url,
                    ambiente=self.ambiente,
                )
            except Exception:
                logger.exception(
                    "Falha ao registar payload de registarFactura no Inspector AGT."
                )
                
        try:
            auth = self._credenciais()
        except Exception as exc:
            if captura_payload:
                try:
                    PayloadInspectorService.marcar_falha(captura_payload, exc, pedido_enviado=False)
                except Exception:
                    logger.exception("Falha ao actualizar o registo do Inspector AGT.")
            raise

        tentativas = self._MAX_TENTATIVAS if meta["retry"] else 1
        ultimo_erro: Optional[AGTError] = None

        for n in range(1, tentativas + 1):
            try:
                resp = self._session.post(
                    url, json=payload, auth=auth, timeout=meta["timeout"],
                    headers={"Accept": "application/json"},
                )
            except requests.RequestException as exc:
                if captura_payload and n >= tentativas:
                    try:
                        PayloadInspectorService.marcar_falha(
                            captura_payload,
                            (
                                "Falha de rede durante a submissão. "
                                "Não foi possível confirmar se a AGT recebeu o pedido. "
                                f"Tipo de erro: {type(exc).__name__}."
                            ),
                            pedido_enviado=True,
                        )
                    except Exception:
                        logger.exception(
                            "Falha ao actualizar o registo de rede no Inspector AGT."
                        )
                ultimo_erro = AGTError(
                    f"Não foi possível contactar a AGT ({servico}): {exc}",
                    servico=servico, rede=True,
                )
                logger.warning("AGT %s: falha de rede (tentativa %d/%d): %s",
                               servico, n, tentativas, type(exc).__name__)
            else:
                if resp.status_code in self._HTTP_REPETIVEIS and n < tentativas:
                    ultimo_erro = AGTError(
                        f"AGT indisponível (HTTP {resp.status_code}) em {servico}.",
                        servico=servico, http_status=resp.status_code, rede=True,
                    )
                else:
                    if captura_payload:
                        try:
                            PayloadInspectorService.registar_resposta(captura_payload, resp)
                        except Exception:
                            logger.exception("Falha ao guardar a resposta do Inspector AGT.")
                    return self._ler_resposta(resp, servico)
            if n < tentativas:
                time.sleep(2 ** (n - 1))  # 1s, 2s
        raise ultimo_erro


    
    @classmethod
    def _ler_resposta(cls, resp: requests.Response, servico: str,) -> Dict[str, Any]:
        """Interpreta respostas AGT e distingue falhas HTTP de JSON inválido."""

        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        corpo = (resp.text or "").strip()
        corpo_resumido = " ".join(corpo.split())[:300]

        # HTTP 401: provável falha de autenticação/autorização HTTP.
        # Não tentar interpretar primeiro a resposta como JSON.
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
                f"A AGT recusou a autenticação/autorização HTTP 401 "
                f"no serviço {servico}. Verifique as credenciais Basic Auth "
                "do produtor de software, o ambiente e o endpoint configurado. "
                "Consulte o log técnico para obter mais detalhes.",
                servico=servico,
                http_status=status,
                result_code="HTTP_401",
            )

        # Para outros códigos, tentar interpretar a resposta como JSON.
        try:
            data = resp.json()
        except ValueError as exc:
            logger.error(
                "Resposta não JSON da AGT. Serviço=%s; HTTP=%s; "
                "Content-Type=%s; URL=%s; corpo=%s",
                servico,
                status,
                content_type or "(não indicado)",
                resp.url,
                corpo_resumido or "(resposta vazia)",
            )

            raise AGTError(
                f"A AGT devolveu uma resposta que não é JSON "
                f"em {servico} (HTTP {status}).",
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

        # Preservar o detalhe de erros devolvidos em JSON por códigos HTTP de erro.
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
        out = []
        for erro in erros:
            if isinstance(erro, dict):
                codigo = erro.get("idError") or erro.get("errorCode") or erro.get("code") or "AGT"
                desc = (erro.get("descriptionError") or erro.get("errorDescription")
                        or erro.get("message") or "sem detalhe")
                out.append(f"{codigo}: {desc}")
            else:
                out.append(str(erro))
        return out

    def _exigir_sucesso(self, data: Dict[str, Any], servico: str, mensagem: str) -> None:
        """resultCode == '1' e HTTP 200 (listarSeries / solicitarSerie)."""
        http = data.get("_http_status")
        code = str(data.get("resultCode", ""))
        if http == 200 and code == "1":
            return
        erros = self.detalhar_erros(data)
        raise AGTError(
            f"{mensagem} (HTTP {http}, resultCode={code or 'ausente'}): "
            f"{'; '.join(erros) or 'sem detalhe'}",
            servico=servico, http_status=http, result_code=code, erros=erros,
        )

    def _envelope(self, servico: str, config: AssinaturaDigital,
                  assinatura_campos: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "schemaVersion": self.SERVICOS[servico]["schema"],
            "taxRegistrationNumber": config.nif_contribuinte,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": AssinaturaSoftwareService.montar_software_info(),
        }
        payload.update(extra)
        payload["jwsSignature"] = AssinaturaDigitalService.assinar_requisicao(assinatura_campos)
        return payload

    # ------------------------------------------------------------------
    # Serviços
    # ------------------------------------------------------------------
    def listar_series(self, *, series_year: Optional[int] = None,
                      document_type: Optional[str] = None,
                      series_status: Optional[str] = None,
                      establishment_number: str = "SEDE") -> List[Dict[str, Any]]:
        """listarSeries → lista de séries (`seriesInfo`)."""
        config = self._config_tenant()
        extra: Dict[str, Any] = {"establishmentNumber": establishment_number}
        if series_year:
            extra["seriesYear"] = series_year
        if document_type:
            extra["documentType"] = document_type
        if series_status:
            extra["seriesStatus"] = series_status
        payload = self._envelope(
            "listarSeries", config,
            {"taxRegistrationNumber": config.nif_contribuinte}, extra,
        )
        data = self._chamar("listarSeries", payload)
        self._exigir_sucesso(data, "listarSeries", "listarSeries não confirmou sucesso")
        # A documentação publicada tem a grafia `seriresInfo` no exemplo.
        info = data.get("seriesInfo") or data.get("seriresInfo") or []
        if not isinstance(info, list):
            raise AGTError("listarSeries sem lista de séries válida.", servico="listarSeries")
        return info

    def solicitar_serie(self, *, document_type: str, series_year: int,
                        establishment_number: str, contingency: bool = False) -> Dict[str, Any]:
        """solicitarSerie → `seriesFEResult`."""
        config = self._config_tenant()
        indicador = "C" if contingency else "N"
        assinados = {
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
        payload = self._envelope("solicitarSerie", config, assinados, extra)
        data = self._chamar("solicitarSerie", payload)
        self._exigir_sucesso(data, "solicitarSerie", "A AGT não autorizou a criação da série")
        resultado = data.get("seriesFEResult")
        if not isinstance(resultado, dict):
            raise AGTError("A AGT indicou sucesso mas sem seriesFEResult válido.",
                           servico="solicitarSerie")
        return resultado

    def registar_factura(self, documents: List[Dict[str, Any]], *,
                         submission_uuid: Optional[str] = None) -> Dict[str, Any]:
        """
        registarFactura. Devolve {"requestID": ..., "submissionUUID": ...}.
        Passe sempre o mesmo `submission_uuid` ao repetir a submissão do mesmo
        lote (persistido pelo chamador) para a AGT conseguir reconhecê-la.
        """
        if not documents:
            raise FiscalServiceError("registarFactura sem documentos.")
        config = self._config_tenant()
        sub_uuid = submission_uuid or str(uuid.uuid4())
        extra = {
            "submissionUUID": sub_uuid,
            "numberOfEntries": len(documents),
            "documents": documents,
        }
        assinados = {"taxRegistrationNumber": config.nif_contribuinte,
                     "submissionUUID": sub_uuid}
        payload = self._envelope("registarFactura", config, assinados, extra)
        data = self._chamar("registarFactura", payload)

        http = data.get("_http_status")
        request_id = data.get("requestID")
        erros = self.detalhar_erros(data)
        if http == 200 and request_id and not erros:
            return {"requestID": request_id, "submissionUUID": sub_uuid}
        raise AGTError(
            f"A AGT não aceitou a submissão (HTTP {http}): {'; '.join(erros) or 'sem requestID'}",
            servico="registarFactura", http_status=http,
            result_code=str(data.get("resultCode", "")), erros=erros,
        )

    def obter_estado(self, request_id: str) -> Dict[str, Any]:
        """obterEstado → resposta bruta (resultCode, documentStatusList, ...)."""
        if not request_id:
            raise FiscalServiceError("obterEstado sem requestID.")
        config = self._config_tenant()
        assinados = {"taxRegistrationNumber": config.nif_contribuinte,
                     "requestID": request_id}
        payload = self._envelope("obterEstado", config, assinados, {"requestID": request_id})
        data = self._chamar("obterEstado", payload)
        if data.get("_http_status") != 200:
            erros = self.detalhar_erros(data)
            raise AGTError(
                f"obterEstado falhou (HTTP {data.get('_http_status')}): {'; '.join(erros) or 'sem detalhe'}",
                servico="obterEstado", http_status=data.get("_http_status"),
                result_code=str(data.get("resultCode", "")), erros=erros,
            )
        return data
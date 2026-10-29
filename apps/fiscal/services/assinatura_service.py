# apps/fiscal/services/assinatura_service.py
"""
Serviço de assinatura fiscal AGT.

Duas classes, duas responsabilidades e duas chaves totalmente separadas:

- AssinaturaSoftwareService: assina o objeto softwareInfo (jwsSoftwareSignature)
  com a chave ÚNICA da SOTARQ, lida do ambiente. Chamado uma vez por
  requisição à API da AGT, igual para qualquer tenant.

- AssinaturaDigitalService: assina documentos (jwsDocumentSignature) e
  requisições (jwsSignature) com a chave DO CONTRIBUINTE, configurada por
  tenant. Também gere a cadeia de hash interna do VistoGest (auditoria
  própria, independente da validação remota da AGT).

RIGOR: RS256 (JWS) = RSASSA-PKCS1-v1_5 + SHA-256, conforme RFC 7518.
NÃO é RSA-PSS — essa era a implementação anterior e estava incorrecta;
um validador RS256 padrão (como o da AGT) rejeita assinaturas PSS.
"""

import base64
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.utility.crypto import AESService
from .utils import FiscalServiceError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django_tenants.utils import get_public_schema_name
from apps.empresas.services import obter_empresa_do_schema
from apps.fiscal.utility import chaves


logger = logging.getLogger('fiscal.assinatura')


# =====================================
# Helpers JWS (RFC 7515 / RFC 7518, RS256)
# =====================================

def _b64url(data: bytes) -> str:
    """Base64URL sem padding, conforme JWS compact serialization."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _json_canonico(obj: Dict[str, Any]) -> bytes:
    """
    Serialização JSON canónica para assinatura: chaves não reordenadas
    (mantém a ordem de inserção do dict, que deve seguir a ordem dos
    campos tal como listados no Anexo I para cada assinatura), sem
    espaços, UTF-8.
    """
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def gerar_jws_rs256(payload: Dict[str, Any], private_key_pem: str) -> str:
    """Gera um JWS compacto (header.payload.signature) usando RS256."""
    header = {"alg": "RS256", "typ": "JWT"}
    header_b64 = _b64url(_json_canonico(header))
    payload_b64 = _b64url(_json_canonico(payload))
    signing_input = f"{header_b64}.{payload_b64}".encode('ascii')

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'), password=None
    )
    assinatura = private_key.sign(
        signing_input,
        padding.PKCS1v15(),   # RS256 real — não PSS
        hashes.SHA256()
    )
    return f"{header_b64}.{payload_b64}.{_b64url(assinatura)}"


def verificar_jws_rs256(jws: str, public_key_pem: str) -> Dict[str, Any]:
    """Verifica um JWS RS256 e devolve o payload decodificado se válido."""
    try:
        header_b64, payload_b64, sig_b64 = jws.split('.')
    except ValueError:
        raise FiscalServiceError("JWS mal formado (esperado header.payload.signature).")

    def _pad(s):
        return s + '=' * (-len(s) % 4)

    signing_input = f"{header_b64}.{payload_b64}".encode('ascii')
    assinatura = base64.urlsafe_b64decode(_pad(sig_b64))

    public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    public_key.verify(assinatura, signing_input, padding.PKCS1v15(), hashes.SHA256())

    payload_json = base64.urlsafe_b64decode(_pad(payload_b64))
    return json.loads(payload_json)


# =====================================
# Chave do SOFTWARE (SOTARQ) — única, vem do ambiente
# =====================================

class AssinaturaSoftwareService:
    """
    Assina o objeto `softwareInfo` (jwsSoftwareSignature) com a chave ÚNICA
    da SOTARQ. Esta chave é a mesma para todos os tenants e NUNCA é gerada
    em runtime nem guardada em base de dados — vive apenas no ambiente do
    servidor (AGT_SOFTWARE_PRIVATE_KEY_PEM ou _PATH).
    """

    @staticmethod
    def _carregar_chave_privada() -> str:
        pem = getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY_PEM', '')
        if pem:
            return pem.replace('\\n', '\n')

        path = getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY_PATH', '')
        if path:
            try:
                with open(path, 'r') as f:
                    return f.read()
            except FileNotFoundError:
                pass

        raise FiscalServiceError(
            "Chave privada do Software não configurada. Defina "
            "AGT_SOFTWARE_PRIVATE_KEY_PEM ou AGT_SOFTWARE_PRIVATE_KEY_PATH no ambiente."
        )

    @staticmethod
    def _software_info_detail() -> Dict[str, str]:
        return {
            "productId": settings.AGT_SOFTWARE_PRODUCT_ID,
            "productVersion": settings.AGT_SOFTWARE_PRODUCT_VERSION,
            "softwareValidationNumber": settings.AGT_SOFTWARE_VALIDATION_NUMBER,
        }

    @classmethod
    def montar_software_info(cls) -> Dict[str, Any]:
        """
        Monta o objeto `softwareInfo` completo do Anexo I: softwareInfoDetail
        + jwsSoftwareSignature (assinatura de todos os campos de detail).
        """
        detail = cls._software_info_detail()
        private_pem = cls._carregar_chave_privada()
        return {
            "softwareInfoDetail": detail,
            "jwsSoftwareSignature": gerar_jws_rs256(detail, private_pem),
        }


# =====================================
# Chave do CONTRIBUINTE (AGT, por tenant) + cadeia interna
# =====================================

class AssinaturaDigitalService:
    """
    Gestão da chave do contribuinte (por tenant, emitida pela AGT) e da
    cadeia de integridade interna bdo VistoGest (auditoria própria).
    """

    # -------------------------------------------------------------
    # Configuração da chave (recebida da AGT, nunca gerada aqui)
    # -------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def configurar_chave_contribuinte( chave_privada_pem: str, chave_publica_pem: Optional[str] = None, usuario=None,) -> AssinaturaDigital:
        """Guarda as chaves dentro do tenant; o NIF vem apenas de Empresa."""
        schema = getattr(connection, "schema_name", "public")
        if schema == get_public_schema_name():
            raise FiscalServiceError(
                "Não é permitido configurar chaves de contribuinte no schema public."
            )

        try:
            empresa = obter_empresa_do_schema()
        except DjangoValidationError as exc:
            raise FiscalServiceError(
                "Não foi possível identificar a empresa do tenant activo."
            ) from exc

        if not empresa.nif:
            raise FiscalServiceError(
                "A empresa não tem NIF no registo oficial. Configure primeiro Empresa.nif."
            )
        if not (chave_privada_pem or "").strip():
            raise FiscalServiceError("A chave privada do contribuinte é obrigatória.")

        # Criar o singleton se necessário e depois bloquear a linha na transacção.
        AssinaturaDigital.objects.get_or_create(pk=1)
        config = AssinaturaDigital.objects.select_for_update().get(pk=1)
        autor = usuario.get_username() if usuario and hasattr(usuario, "get_username") else ""

        try:
            config.definir_chaves(
                chave_privada_pem=chave_privada_pem,
                chave_publica_pem=chave_publica_pem,
                autor=autor,
            )
            config.refresh_from_db()
            problemas = config.verificar_integridade()
        except DjangoValidationError as exc:
            detalhe = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            raise FiscalServiceError(detalhe) from exc
        except (ValueError, TypeError) as exc:
            raise FiscalServiceError(str(exc)) from exc

        if problemas:
            raise FiscalServiceError(
                "Chaves fiscais inconsistentes: " + "; ".join(problemas)
            )

        logger.info(
            "Chaves do contribuinte actualizadas para schema=%s por user_id=%s",
            schema,
            getattr(usuario, "pk", None),
        )
        return config
    

    @staticmethod
    def _obter_chave_privada_contribuinte() -> str:
        config = AssinaturaDigital.get_solo()
        try:
            chave_privada = config.obter_chave_privada()
        except DjangoValidationError as exc:
            detalhe = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            raise FiscalServiceError(
                "Chaves fiscais inconsistentes: " + detalhe
            ) from exc
        except Exception as exc:
            raise FiscalServiceError(
                "Não foi possível validar a chave privada do contribuinte."
            ) from exc

        # gerar_jws_rs256() recebe PEM em texto, não um objecto RSAPrivateKey.
        return chaves.pem_privada(chave_privada)

    # -------------------------------------------------------------
    # jwsDocumentSignature — assina UM documento
    # -------------------------------------------------------------

    @classmethod
    def assinar_documento(cls, dados_documento: Dict[str, Any]) -> str:
        """
        Assina os campos obrigatórios de um documento (Anexo I):
        documentNo, taxRegistrationNumber, documentType, documentDate,
        customerTaxID, customerCountry, companyName, documentTotals.
        `dados_documento` deve conter exactamente estes campos, na ordem
        listada no Decreto.
        """
        private_pem = cls._obter_chave_privada_contribuinte()
        return gerar_jws_rs256(dados_documento, private_pem)

    # -------------------------------------------------------------
    # jwsSignature — assina uma requisição (payload varia por serviço)
    # -------------------------------------------------------------

    @classmethod
    def assinar_requisicao(cls, campos_requisicao: Dict[str, Any]) -> str:
        """
        Assina o payload de assinatura de requisição — os campos exactos
        variam por serviço (ex.: taxRegistrationNumber+submissionUUID em
        registarFactura; taxRegistrationNumber+requestID em obterEstado).
        Quem chama decide o dict; este método só assina.
        """
        private_pem = cls._obter_chave_privada_contribuinte()
        return gerar_jws_rs256(campos_requisicao, private_pem)

    # -------------------------------------------------------------
    # Cadeia de integridade INTERNA (não é a cadeia da AGT)
    # -------------------------------------------------------------

    @staticmethod
    def calcular_hash_documento(doc: Dict[str, Any], hash_anterior: str = "") -> str:
        """Hash SHA-256 interno para a cadeia própria de auditoria do VistoGest."""
        dados = dict(doc)
        if hash_anterior:
            dados['hash_anterior'] = hash_anterior
        dados_json = json.dumps(dados, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(dados_json.encode('utf-8')).hexdigest()

    @classmethod
    @transaction.atomic
    def atualizar_cadeia_interna(cls, serie: str, numero_documento: str, novo_hash: str) -> None:
        """Avança a cadeia interna de uma série após confirmar um documento."""
        config, _ = AssinaturaDigital.objects.select_for_update().get_or_create(pk=1)
        meta = config.dados_series_fiscais.get(serie, {})
        meta.update({
            'ultimo_hash': novo_hash,
            'ultimo_documento': numero_documento,
            'data_ultima_assinatura': datetime.now().isoformat(),
        })
        config.dados_series_fiscais[serie] = meta
        config.ultimo_hash = novo_hash
        config.save(update_fields=['dados_series_fiscais', 'ultimo_hash'])

    @staticmethod
    def obter_hash_anterior(serie: str) -> str:
        config = AssinaturaDigital.obter_configuracao()
        if not config:
            return ""
        return config.dados_series_fiscais.get(serie, {}).get('ultimo_hash', "")



class VerificadorIntegridadeService:
    """
    Verifica a integridade fiscal do tenant activo. Duas checagens
    independentes: (1) cadeia de hash interna do VistoGest, (2) validade
    da assinatura JWS de cada documento com a chave pública do contribuinte.
    """

    @staticmethod
    def verificar_tenant() -> tuple[bool, list[str]]:
        from apps.fiscal.models import DocumentoFiscal

        erros = []
        config = AssinaturaDigital.obter_configuracao()
        if not config:
            return False, ["Configuração de assinatura fiscal inexistente para este tenant."]

        chave_publica_pem = config.chave_contribuinte_publica
        docs = DocumentoFiscal.objects.filter(status='confirmed').order_by(
            'tipo_documento', 'serie', 'numero'
        )

        for tipo, serie in docs.values_list('tipo_documento', 'serie').distinct():
            hash_anterior_esperado = ""
            for doc in docs.filter(tipo_documento=tipo, serie=serie):
                # 1) Cadeia interna
                if doc.hash_anterior != hash_anterior_esperado:
                    erros.append(
                        f"Quebra de cadeia interna: {doc.numero_documento} "
                        f"esperava hash anterior '{hash_anterior_esperado[:10]}', "
                        f"tem '{(doc.hash_anterior or '')[:10]}'."
                    )
                hash_anterior_esperado = doc.hash_documento

                # 2) Assinatura JWS (se houver chave pública configurada)
                if chave_publica_pem and doc.assinatura_digital:
                    try:
                        verificar_jws_rs256(doc.assinatura_digital, chave_publica_pem)
                    except Exception:
                        erros.append(f"Assinatura JWS inválida em {doc.numero_documento}.")

        return (len(erros) == 0), erros



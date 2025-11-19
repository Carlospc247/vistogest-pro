# apps/fiscal/servicos/assinatura_service.py
import base64
import hashlib
import logging
from typing import Dict
from django.db import transaction
from django.utils import timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.services import FiscalServiceError
from apps.fiscal.utility.crypto import AESService
from apps.core.models import Empresa
from .utils import gerar_rsa_local

logger = logging.getLogger(__name__)


class AssinaturaDigitalService:
    """Serviço oficial AGT para assinatura digital de documentos."""

    # ----------------------------------------------------------------------
    # 1) GERAÇÃO DE CHAVES RSA POR EMPRESA
    # ----------------------------------------------------------------------
    @staticmethod
    def gerar_chaves_rsa(empresa: Empresa, tamanho_chave: int = 2048) -> AssinaturaDigital:
        """Gera par RSA e guarda na DB (chave privada encriptada)."""
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=tamanho_chave,
            )
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        except Exception:
            private_pem, public_pem = gerar_rsa_local()  # fallback local

        assinatura, _ = AssinaturaDigital.objects.update_or_create(
            empresa=empresa,
            defaults={
                "chave_privada": AESService.encrypt(private_pem.decode()),
                "chave_publica": public_pem.decode(),
                "data_geracao": timezone.now(),
                "dados_series_fiscais": {},  # garante dict default
            },
        )
        return assinatura

    # ----------------------------------------------------------------------
    # 2) EXPORTA CHAVE PÚBLICA
    # ----------------------------------------------------------------------
    @staticmethod
    def exportar_chave_publica_pem(empresa: Empresa) -> bytes:
        """Retorna a chave pública da empresa em bytes (UTF-8)."""
        assinatura = AssinaturaDigital.objects.filter(empresa=empresa).first()
        if not assinatura or not assinatura.chave_publica:
            raise FiscalServiceError("Chave pública inexistente.")
        return assinatura.chave_publica.encode("utf-8")

    # ----------------------------------------------------------------------
    # 3) HASH DETERMINÍSTICO (cadeia AGT)
    # ----------------------------------------------------------------------
    @staticmethod
    def calcular_hash_documento(doc: Dict, hash_anterior: str = "") -> str:
        """Calcula hash base64 de um documento, usando hash anterior."""
        ordenado = {
            "data": doc.get("data", ""),
            "tipo_documento": doc.get("tipo_documento", ""),
            "serie": doc.get("serie", ""),
            "numero": str(doc.get("numero", "")),
            "valor_total": str(doc.get("valor_total", "0.00")),
            "hash_anterior": hash_anterior,
        }
        texto = ";".join(f"{k}:{v}" for k, v in sorted(ordenado.items()))
        digest = hashlib.sha256(texto.encode("utf-8")).digest()
        return base64.b64encode(digest).decode("utf-8")

    # ----------------------------------------------------------------------
    # 4) GERA ATCUD
    # ----------------------------------------------------------------------
    @staticmethod
    def gerar_atcud(empresa: Empresa, serie: str, numero: str, hash_: str) -> str:
        """Gera ATCUD conforme padrão AGT (hash SHA256)."""
        nif = empresa.nif or empresa.numero_contribuinte or ""
        base = f"{nif}|{serie}|{numero}|{hash_}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest().upper()

    # ----------------------------------------------------------------------
    # 5) ASSINATURA DE DOCUMENTO
    # ----------------------------------------------------------------------
    @staticmethod
    def assinar_documento(empresa: Empresa, doc: Dict) -> Dict[str, str]:
        """
        Assina documento digitalmente e atualiza cadeia de hashes por série.
        Retorna: {hash, assinatura (base64), hash_anterior, atcud}
        """
        try:
            with transaction.atomic():
                assinatura = AssinaturaDigital.objects.select_for_update().get(empresa=empresa)
                serie = doc.get("serie", "DEFAULT")
                numero = str(doc.get("numero", "0"))
                meta = assinatura.dados_series_fiscais.get(serie, {})

                hash_anterior = meta.get("ultimo_hash", "")

                # gera novo hash
                novo_hash = AssinaturaDigitalService.calcular_hash_documento(doc, hash_anterior)

                if not assinatura.chave_privada:
                    raise FiscalServiceError("Chave privada não configurada.")

                # descriptografa chave privada
                private_pem = AESService.decrypt(assinatura.chave_privada)
                private_key = serialization.load_pem_private_key(
                    private_pem.encode("utf-8"),
                    password=None,
                )

                assinatura_bin = private_key.sign(
                    novo_hash.encode("utf-8"),
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
                assinatura_b64 = base64.b64encode(assinatura_bin).decode("utf-8")

                # Gera ATCUD
                atcud = AssinaturaDigitalService.gerar_atcud(empresa, serie, numero, novo_hash)

                # Atualiza metadados da série
                meta.update({
                    "ultimo_hash": novo_hash,
                    "ultimo_documento": numero,
                    "data_ultima_assinatura": timezone.now().isoformat(),
                    "ultimo_atcud": atcud,
                })
                assinatura.dados_series_fiscais[serie] = meta
                assinatura.ultimo_hash = novo_hash
                assinatura.save(update_fields=["dados_series_fiscais", "ultimo_hash"])

                return {
                    "hash": novo_hash,
                    "assinatura": assinatura_b64,
                    "hash_anterior": hash_anterior,
                    "atcud": atcud,
                }

        except AssinaturaDigital.DoesNotExist:
            raise FiscalServiceError("Assinatura digital não configurada.")
        except Exception as e:
            logger.exception("Erro ao assinar documento")
            raise FiscalServiceError(f"Erro ao assinar documento: {e}")

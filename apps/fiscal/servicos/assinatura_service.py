# apps/fiscal/servicos/assinatura_service.py
import base64
import hashlib
import json
import logging
from typing import Dict, Optional
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet, InvalidToken

from apps.core.models import Empresa
from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.services import FiscalServiceError



logger = logging.getLogger(__name__)

# helper: Fernet instance from env
def _get_fernet() -> Fernet:
    key = getattr(settings, "FERNET_KEY", None)
    if not key:
        raise FiscalServiceError("FERNET_KEY não configurada no settings.")
    return Fernet(key.encode() if isinstance(key, str) else key)

class AssinaturaDigitalService:
    """Serviço leve e testável para geração/assinatura compatível AGT."""

    @staticmethod
    def _encrypt_private(private_pem: bytes) -> str:
        f = _get_fernet()
        token = f.encrypt(private_pem)
        return base64.b64encode(token).decode('utf-8')

    @staticmethod
    def _decrypt_private(token_b64: str) -> bytes:
        try:
            f = _get_fernet()
            token = base64.b64decode(token_b64)
            return f.decrypt(token)
        except (InvalidToken, ValueError) as e:
            logger.exception("Erro desencriptando chave privada")
            raise FiscalServiceError("Chave privada corrompida ou FERNET_KEY inválida.")

    @staticmethod
    def gerar_chaves_rsa(empresa: Empresa, tamanho_chave: int = 2048) -> AssinaturaDigital:
        """Gera par RSA, grava chave pública em claro e privada encriptada."""
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=tamanho_chave,
                #backend=default_backend()
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

            with transaction.atomic():
                assinatura, created = AssinaturaDigital.objects.get_or_create(
                    empresa=empresa,
                    defaults={
                        'chave_privada': AssinaturaDigitalService._encrypt_private(private_pem),
                        'chave_publica': public_pem.decode('utf-8'),
                        'dados_series_fiscais': {}
                    }
                )

                if not created:
                    # Proteção: só permitir regeneração se o utilizador for superuser/admin — isso é checado na view/admin
                    assinatura.chave_privada = AssinaturaDigitalService._encrypt_private(private_pem)
                    assinatura.chave_publica = public_pem.decode('utf-8')
                    ds = assinatura.dados_series_fiscais or {}
                    ds['_global_public_version'] = ds.get('_global_public_version', 0) + 1
                    assinatura.dados_series_fiscais = ds

                assinatura.ultimo_hash = assinatura.ultimo_hash or ''
                assinatura.data_geracao = timezone.now()
                assinatura.save()

            logger.info("Chaves RSA geradas/atualizadas", extra={'empresa_id': empresa.id, 'created': created})
            return assinatura

        except Exception as e:
            logger.exception("Erro ao gerar chaves RSA")
            raise FiscalServiceError(f"Erro na geração de chaves RSA: {e}")

    @staticmethod
    def exportar_chave_publica_pem(empresa: Empresa) -> bytes:
        assinatura = AssinaturaDigital.objects.filter(empresa=empresa).first()
        if not assinatura or not assinatura.chave_publica:
            raise FiscalServiceError("Chave pública não encontrada.")
        return assinatura.chave_publica.encode('utf-8')

    @staticmethod
    def _calcular_hash_documento(dados_documento: Dict, hash_anterior: str = "") -> str:
        campos = {
            'data': dados_documento.get('data', ''),
            'tipo_documento': dados_documento.get('tipo_documento', ''),
            'serie': dados_documento.get('serie', ''),
            'numero': str(dados_documento.get('numero', '')),
            'valor_total': str(dados_documento.get('valor_total', '0.00')),
            'hash_anterior': hash_anterior or ''
        }
        string_hash = ';'.join([f"{k}:{v}" for k, v in sorted(campos.items())])
        digest = hashlib.sha256(string_hash.encode('utf-8')).digest()
        return base64.b64encode(digest).decode('utf-8')

    @staticmethod
    def _gerar_atcud(empresa: Empresa, serie: str, numero: str, novo_hash: str) -> str:
        nif = getattr(empresa, 'nif', '') or getattr(empresa, 'numero_contribuinte', '')
        base = f"{nif}|{serie}|{numero}|{novo_hash}"
        return hashlib.sha256(base.encode('utf-8')).hexdigest().upper()

    @staticmethod
    def assinar_documento(empresa: Empresa, dados_documento: Dict) -> Dict[str, str]:
        """
        Retorna: { hash, assinatura (base64), hash_anterior, atcud }.
        Atualiza dados_series_fiscais e ultimo_hash atomically.
        """
        try:
            with transaction.atomic():
                assinatura = AssinaturaDigital.objects.select_for_update().get(empresa=empresa)
                serie = dados_documento.get('serie', 'DEFAULT')
                numero = str(dados_documento.get('numero', '0'))
                serie_meta = assinatura.dados_series_fiscais.get(serie, {}) if assinatura.dados_series_fiscais else {}
                ultimo_hash = serie_meta.get('ultimo_hash') or assinatura.ultimo_hash or ''

                novo_hash = AssinaturaDigitalService._calcular_hash_documento(dados_documento, ultimo_hash)

                if not assinatura.chave_privada:
                    raise FiscalServiceError("Chave privada não configurada.")

                private_pem = AssinaturaDigitalService._decrypt_private(assinatura.chave_privada)
                private_key = serialization.load_pem_private_key(private_pem, password=None)

                signature = private_key.sign(
                    novo_hash.encode('utf-8'),
                    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                    hashes.SHA256()
                )
                assinatura_b64 = base64.b64encode(signature).decode('utf-8')
                atcud = AssinaturaDigitalService._gerar_atcud(empresa, serie, numero, novo_hash)

                # Atualiza metadados da série
                ds = assinatura.dados_series_fiscais or {}
                sm = ds.get(serie, {})
                sm.update({
                    'ultimo_hash': novo_hash,
                    'ultimo_documento': numero,
                    'data_ultima_assinatura': timezone.now().isoformat(),
                    'ultimo_atcud': atcud
                })
                ds[serie] = sm
                assinatura.dados_series_fiscais = ds
                assinatura.ultimo_hash = novo_hash
                assinatura.save()

                return {
                    'hash': novo_hash,
                    'assinatura': assinatura_b64,
                    'hash_anterior': ultimo_hash,
                    'atcud': atcud
                }

        except AssinaturaDigital.DoesNotExist:
            raise FiscalServiceError("Assinatura digital não configurada.")
        except Exception as e:
            logger.exception("Erro ao assinar documento")
            raise FiscalServiceError(f"Erro na assinatura: {e}")

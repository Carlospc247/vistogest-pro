# apps/integracoes/services/crypto.py
import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class ChaveNaoConfigurada(RuntimeError):
    pass


def _fernet() -> MultiFernet:
    """ENCRYPTION_KEY: uma chave Fernet, ou várias separadas por vírgula (a 1.ª cifra; todas decifram)."""
    bruto = getattr(settings, 'ENCRYPTION_KEY', None)
    if not bruto:
        raise ChaveNaoConfigurada(
            "ENCRYPTION_KEY não configurada. Gere uma com: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "e defina-a no .env.")
    chaves = bruto if isinstance(bruto, (list, tuple)) else str(bruto).split(',')
    return MultiFernet([Fernet(k.strip().encode()) for k in chaves if k.strip()])


def cifrar_dict(dados: dict) -> str:
    return _fernet().encrypt(json.dumps(dados).encode()).decode()


def decifrar_dict(token: str) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()).decode())
    except InvalidToken:
        raise ChaveNaoConfigurada("Não foi possível decifrar: a ENCRYPTION_KEY mudou ou os dados estão corrompidos.")

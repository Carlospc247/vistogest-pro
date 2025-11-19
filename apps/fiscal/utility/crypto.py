# apps/fiscal/utils/crypto.py
import os
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

FERNET_KEY = os.getenv('ASSINATURA_FERNET_KEY') or getattr(settings, 'ASSINATURA_FERNET_KEY', None)
if not FERNET_KEY:
    raise RuntimeError("ASSINATURA_FERNET_KEY is not set in environment")

fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

def encrypt_bytes(data: bytes) -> bytes:
    return fernet.encrypt(data)

def decrypt_bytes(token: bytes) -> bytes:
    try:
        return fernet.decrypt(token)
    except InvalidToken as e:
        raise ValueError("Invalid encryption token") from e


class AESService:
    @staticmethod
    def encrypt(text: str) -> str:
        return encrypt_bytes(text.encode()).decode()

    @staticmethod
    def decrypt(token: str) -> str:
        return decrypt_bytes(token.encode()).decode()


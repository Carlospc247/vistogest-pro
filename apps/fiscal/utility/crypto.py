import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# RIGOR SOTARQ: A AES_KEY agora pode ter qualquer tamanho, o KDF garante os 32 bytes fortes.
_RAW_KEY = os.getenv("AES_KEY")
if not _RAW_KEY:
    raise RuntimeError("ERRO CRÍTICO: AES_KEY (Cofre Mestre) não definida nas variáveis de ambiente.")

# Derivação de Chave (KDF) - Garante que a chave final seja sempre de 32 bytes estáveis
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=b'SOTARQ_FISCAL_SALT', # Salt fixo para consistência na descriptografia
    iterations=100000,
    backend=default_backend()
)
AES_KEY_FINAL = kdf.derive(_RAW_KEY.encode())

class AESService:
    """Serviço de Cofre Mestre para chaves privadas RSA (Padrão AGT)."""

    @staticmethod
    def encrypt(text: str) -> str:
        if not text: return ""
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(AES_KEY_FINAL), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ct = encryptor.update(text.encode()) + encryptor.finalize()
        # Retorna IV + Ciphertext em Base64
        return base64.b64encode(iv + ct).decode()

    @staticmethod
    def decrypt(token: str) -> str:
        if not token: return ""
        try:
            raw = base64.b64decode(token)
            iv, ct = raw[:16], raw[16:]
            cipher = Cipher(algorithms.AES(AES_KEY_FINAL), modes.CFB(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            return (decryptor.update(ct) + decryptor.finalize()).decode()
        except Exception as e:
            raise ValueError(f"Falha ao abrir o cofre fiscal (Chave Mestra Inválida ou Corrompida): {e}")
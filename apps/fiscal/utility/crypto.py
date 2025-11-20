# apps/fiscal/utils/crypto.py
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import base64, os

AES_KEY = os.getenv("AES_KEY")
if not AES_KEY:
    raise RuntimeError("AES_KEY não está definido no ambiente")

# Garantir 32 bytes para AES-256
key = AES_KEY.encode()[:32].ljust(32, b'0')

class AESService:
    @staticmethod
    def encrypt(text: str) -> str:
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(text.encode()) + encryptor.finalize()
        return base64.b64encode(iv + ct).decode()

    @staticmethod
    def decrypt(token: str) -> str:
        raw = base64.b64decode(token)
        iv, ct = raw[:16], raw[16:]
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
        decryptor = cipher.decryptor()
        return (decryptor.update(ct) + decryptor.finalize()).decode()


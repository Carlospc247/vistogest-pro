# apps/fiscal/utility/chaves.py
"""Chaves RSA do contribuinte: carregar, validar, serializar. Sem BD, sem tenant."""
import hashlib

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_AMOSTRA = b"sotarq-verificacao-de-par"


def carregar_privada(pem: str):
    try:
        chave = serialization.load_pem_private_key(pem.strip().encode(), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise ValueError("Chave privada inválida. Cole o PEM completo, sem palavra-passe.") from None
    if not isinstance(chave, rsa.RSAPrivateKey):
        raise ValueError("A chave privada tem de ser RSA.")
    if chave.key_size < 2048:
        raise ValueError("A chave RSA deve ter pelo menos 2048 bits.")
    return chave


def carregar_publica(pem: str):
    try:
        chave = serialization.load_pem_public_key(pem.strip().encode())
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise ValueError("Chave pública inválida. Cole o PEM completo.") from None
    if not isinstance(chave, rsa.RSAPublicKey):
        raise ValueError("A chave pública tem de ser RSA.")
    return chave


def validar_par(priv, pub) -> None:
    """Mesmo módulo/expoente e prova de assinatura RS256 (PKCS#1 v1.5 + SHA-256)."""
    if priv.public_key().public_numbers() != pub.public_numbers():
        raise ValueError("A chave pública não corresponde à chave privada.")
    try:
        assinatura = priv.sign(_AMOSTRA, padding.PKCS1v15(), hashes.SHA256())
        pub.verify(assinatura, _AMOSTRA, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise ValueError("O par de chaves falhou a prova de assinatura.") from None


def pem_publica(pub) -> str:
    return pub.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def pem_privada(priv) -> str:
    return priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def fingerprint(pub) -> str:
    der = pub.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()
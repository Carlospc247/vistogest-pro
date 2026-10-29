
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def gerar_chaves():
    """Gera um par RSA de 4096 bits para assinatura do software SOTARQ."""

    # Gerar par de chaves RSA
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    # Converter a chave privada para PEM
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    # Preparar a chave privada para a variável do ficheiro .env:
    # substituir as quebras de linha reais por \n literal.
    private_env = private_pem.replace("\n", r"\n")

    # Apresentar a variável pronta para copiar para o .env
    print("=" * 70)
    print("CHAVE PRIVADA — COPIAR PARA O .env")
    print("=" * 70)
    print(f'AGT_SOFTWARE_PRIVATE_KEY_PEM="{private_env}"')

    # Converter a chave pública para PEM normal
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    # Apresentar a chave pública com quebras de linha reais
    print()
    print("=" * 70)
    print("CHAVE PUBLICA — FORMATO PEM")
    print("=" * 70)
    print(public_pem, end="")


if __name__ == "__main__":
    gerar_chaves()

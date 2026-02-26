import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def generate_master_keys():
    print("--- A GERAR PAR DE CHAVES MESTRA SOTARQ (RSA 2048) ---\n")

    # 1. Criar pasta de backup se não existir
    backup_dir = "certs_backup"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    # 2. Gerar a chave privada
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 3. Serializar a Chave Privada (Formato PEM)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # 4. Serializar a Chave Pública (Formato PEM)
    public_key = private_key.public_key()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # --- SALVAMENTO EM FICHEIROS ---

    # Gravar .pem (Formato padrão para servidores)
    with open(os.path.join(backup_dir, "chave_privada.pem"), "wb") as f:
        f.write(pem_private)
    with open(os.path.join(backup_dir, "chave_publica.pem"), "wb") as f:
        f.write(pem_public)

    # Gravar .txt (Para visualização simples e upload manual)
    with open(os.path.join(backup_dir, "chave_privada.txt"), "w") as f:
        f.write(pem_private.decode('utf-8'))
    with open(os.path.join(backup_dir, "chave_publica.txt"), "w") as f:
        f.write(pem_public.decode('utf-8'))

    # --- PREPARAÇÃO PARA .ENV ---
    private_str = pem_private.decode('utf-8').replace('\n', '\\n')

    print(f"SUCESSO: Ficheiros gerados na pasta '{backup_dir}/'\n")
    print("COPIE A LINHA ABAIXO PARA O SEU .env (TUDO NUMA LINHA SÓ):")
    print("-" * 60)
    print(f'SOTARQ_PRIVATE_KEY="{private_str}"')
    print("-" * 60)
    
    print("\nCHAVE PÚBLICA (Para o Portal da AGT):")
    print("-" * 60)
    print(pem_public.decode('utf-8'))
    print("-" * 60)

if __name__ == "__main__":
    generate_master_keys()
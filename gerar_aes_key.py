import os
import base64

def gerar_aes_key():
    # Gera 32 bytes de entropia pura (padrão AES-256)
    chave_binaria = os.urandom(32)
    # Codifica em Base64 para ser armazenada como string no .env
    aes_key = base64.urlsafe_b64encode(chave_binaria).decode('utf-8')
    
    print("\n" + "="*50)
    print("CHAVE AES-256 PARA CRIPTOGRAFIA SIMÉTRICA")
    print("="*50)
    print(f"AES_KEY={aes_key}")
    print("="*50)
    print("AVISO: Guarde isto no .env. Se perder esta chave,")
    print("os dados encriptados no banco serão irrecuperáveis.\n")

if __name__ == "__main__":
    gerar_aes_key()
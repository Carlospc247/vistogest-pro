import secrets
import string

def gerar_senha_singular(tamanho=16):
    """
    Gera uma senha aleatória, segura e singular.
    Utiliza letras (maiúsculas/minúsculas), números e símbolos.
    """
    # Definimos o conjunto de caracteres: Letras + Números + Símbolos
    caracteres = string.ascii_letters + string.digits + string.punctuation
    
    while True:
        # Gera a senha
        senha = ''.join(secrets.choice(caracteres) for _ in range(tamanho))
        
        # Validação de Robustez: Garante que a senha tenha pelo menos 
        # 1 letra minúscula, 1 maiúscula, 1 número e 1 símbolo.
        if (any(c.islower() for c in senha)
                and any(c.isupper() for c in senha)
                and sum(c.isdigit() for c in senha) >= 5
                and any(c in string.punctuation for c in senha)):
            return senha

# Exemplo de uso direto:
if __name__ == "__main__":
    nova_senha = gerar_senha_singular()
    print(f"Senha Gerada: {nova_senha}")
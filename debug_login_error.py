# debug_login_error.py
import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from apps.core.models import Usuario

def surgery():
    print(f"--- CIRURGIA SOTARQ INICIADA (Schema: {connection.schema_name}) ---")
    
    # Pegamos o usuário que o senhor criou
    try:
        user = Usuario.objects.get(username='admin_sotarq')
        print(f"✔ Usuário {user.username} carregado.")
        
        print("\n[TESTE 1] Acessando propriedade .funcionario...")
        try:
            f = user.funcionario
            print(f"Resultado: {f}")
        except Exception as e:
            print(f"❌ FALHA NO TESTE 1: {e}")

        print("\n[TESTE 2] Forçando serialização (o que o login faz)...")
        try:
            # O Django Admin as vezes tenta acessar campos para o log de auditoria
            from django.forms.models import model_to_dict
            data = model_to_dict(user)
            print("✔ Serialização básica OK.")
        except Exception as e:
            print(f"❌ FALHA NO TESTE 2: {e}")

    except Exception as e:
        print(f"Erro ao carregar usuário: {e}")

if __name__ == "__main__":
    surgery()
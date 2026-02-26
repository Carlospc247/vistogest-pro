import os
import django
from django.db import connection

# 1. SETUP AMBIENTE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from apps.empresas.models import Empresa
from apps.core.models import Usuario
from django_tenants.utils import schema_exists

def executar_auditoria_integridade():
    print(f"\n{'='*60}")
    print(f"   AUDITORIA DE INTEGRIDADE SOTARQ - {django.utils.timezone.now()}")
    print(f"{'='*60}\n")

    # --- 1. VERIFICAÇÃO DE SCHEMAS FÍSICOS ---
    print("[*] Passo 1: Verificando Schemas Órfãos ou Ausentes...")
    empresas = Empresa.objects.exclude(schema_name='public')
    schemas_ausentes = []
    
    for emp in empresas:
        if not schema_exists(emp.schema_name):
            print(f"  [!] ERRO: Empresa '{emp.nome}' (ID: {emp.id}) aponta para schema '{emp.schema_name}' que NÃO EXISTE no DB.")
            schemas_ausentes.append(emp.id)
        else:
            print(f"  [OK] Schema '{emp.schema_name}' verificado.")

    # --- 2. VERIFICAÇÃO DE USUÁRIOS ZUMBIS ---
    print("\n[*] Passo 2: Verificando Usuários com Vínculos Inválidos...")
    usuarios = Usuario.objects.exclude(is_superuser=True)
    usuarios_invalidos = 0

    for user in usuarios:
        if user.empresa and user.empresa.id in schemas_ausentes:
            print(f"  [!] ALERTA: Usuário '{user.username}' vinculado a uma empresa sem schema físico!")
            usuarios_invalidos += 1
        elif not user.empresa and not user.is_staff:
            print(f"  [!] AVISO: Usuário '{user.username}' está sem empresa vinculada (órfão).")
            usuarios_invalidos += 1

    # --- 3. RELATÓRIO FINAL ---
    print(f"\n{'='*60}")
    print(f"   RESUMO DA SAÚDE DO SISTEMA")
    print(f"{'='*60}")
    print(f" Empresas com Erro: {len(schemas_ausentes)}")
    print(f" Usuários Instáveis: {usuarios_invalidos}")
    
    if not schemas_ausentes and usuarios_invalidos == 0:
        print("\n✔ CONCLUSÃO: O sistema está 100% íntegro. SOTARQ está pronta para faturar.")
    else:
        print("\n✘ CONCLUSÃO: Intervenção necessária detectada.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    executar_auditoria_integridade()
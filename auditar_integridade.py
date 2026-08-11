import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.db import connection
from django.utils import timezone
from django_tenants.utils import (
    get_tenant_model,
    get_public_schema_name,
    schema_exists,
    schema_context
)

def executar_auditoria_integridade():
    print(f"\n{'='*60}")
    print(f"   AUDITORIA DE INTEGRIDADE FÍSICA (SCHEMAS) - {timezone.now()}")
    print(f"{'='*60}\n")

    Empresa = get_tenant_model()
    public_schema = get_public_schema_name()

    # --- 1. VERIFICAR SE CADA EMPRESA TEM SEU SCHEMA FÍSICO ---
    print("[*] Passo 1: Verificando se os Registros de Empresa possuem Schema no PostgreSQL...")
    empresas = Empresa.objects.exclude(schema_name=public_schema)
    schemas_ausentes = []

    for emp in empresas:
        if not schema_exists(emp.schema_name):
            print(f"  [!] ERRO CRÍTICO: Empresa '{emp.nome}' (ID: {emp.id}) aponta para o schema '{emp.schema_name}', mas ele NÃO EXISTE no PostgreSQL!")
            schemas_ausentes.append(emp.schema_name)
        else:
            print(f"  [OK] Schema '{emp.schema_name}' existe no banco.")

    # --- 2. VERIFICAR SCHEMAS FÍSICOS ÓRFÃOS NO POSTGRESQL ---
    print("\n[*] Passo 2: Verificando Schemas no PostgreSQL sem Registro na Tabela de Tenants...")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nspname FROM pg_catalog.pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%%' "
            "AND nspname NOT IN ('information_schema', %s)", 
            [public_schema]
        )
        schemas_no_postgres = [row[0] for row in cursor.fetchall()]

    schemas_registrados = set(Empresa.objects.values_list('schema_name', flat=True))
    schemas_orfaos = set(schemas_no_postgres) - schemas_registrados

    if schemas_orfaos:
        for sch in schemas_orfaos:
            print(f"  [!] AVISO: Schema físico '{sch}' existe no DB, mas não está cadastrado na tabela de empresas.")
    else:
        print("  [OK] Nenhum schema órfão encontrado no PostgreSQL.")

    # --- 3. VERIFICAR ESTRUTURA INTERNA DOS SCHEMAS (MIGRAÇÕES) ---
    print("\n[*] Passo 3: Testando Conexão e Integridade do Contexto dos Schemas...")
    schemas_com_falha = []
    
    for emp in empresas:
        if emp.schema_name in schemas_ausentes:
            continue
        try:
            with schema_context(emp.schema_name):
                with connection.cursor() as cursor:
                    # Teste básico de execução dentro do schema do tenant
                    cursor.execute("SELECT 1;")
            print(f"  [OK] Contexto do Schema '{emp.schema_name}' ativo e funcional.")
        except Exception as e:
            print(f"  [!] ERRO ao alternar para o schema '{emp.schema_name}': {e}")
            schemas_com_falha.append(emp.schema_name)

    # --- 4. RESUMO ---
    print(f"\n{'='*60}")
    print(f"   RESUMO DA INFRAESTRUTURA TENANT")
    print(f"{'='*60}")
    print(f" Total de Tenants Registrados: {empresas.count()}")
    print(f" Schemas Ausentes (Falta criar no DB): {len(schemas_ausentes)}")
    print(f" Schemas Órfãos (Sobrou no DB): {len(schemas_orfaos)}")
    print(f" Schemas com Falha de Acesso: {len(schemas_com_falha)}")

    if not schemas_ausentes and not schemas_orfaos and not schemas_com_falha:
        print("\n✔ CONCLUSÃO: O isolamento físico está 100% íntegro.")
    else:
        print("\n✘ CONCLUSÃO: Existem divergências na infraestrutura de schemas.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    executar_auditoria_integridade()
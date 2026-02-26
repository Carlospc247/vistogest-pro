import os
import django
import sys
from datetime import datetime

# ==============================================================================
# 1. SETUP DE AMBIENTE (RIGOR SOTARQ: Deve vir antes de QUALQUER import de apps)
# ==============================================================================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

# Agora que o Django acordou, podemos importar os modelos e ferramentas
from django.db import transaction, connection
from django.core.management import call_command
from django.contrib.auth.models import Permission, Group
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.empresas.models import Empresa, Domain, Loja
from apps.core.models import Usuario

# --- AUXILIARES ---
def format_header(title):
    print(f"\n{'='*50}\n {title.upper()} \n{'='*50}")

# --- (00) CONFIGURAÇÃO INICIAL DO SCHEMA PUBLIC ---
def configurar_public_inicial():
    format_header("Configuração Inicial SOTARQ (PUBLIC)")
    if Empresa.objects.filter(schema_name='public').exists():
        print("Aviso: O schema 'public' já está configurado.")
        return

    try:
        with transaction.atomic():
            public_tenant = Empresa.objects.create(
                schema_name='public',
                nome="SOTARQ CLOUD - ADMINISTRAÇÃO CENTRAL",
                nif="0000000000",
                provincia='LUA',
                ativa=True
            )
            domain_name = input("\nDigite o domínio principal (ex: localhost): ")
            Domain.objects.create(domain=domain_name, tenant=public_tenant, is_primary=True)
            print(f"✔ Sucesso: Infraestrutura base configurada.")
    except Exception as e:
        print(f"❌ Erro ao configurar Public: {e}")

# --- (1) CRIAR DOMÍNIO GLOBAL ---
def criar_dominio_global():
    format_header("Criar Domínio Global")
    domain_name = input("Domínio (ex: localhost ou sotarq.com): ")
    try:
        public_tenant = Empresa.objects.get(schema_name='public')
        Domain.objects.get_or_create(domain=domain_name, tenant=public_tenant, is_primary=True)
        print(f"✔ Sucesso: Domínio '{domain_name}' vinculado ao Global.")
    except Exception as e:
        print(f"❌ Erro: {e}")

# --- (2) CRIAR SUPERUSER GLOBAL ---
def criar_superuser_global():
    format_header("Criar Superuser Global (Acesso ao Painel Central)")
    username = input("Username: ")
    email = input("Email: ")
    password = input("Senha: ")
    
    with schema_context('public'):
        if Usuario.objects.filter(username=username).exists():
            print("Erro: Usuário já existe.")
            return
        Usuario.objects.create_superuser(username=username, email=email, password=password)
        print(f"✔ Sucesso: Superuser '{username}' criado.")

# --- (3) CRIAR EMPRESA COMPLETA (SETUP TOTAL VIA TERMINAL) ---
def criar_empresa_completa():
    format_header("Nova Empresa + Admin Supremo (Setup Total)")
    nome = input("Nome da Empresa: ")
    schema = input("Schema Name (ex: mundo_maquinas): ")
    nif = input("NIF: ")
    regime = input("Regime (COMERCIO/SERVICOS/MISTO): ").upper()
    domain_name = input("Domínio (ex: mundo.localhost): ")
    
    adm_user = input("Username do Admin Supremo: ")
    adm_email = input("Email do Admin Supremo: ")
    adm_pass = input("Senha do Admin Supremo: ")

    try:
        with transaction.atomic():
            tenant = Empresa.objects.create(
                schema_name=schema, nome=nome, nif=nif, regime=regime, provincia='LUA', ativa=True
            )
            Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)
            
            loja_matriz = Loja.objects.create(
                empresa=tenant, nome=f"Matriz - {nome}", codigo="MATRIZ-01", eh_matriz=True
            )

            novo_user = Usuario.objects.create_user(
                username=adm_user, email=adm_email, password=adm_pass,
                empresa=tenant, loja=loja_matriz, e_administrador_empresa=True
            )
            
            print(f"[*] Migrando schema '{schema}' (isso pode demorar)...")
            call_command('migrate_schemas', schema_name=schema, verbosity=0)

            _setup_hierarquia_local(tenant, novo_user, loja_matriz)
            print(f"🚀 SUCESSO: Empresa '{nome}' pronta!")
    except Exception as e:
        print(f"❌ Erro Crítico: {e}")

# --- (10) EMPOSTAR ADMIN EM TENANT EXISTENTE (SETUP PÓS-ADMIN) ---
def vincular_admin_supremo_tenant():
    format_header("Empossar Admin Supremo Local")
    u_id = input("ID do Usuário: ")
    e_id = input("ID da Empresa: ")

    try:
        user = Usuario.objects.get(id=u_id)
        tenant = Empresa.objects.get(id=e_id)
        
        loja_matriz = Loja.objects.filter(empresa=tenant, eh_matriz=True).first()
        if not loja_matriz:
            loja_matriz = Loja.objects.create(
                empresa=tenant, nome=f"Matriz - {tenant.nome}", codigo="MATRIZ-01", eh_matriz=True
            )

        with transaction.atomic():
            user.empresa = tenant
            user.loja = loja_matriz
            user.e_administrador_empresa = True
            user.save()

            _setup_hierarquia_local(tenant, user, loja_matriz)
            print(f"🚀 SUCESSO: '{user.username}' empossado em '{tenant.nome}'!")
    except Exception as e:
        print(f"❌ Erro: {e}")

# --- FUNÇÃO PRIVADA DE HIERARQUIA ---
def _setup_hierarquia_local(tenant, user, loja):
    """Garante Cargo Supremo, Dept e Funcionario dentro do schema do tenant."""
    with schema_context(tenant.schema_name):
        from apps.funcionarios.models import Cargo, Departamento, Funcionario
        
        cargo, _ = Cargo.objects.get_or_create(
            nome="Administrador Supremo",
            defaults={
                'empresa': tenant, 'codigo': f"SUP-{tenant.id}", 'nivel_hierarquico': 1,
                'categoria': 'diretoria', 'selecionar_todos': True, 'pode_vender': True,
                'pode_acessar_rh': True, 'pode_acessar_financeiro': True, 'pode_exportar_saft': True
            }
        )
        dept, _ = Departamento.objects.get_or_create(
            nome="Administração Geral", defaults={'codigo': "DEP-001", 'ativo': True}
        )
        Funcionario.objects.update_or_create(
            usuario=user,
            defaults={
                'empresa': tenant, 'cargo': cargo, 'departamento': dept,
                'nome_completo': user.username.upper(), 'data_admissao': timezone.now().date(),
                'salario_atual': 1.00, 'ativo': True
            }
        )
        app_labels = ['produtos', 'analytics', 'clientes', 'vendas', 'funcionarios', 'fiscal', 'saft', 'financeiro', 'estoque']
        perms = Permission.objects.filter(content_type__app_label__in=app_labels)
        user.user_permissions.set(perms)

# --- OUTRAS UTILIDADES ---
def listar_empresas():
    format_header("Empresas/Inquilinos")
    for e in Empresa.objects.all(): print(f"ID: {e.id} | Schema: {e.schema_name} | Nome: {e.nome}")

def listar_usuarios():
    format_header("Usuários do Sistema")
    for u in Usuario.objects.all(): print(f"ID: {u.id} | User: {u.username} | Empresa: {u.empresa.nome if u.empresa else 'GLOBAL'}")

def resetar_senha_usuario():
    format_header("Resetar Senha")
    u_id = input("ID do Usuário: ")
    try:
        user = Usuario.objects.get(id=u_id)
        nova = input("Nova Senha: ")
        user.set_password(nova)
        user.save()
        print("✔ Senha atualizada.")
    except: print("Erro.")

def apagar_empresa():
    format_header("Apagar Empresa")
    e_id = input("ID da Empresa: ")
    try:
        emp = Empresa.objects.get(id=e_id)
        if emp.schema_name != 'public' and input(f"Apagar {emp.nome}? (s/n): ") == 's':
            emp.delete()
            print("✔ Removido.")
    except: print("Erro.")

def apagar_usuario():
    format_header("Apagar Usuário")
    u_id = input("ID do Usuário: ")
    try:
        user = Usuario.objects.get(id=u_id)
        if input(f"Apagar {user.username}? (s/n): ") == 's':
            user.delete()
            print("✔ Removido.")
    except: print("Erro.")

# --- MENU ---
def menu():
    while True:
        print("\nSOTARQ VENDOR - CONSOLE SUPREMO")
        print("00. Configurar Infra (PUBLIC)")
        print("1. Criar Domínio Global")
        print("2. Criar Superuser Global")
        print("3. Criar Empresa + Admin (Full Setup)")
        print("4. Listar Empresas")
        print("5. Listar Usuários")
        print("7. Apagar Empresa")
        print("8. Apagar Usuário")
        print("9. Resetar Senha")
        print("10. Empossar Admin em Tenant Existente")
        print("0. Sair")
        
        opcao = input("\nEscolha: ")
        if opcao == '00': configurar_public_inicial()
        elif opcao == '1': criar_dominio_global()
        elif opcao == '2': criar_superuser_global()
        elif opcao == '3': criar_empresa_completa()
        elif opcao == '4': listar_empresas()
        elif opcao == '5': listar_usuarios()
        elif opcao == '7': apagar_empresa()
        elif opcao == '8': apagar_usuario()
        elif opcao == '9': resetar_senha_usuario()
        elif opcao == '10': vincular_admin_supremo_tenant()
        elif opcao == '0': break

if __name__ == "__main__":
    menu()
# vistogest-pro/gerenciar_sotarq.py
import os
import sys
from datetime import datetime

# ==============================================================================
# 1. SETUP DE AMBIENTE (RIGOR SOTARQ)
# ==============================================================================
if os.environ.get('RENDER'):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()

# ==============================================================================
# 2. IMPORTS APÓS O SETUP DO DJANGO
# ==============================================================================
from django.db import transaction
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from django_tenants.utils import (
    get_tenant_model,
    get_public_schema_name,
    schema_context,
)

from apps.empresas.models import Domain

# Resolução dinâmica dos modelos de Tenant e Usuário
Empresa = get_tenant_model()
Usuario = get_user_model()
PUBLIC_SCHEMA = get_public_schema_name()


# --- AUXILIARES ---
def format_header(title):
    print(f"\n{'='*50}\n {title.upper()} \n{'='*50}")


# --- (00) CONFIGURAÇÃO INICIAL DO SCHEMA PUBLIC ---
def configurar_public_inicial():
    format_header("Configuração Inicial SOTARQ (PUBLIC)")

    with schema_context(PUBLIC_SCHEMA):
        if Empresa.objects.filter(schema_name=PUBLIC_SCHEMA).exists():
            print("ℹ Aviso: O schema 'public' já está configurado.")
            return

        try:
            with transaction.atomic():
                public_tenant = Empresa.objects.create(
                    schema_name=PUBLIC_SCHEMA,
                    nome="SOTARQ CLOUD - ADMINISTRAÇÃO CENTRAL",
                    nome_fantasia="SOTARQ Central",
                    nif="0000000000",
                    provincia='LUA',
                    ativa=True
                )
                domain_name = input("\nDigite o domínio principal (ex: localhost): ").strip()
                Domain.objects.create(domain=domain_name, tenant=public_tenant, is_primary=True)
                print("✔ Sucesso: Infraestrutura base configurada no schema 'public'.")
        except Exception as e:
            print(f"❌ Erro ao configurar Public: {e}")


# --- (1) CRIAR DOMÍNIO GLOBAL ---
def criar_dominio_global():
    format_header("Criar Domínio Global")
    domain_name = input("Domínio (ex: localhost ou sotarq.com): ").strip()

    with schema_context(PUBLIC_SCHEMA):
        try:
            public_tenant = Empresa.objects.get(schema_name=PUBLIC_SCHEMA)
            Domain.objects.get_or_create(domain=domain_name, tenant=public_tenant, defaults={'is_primary': True})
            print(f"✔ Sucesso: Domínio '{domain_name}' vinculado ao Global.")
        except Exception as e:
            print(f"❌ Erro: {e}")


# --- (2) CRIAR SUPERUSER GLOBAL ---
def criar_superuser_global():
    format_header("Criar Superuser Global (Acesso ao Painel Central)")
    username = input("Username: ").strip()
    email = input("Email: ").strip()
    password = input("Senha: ").strip()

    with schema_context(PUBLIC_SCHEMA):
        if Usuario.objects.filter(username=username).exists():
            print("❌ Erro: Usuário já existe.")
            return
        Usuario.objects.create_superuser(username=username, email=email, password=password)
        print(f"✔ Sucesso: Superuser '{username}' criado no schema 'public'.")


# --- (3) CRIAR EMPRESA COMPLETA (SETUP TOTAL) ---
def criar_empresa_completa():
    format_header("Nova Empresa + Admin Supremo (Setup Total)")
    nome = input("Nome da Empresa: ").strip()
    schema = input("Schema Name (ex: mundo_maquinas): ").strip().lower()
    nif = input("NIF: ").strip()
    regime = input("Regime (COMERCIO/SERVICOS/MISTO): ").strip().upper()
    domain_name = input("Domínio (ex: mundo.localhost): ").strip()

    adm_user = input("Username do Admin Supremo: ").strip()
    adm_email = input("Email do Admin Supremo: ").strip()
    adm_pass = input("Senha do Admin Supremo: ").strip()

    try:
        # STEP 1: Criar Tenant e Domínio no Schema Public
        with schema_context(PUBLIC_SCHEMA):
            if Empresa.objects.filter(schema_name=schema).exists():
                print(f"❌ Erro: O schema '{schema}' já existe.")
                return

            tenant = Empresa.objects.create(
                schema_name=schema,
                nome=nome,
                nome_fantasia=nome,
                nif=nif,
                regime=regime,
                provincia='LUA',
                ativa=True
            )
            Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)

            # Criar usuário administrador global/vinculado no public
            novo_user, created_user = Usuario.objects.get_or_create(
                username=adm_user,
                defaults={
                    'email': adm_email,
                    'is_staff': True,
                    'is_active': True
                }
            )
            if created_user:
                novo_user.set_password(adm_pass)
                novo_user.save()

        # STEP 2: Executar Migrações do Novo Schema
        print(f"[*] Executando migrações no schema '{schema}' (aguarde)...")
        call_command('migrate_schemas', schema_name=schema, verbosity=0)

        # STEP 3: Configurar estruturas locais dentro do Schema do Tenant
        _setup_hierarquia_local(schema, novo_user)

        print(f"🚀 SUCESSO: Empresa '{nome}' e ambiente '{schema}' prontos!")

    except Exception as e:
        print(f"❌ Erro Crítico durante o Setup: {e}")


# --- (10) EMPOSSAR ADMIN EM TENANT EXISTENTE ---
def vincular_admin_supremo_tenant():
    format_header("Empossar Admin Supremo Local")
    u_id = input("ID do Usuário (schema public): ").strip()
    e_id = input("ID ou Schema da Empresa: ").strip()

    try:
        with schema_context(PUBLIC_SCHEMA):
            user = Usuario.objects.get(id=u_id)
            if e_id.isdigit():
                tenant = Empresa.objects.get(id=int(e_id))
            else:
                tenant = Empresa.objects.get(schema_name=e_id)

        _setup_hierarquia_local(tenant.schema_name, user)
        print(f"🚀 SUCESSO: '{user.username}' empossado em '{tenant.nome}'!")

    except Exception as e:
        print(f"❌ Erro: {e}")


# --- FUNÇÃO PRIVADA DE HIERARQUIA NO SCHEMA DO TENANT ---
def _setup_hierarquia_local(schema_name, user):
    """Garante Cargo Supremo, Dept e Funcionario dentro do schema do tenant."""
    with schema_context(schema_name):
        from datetime import date
        from apps.funcionarios.models import Cargo, Departamento, Funcionario

        with transaction.atomic():
            # 1. Empresa atual (Empresa é SHARED_APPS — acessível via search_path
            # mesmo estando ligado ao schema do tenant)
            empresa_obj = Empresa.objects.get(schema_name=schema_name)

            # 2. Cargo Supremo (empresa é obrigatório no model Cargo)
            cargo, _ = Cargo.objects.get_or_create(
                nome="Administrador Supremo",
                empresa=empresa_obj,
                defaults={
                    'codigo': "SUP-01",
                    'nivel_hierarquico': 1,
                    'categoria': 'diretoria',
                    'selecionar_todos': True,
                    'pode_vender': True,
                    'pode_acessar_rh': True,
                    'pode_acessar_financeiro': True,
                    'pode_exportar_saft': True
                }
            )

            # 3. Departamento
            dept, _ = Departamento.objects.get_or_create(
                codigo="DEP-001",
                defaults={
                    'nome': "Administração Geral",
                    'ativo': True
                }
            )

            # 4. Funcionário
            # NOTA: bi, data_nascimento, sexo, endereco, numero, bairro, cidade e
            # postal são campos obrigatórios no model Funcionario (sem default).
            # Os valores abaixo são PLACEHOLDERS — o admin deve completar o perfil
            # real depois, via o painel do sistema.
            bi_placeholder = f"SUP{user.id:011d}"[:14]

            Funcionario.objects.update_or_create(
                usuario=user,
                defaults={
                    'cargo': cargo,
                    'departamento': dept,
                    'nome_completo': user.username.upper(),
                    'bi': bi_placeholder,
                    'data_nascimento': date(2000, 1, 1),
                    'sexo': 'O',
                    'endereco': "A definir",
                    'numero': "S/N",
                    'bairro': "A definir",
                    'cidade': getattr(empresa_obj, 'cidade', 'Luanda') or 'Luanda',
                    'postal': "0000000",
                    'data_admissao': timezone.now().date(),
                    'salario_atual': 1.00,
                    'ativo': True
                }
            )
            print("⚠ Perfil do Funcionário criado com dados placeholder (BI, data de nascimento, "
                  "sexo, morada). Completa o perfil real depois, via o sistema.")

            # 5. Permissões
            app_labels = [
                'produtos', 'analytics', 'clientes', 'vendas',
                'funcionarios', 'fiscal', 'saft', 'financeiro', 'estoque'
            ]
            perms = Permission.objects.filter(content_type__app_label__in=app_labels)
            user.user_permissions.set(perms)


# --- UTILIDADES ---
def listar_empresas():
    format_header("Empresas/Tenants Cadastrados")
    with schema_context(PUBLIC_SCHEMA):
        for e in Empresa.objects.all():
            print(f"ID: {e.id:<4} | Schema: {e.schema_name:<18} | Nome: {e.nome}")


def listar_usuarios():
    format_header("Usuários do Sistema (Schema Public)")
    with schema_context(PUBLIC_SCHEMA):
        for u in Usuario.objects.all():
            print(f"ID: {u.id:<4} | User: {u.username:<15} | Email: {u.email}")


def resetar_senha_usuario():
    format_header("Resetar Senha de Usuário")
    u_id = input("ID do Usuário: ").strip()

    with schema_context(PUBLIC_SCHEMA):
        try:
            user = Usuario.objects.get(id=u_id)
            nova = input("Nova Senha: ").strip()
            user.set_password(nova)
            user.save()
            print(f"✔ Senha de '{user.username}' atualizada com sucesso.")
        except Usuario.DoesNotExist:
            print("❌ Usuário não encontrado.")
        except Exception as e:
            print(f"❌ Erro: {e}")


def apagar_empresa():
    format_header("Apagar Empresa / Tenant")
    e_id = input("ID da Empresa: ").strip()

    with schema_context(PUBLIC_SCHEMA):
        try:
            emp = Empresa.objects.get(id=e_id)
            if emp.schema_name == PUBLIC_SCHEMA:
                print("❌ Não é permitido apagar o schema 'public'.")
                return

            if input(f"⚠️ Apagar a empresa '{emp.nome}' e SEU SCHEMA COMPLETO '{emp.schema_name}'? (s/n): ").lower() == 's':
                emp.delete()
                print("✔ Tenant e schema removidos com sucesso.")
        except Empresa.DoesNotExist:
            print("❌ Empresa não encontrada.")
        except Exception as e:
            print(f"❌ Erro: {e}")


def apagar_usuario():
    format_header("Apagar Usuário")
    u_id = input("ID do Usuário: ").strip()

    with schema_context(PUBLIC_SCHEMA):
        try:
            user = Usuario.objects.get(id=u_id)
            if input(f"⚠️ Apagar o usuário '{user.username}'? (s/n): ").lower() == 's':
                user.delete()
                print("✔ Usuário removido com sucesso.")
        except Usuario.DoesNotExist:
            print("❌ Usuário não encontrado.")
        except Exception as e:
            print(f"❌ Erro: {e}")


# --- (11) RESETAR BANCO (APAGAR TUDO, EXCETO A ÁREA GLOBAL) ---
def resetar_banco():
    """
    ⚠️ OPERAÇÃO DESTRUTIVA IRREVERSÍVEL ⚠️
    Reseta o banco por completo, mantendo apenas a "área global":
      - A Empresa/schema 'public' em si (nunca é apagada)
      - Os Usuarios com is_superuser=True (schema public)
      - Os dados da app 'licenca' (Modulo, PlanoLicenca) — catálogo global,
        não é tocado. Registos de Licenca ligados aos tenants apagados
        somem naturalmente via CASCADE, porque a empresa deixa de existir.

    Tudo o resto é apagado:
      - Todos os tenants (exceto 'public') e os respetivos schemas físicos
      - Todos os domínios (Domain), incluindo os do schema public
      - Todos os Usuarios não-superuser (schema public)

    Trava de segurança em 2 etapas:
      1. Confirmação simples (s/n)
      2. Digitação exata da frase de confirmação
    """
    format_header("⚠️  RESETAR BANCO — OPERAÇÃO IRREVERSÍVEL  ⚠️")

    with schema_context(PUBLIC_SCHEMA):
        tenants_a_apagar = list(Empresa.objects.exclude(schema_name=PUBLIC_SCHEMA))
        total_dominios = Domain.objects.count()
        usuarios_a_apagar = list(Usuario.objects.filter(is_superuser=False))
        total_superusers = Usuario.objects.filter(is_superuser=True).count()

    if not tenants_a_apagar and total_dominios == 0 and not usuarios_a_apagar:
        print("ℹ Nada a resetar: já só existe a área global (public + superusers).")
        return

    print("\nEsta ação vai apagar PERMANENTEMENTE:")
    print(f"  • {len(tenants_a_apagar)} empresa(s)/tenant(s) e os respetivos schemas:")
    for t in tenants_a_apagar:
        print(f"     - ID: {t.id:<4} | Schema: {t.schema_name:<18} | Nome: {t.nome}")
    print(f"  • {total_dominios} domínio(s) cadastrado(s) (incluindo os do schema public)")
    print(f"  • {len(usuarios_a_apagar)} usuário(s) não-superuser (schema public):")
    for u in usuarios_a_apagar:
        print(f"     - ID: {u.id:<4} | User: {u.username}")

    print("\nVai ser MANTIDO:")
    print(f"  • O schema 'public' em si")
    print(f"  • {total_superusers} superuser(s)")
    print(f"  • Todos os Módulos e Planos de Licença (catálogo global)")

    # --- TRAVA 1: Confirmação simples ---
    confirmacao_1 = input("\nTens a CERTEZA que queres continuar? (s/n): ").strip().lower()
    if confirmacao_1 != 's':
        print("❌ Operação cancelada.")
        return

    # --- TRAVA 2: Frase exata de confirmação ---
    frase_esperada = "RESETAR TUDO"
    print(f"\nPara confirmar definitivamente, digita exatamente a frase abaixo (sensível a maiúsculas):")
    print(f"    {frase_esperada}")
    frase_digitada = input("\n> ").strip()

    if frase_digitada != frase_esperada:
        print("❌ Frase de confirmação incorreta. Operação cancelada por segurança.")
        return

    # --- EXECUÇÃO ---
    try:
        with schema_context(PUBLIC_SCHEMA):
            with transaction.atomic():
                # Apaga todos os domínios (public + tenants)
                total_dominios_apagados, _ = Domain.objects.all().delete()

                # Apaga cada tenant: primeiro derruba o schema físico (DROP SCHEMA ... CASCADE),
                # depois remove a linha da tabela Empresa via SQL direto (_raw_delete), evitando
                # o Collector padrão do Django — que tentaria verificar FKs reversas de models de
                # TENANT_APPS (ex: clientes.GrupoCliente.empresa) cujas tabelas só existem dentro
                # de cada schema de tenant, não no schema 'public' onde estamos a operar.
                for t in tenants_a_apagar:
                    t._drop_schema(force_drop=True)
                    Empresa.objects.filter(pk=t.pk)._raw_delete(Empresa.objects.db)

                # Apaga todos os usuários não-superuser do schema public
                total_usuarios_apagados = len(usuarios_a_apagar)
                Usuario.objects.filter(is_superuser=False).delete()

        print(f"\n✔ SUCESSO:")
        print(f"   • {len(tenants_a_apagar)} empresa(s)/schema(s) removidos")
        print(f"   • {total_dominios_apagados} domínio(s) removidos")
        print(f"   • {total_usuarios_apagados} usuário(s) não-superuser removidos")
        print("ℹ O schema 'public' e os superusers continuam intactos.")
        print("ℹ Usa a opção '1' para recriar o domínio global antes de voltar a aceder ao sistema.")
    except Exception as e:
        print(f"❌ Erro Crítico durante o Reset: {e}")


# --- MENU PRINCIPAL ---
def menu():
    while True:
        print("\n==========================================")
        print("      SOTARQ VENDOR - CONSOLE SUPREMO     ")
        print("==========================================")
        print("00. Configurar Infra Base (PUBLIC)")
        print(" 1. Criar Domínio Global")
        print(" 2. Criar Superuser Global")
        print(" 3. Criar Empresa + Admin (Full Setup)")
        print(" 4. Listar Empresas")
        print(" 5. Listar Usuários")
        print(" 7. Apagar Empresa/Tenant")
        print(" 8. Apagar Usuário")
        print(" 9. Resetar Senha")
        print("10. Empossar Admin em Tenant Existente")
        print("11. ⚠️  Resetar Banco (Apagar tudo, exceto área global)")
        print(" 0. Sair")

        opcao = input("\nEscolha uma opção: ").strip()

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
        elif opcao == '11': resetar_banco()
        elif opcao == '0':
            print("Saindo...")
            sys.exit(0)


if __name__ == "__main__":
    menu()
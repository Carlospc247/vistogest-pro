# gerenciar_sotarq.py — VistoGest Pro / SOTARQ Software
"""
Console administrativo da infraestrutura SOTARQ.

Uso:
    python gerenciar_sotarq.py

O ambiente é seleccionado automaticamente:
    • RENDER definido            → config.settings.production
    • ENV_MODE=production        → config.settings.production
    • Caso contrário             → config.settings.development

Revisão actual (sobre a versão anterior):
    • Opção 14 — já não mostra api_username/api_password do tenant: as
      credenciais Basic Auth da AGT são do SISTEMA (.env). Mostra o ambiente AGT
      e se AGT_API_USERNAME/AGT_API_PASSWORD estão definidas (nunca os valores).
    • Opção 15 — testa a ligação REAL pelo AGTClient (listarSeries assinado),
      em modo só-leitura (não grava séries). Antes chamava /listarFacturas com
      assinaturas "test" e credenciais por tenant.
    • Apagar tenant/reset: usa delete(force_drop=True). Em django-tenants o
      schema só é apagado automaticamente se o modelo tiver auto_drop_schema=True;
      sem force_drop o registo ia embora e o schema ficava órfão na base de dados.
    • Reset: já NÃO apaga o domínio do tenant 'public' (antes ficava o tenant
      global sem domínio e o site deixava de responder).
    • _setup_hierarquia_local: Cargo deixou de usar FK `empresa` (regra do
      isolamento físico: apps de tenant não referenciam Empresa).
    • Protecção de produção também ao apagar um tenant.
"""

import os
from datetime import date
from getpass import getpass

# ──────────────────────────────────────────────────────────────────────────────
# 1. SETUP DO DJANGO
# ──────────────────────────────────────────────────────────────────────────────

if os.environ.get('RENDER') or os.environ.get('ENV_MODE', '').lower() == 'production':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

# ──────────────────────────────────────────────────────────────────────────────
# 2. IMPORTS APÓS django.setup()
# ──────────────────────────────────────────────────────────────────────────────

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import (
    get_public_schema_name,
    get_tenant_model,
    schema_context,
)

from apps.empresas.models import Domain

Empresa       = get_tenant_model()
Usuario       = get_user_model()
PUBLIC_SCHEMA = get_public_schema_name()

EM_PRODUCAO = bool(os.environ.get('RENDER') or os.environ.get('ENV_MODE', '').lower() == 'production')

# ──────────────────────────────────────────────────────────────────────────────
# 3. AUXILIARES
# ──────────────────────────────────────────────────────────────────────────────

def format_header(title):
    print(f"\n{'=' * 60}\n {title.upper()} \n{'=' * 60}")


def normalizar_domain(domain):
    return domain.strip().lower().rstrip('.')


def validar_domain(domain):
    if not domain:
        raise ValueError("O domínio não pode estar vazio.")
    if '://' in domain:
        raise ValueError("Informe apenas o hostname, sem http:// ou https://.")
    if '/' in domain:
        raise ValueError("O domínio não deve conter '/'.")
    return domain


def obter_tenant_public():
    try:
        return Empresa.objects.get(schema_name=PUBLIC_SCHEMA)
    except Empresa.DoesNotExist:
        raise RuntimeError(
            "O tenant global 'public' ainda não existe. "
            "Execute primeiro a opção 00."
        )


def obter_empresa(identificador):
    """Resolve uma Empresa por ID numérico ou schema_name (corre no schema public)."""
    identificador = identificador.strip()
    with schema_context(PUBLIC_SCHEMA):
        if identificador.isdigit():
            return Empresa.objects.get(id=int(identificador))
        return Empresa.objects.get(schema_name=identificador)


def confirmar_producao(acao):
    """Exige confirmação reforçada em produção. Devolve True se pode continuar."""
    if not EM_PRODUCAO:
        return True
    resposta = input(
        f"⚡ ATENÇÃO: PRODUÇÃO. Para {acao}, escreva 'CONFIRMO PRODUCAO': "
    ).strip()
    if resposta != 'CONFIRMO PRODUCAO':
        print("❌ Operação cancelada (protecção de produção).")
        return False
    return True


def campos_base_empresa():
    return {
        'endereco':  'A definir',
        'numero':    'S/N',
        'bairro':    'A definir',
        'cidade':    'Luanda',
        'postal':    '0000000',
        'telefone':  '000000000',
        'email':     os.getenv('SUPPORT_EMAIL', ''),
    }


def obter_ou_criar_usuario(username, email, password=None):
    """
    Cria/actualiza um utilizador no schema public.
    update_fields é construído dinamicamente — só inclui o que mudou.
    """
    username = username.strip()
    email    = email.strip()

    if not username:
        raise ValueError("Username é obrigatório.")
    if not email:
        raise ValueError("Email é obrigatório.")

    with schema_context(PUBLIC_SCHEMA):
        user = Usuario.objects.filter(username=username).first()

        if user:
            update_fields = []

            if email and user.email != email:
                user.email = email
                update_fields.append('email')

            if not user.is_staff:
                user.is_staff = True
                update_fields.append('is_staff')

            if not user.is_active:
                user.is_active = True
                update_fields.append('is_active')

            if update_fields:
                user.save(update_fields=update_fields)

            return user, False

        if not password:
            raise ValueError("Senha é obrigatória para um novo utilizador.")

        user = Usuario.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        return user, True


# ──────────────────────────────────────────────────────────────────────────────
# 00. CONFIGURAÇÃO INICIAL DO SCHEMA PUBLIC
# ──────────────────────────────────────────────────────────────────────────────

def configurar_public_inicial():
    format_header("Configuração Inicial SOTARQ — PUBLIC")

    with schema_context(PUBLIC_SCHEMA):
        if Empresa.objects.filter(schema_name=PUBLIC_SCHEMA).exists():
            print("ℹ O tenant global 'public' já existe.")
            print("  Use a opção 1 para criar/vincular o domínio global.")
            return

        domain_name = validar_domain(
            normalizar_domain(input("\nDomínio global (ex: sotarqsoft.com) ou localhost: "))
        )

        try:
            with transaction.atomic():
                dados = campos_base_empresa()
                public_tenant = Empresa.objects.create(
                    schema_name=PUBLIC_SCHEMA,
                    nome='SOTARQ CLOUD - ADMINISTRAÇÃO CENTRAL',
                    nome_fantasia='SOTARQ Central',
                    nif='0000000000',
                    regime='MISTO',           # tipo de actividade
                    regime_fiscal='GERAL',    # regime fiscal AGT
                    provincia='LUA',
                    ativa=True,
                    **dados,
                )
                Domain.objects.create(
                    domain=domain_name,
                    tenant=public_tenant,
                    is_primary=True,
                )
            print("✔ Tenant global e domínio configurados no schema public.")
        except Exception as exc:
            print(f"❌ Erro ao configurar o PUBLIC: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 01. CRIAR DOMÍNIO GLOBAL
# ──────────────────────────────────────────────────────────────────────────────

def criar_dominio_global():
    format_header("Criar Domínio Global")
    domain_name = validar_domain(
        normalizar_domain(input("Domínio (ex: localhost ou sotarq.com): "))
    )

    with schema_context(PUBLIC_SCHEMA):
        try:
            public_tenant = obter_tenant_public()
            existente = Domain.objects.filter(domain=domain_name).select_related('tenant').first()

            if existente:
                if existente.tenant_id != public_tenant.id:
                    print(f"❌ Este domínio já está vinculado a outro tenant: {existente.tenant.schema_name}")
                    return
                if not existente.is_primary:
                    existente.is_primary = True
                    existente.save(update_fields=['is_primary'])
                print(f"ℹ O domínio '{domain_name}' já estava vinculado ao tenant global.")
                return

            Domain.objects.create(domain=domain_name, tenant=public_tenant, is_primary=True)
            print(f"✔ Domínio '{domain_name}' vinculado ao GLOBAL.")

        except RuntimeError as exc:
            print(f"❌ {exc}")
        except Exception as exc:
            print(f"❌ Erro: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 02. CRIAR SUPERUSER GLOBAL
# ──────────────────────────────────────────────────────────────────────────────

def criar_superuser_global():
    format_header("Criar Superuser Global")
    username = input("Username: ").strip()
    email    = input("Email: ").strip()
    password = getpass("Senha: ")
    password_confirm = getpass("Confirmar senha: ")

    if password != password_confirm:
        print("❌ As senhas não coincidem.")
        return
    if not password:
        print("❌ A senha não pode estar vazia.")
        return

    try:
        with schema_context(PUBLIC_SCHEMA):
            user = Usuario.objects.filter(username=username).first()
            if user:
                print(f"ℹ O utilizador '{username}' já existe.")
                update_fields = []
                if email and user.email != email:
                    user.email = email
                    update_fields.append('email')
                if not user.is_staff:
                    user.is_staff = True
                    update_fields.append('is_staff')
                if not user.is_active:
                    user.is_active = True
                    update_fields.append('is_active')
                if update_fields:
                    user.save(update_fields=update_fields)
                    print(f"✔ Actualizado: {', '.join(update_fields)}")
                print("⚠ A senha NÃO foi alterada.")
                return

            user = Usuario.objects.create_superuser(
                username=username, email=email, password=password
            )
            print(f"✔ Superuser global '{user.username}' criado no schema public.")

    except Exception as exc:
        print(f"❌ Erro ao criar superuser: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 03. CRIAR EMPRESA + ADMIN + ESTRUTURA INICIAL
# ──────────────────────────────────────────────────────────────────────────────

def criar_empresa_completa():
    format_header("Nova Empresa + Admin Supremo — Full Setup")

    nome    = input("Nome da Empresa: ").strip()
    schema  = input("Schema Name (ex: mundo_maquinas): ").strip().lower()
    nif     = input("NIF: ").strip()
    regime  = (input("Regime (COMERCIO/SERVICOS/MISTO) [MISTO]: ").strip().upper() or "MISTO")
    domain_name = validar_domain(normalizar_domain(input("Domínio (ex: mundo.localhost): ")))

    adm_user  = input("Username do Admin Supremo: ").strip()
    adm_email = input("Email do Admin Supremo: ").strip()
    adm_pass  = getpass("Senha do Admin Supremo: ")
    adm_pass_confirm = getpass("Confirmar senha: ")

    if adm_pass != adm_pass_confirm:
        print("❌ As senhas não coincidem.")
        return
    if not nome or not schema or not nif:
        print("❌ Nome, schema e NIF são obrigatórios.")
        return
    if regime not in {"COMERCIO", "SERVICOS", "MISTO"}:
        print("❌ Regime inválido.")
        return
    if schema == PUBLIC_SCHEMA:
        print("❌ O schema 'public' é reservado ao tenant global.")
        return

    try:
        with schema_context(PUBLIC_SCHEMA):
            if Empresa.objects.filter(schema_name=schema).exists():
                print(f"❌ O schema '{schema}' já está cadastrado.")
                return
            if Domain.objects.filter(domain=domain_name).exists():
                print(f"❌ O domínio '{domain_name}' já está cadastrado.")
                return
            if Empresa.objects.filter(nif=nif).exists():
                print(f"❌ O NIF '{nif}' já está cadastrado.")
                return

            dados = campos_base_empresa()
            with transaction.atomic():
                tenant = Empresa.objects.create(
                    schema_name=schema,
                    nome=nome,
                    nome_fantasia=nome,
                    nif=nif,
                    regime=regime,            # tipo de actividade
                    regime_fiscal='GERAL',    # regime fiscal AGT (padrão; alterar no painel)
                    provincia='LUA',
                    ativa=True,
                    **dados,
                )
                Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)
                novo_user, criado = obter_ou_criar_usuario(
                    username=adm_user, email=adm_email, password=adm_pass
                )

        print(f"[*] Aplicando migrações no schema '{schema}'...")
        call_command('migrate_schemas', '--schema', schema, interactive=False, verbosity=1)

        _setup_hierarquia_local(schema, novo_user, tenant_obj=tenant)

        print(f"\n🚀 SUCESSO: Empresa '{nome}' criada.")
        print(f"   Schema : {schema}")
        print(f"   Domínio: {domain_name}")
        print(f"   Admin  : {novo_user.username}")
        print("   Próximo passo fiscal: admin global → Fiscal → Chaves fiscais das empresas.")
        if not criado:
            print("⚠ O utilizador administrador já existia no PUBLIC.")

    except Exception as exc:
        print(f"❌ Erro crítico durante o Full Setup: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 06. APLICAR MIGRAÇÕES A UM TENANT
# ──────────────────────────────────────────────────────────────────────────────

def aplicar_migracoes_tenant():
    format_header("Aplicar Migrações a um Tenant")

    e_id = input("ID ou Schema da Empresa (ou 'public' para o schema global): ").strip()

    try:
        if e_id.lower() == 'public':
            schema = PUBLIC_SCHEMA
        else:
            schema = obter_empresa(e_id).schema_name

        print(f"[*] A aplicar migrações no schema '{schema}'...")
        call_command('migrate_schemas', '--schema', schema, interactive=False, verbosity=1)
        print(f"✔ Migrações aplicadas em '{schema}'.")

    except Empresa.DoesNotExist:
        print("❌ Empresa não encontrada.")
    except Exception as exc:
        print(f"❌ Erro: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 10. EMPOSSAR ADMIN EM TENANT EXISTENTE
# ──────────────────────────────────────────────────────────────────────────────

def vincular_admin_supremo_tenant():
    format_header("Empossar Admin Supremo Local")
    u_id = input("ID do Usuário (schema public): ").strip()
    e_id = input("ID ou Schema da Empresa: ").strip()

    try:
        with schema_context(PUBLIC_SCHEMA):
            user = Usuario.objects.get(id=u_id)
        tenant = obter_empresa(e_id)

        if tenant.schema_name == PUBLIC_SCHEMA:
            print("❌ O tenant public não é um tenant empresarial.")
            return

        _setup_hierarquia_local(tenant.schema_name, user, tenant_obj=tenant)
        print(f"🚀 SUCESSO: '{user.username}' empossado em '{tenant.nome}'!")

    except Usuario.DoesNotExist:
        print("❌ Usuário não encontrado no schema public.")
    except Empresa.DoesNotExist:
        print("❌ Empresa/Tenant não encontrado.")
    except Exception as exc:
        print(f"❌ Erro: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# HIERARQUIA LOCAL DO TENANT
# ──────────────────────────────────────────────────────────────────────────────

def _setup_hierarquia_local(schema_name, user, tenant_obj=None):
    """
    Garante Cargo Supremo, Departamento e Funcionário dentro do schema do tenant.

    tenant_obj é obrigatório e vem de FORA do schema_context: Empresa é SHARED_APP
    (schema public) e não deve ser consultada com o search_path do tenant.
    Os modelos de tenant (Cargo, Departamento, Funcionario) NÃO têm FK para
    Empresa — o schema já isola.
    """
    if tenant_obj is None:
        raise ValueError(
            "_setup_hierarquia_local: tenant_obj é obrigatório. "
            "Nunca chamar sem o objecto de empresa."
        )

    with schema_context(schema_name):
        from apps.funcionarios.models import Cargo, Departamento, Funcionario

        with transaction.atomic():
            cargo, _ = Cargo.objects.get_or_create(
                nome='Administrador Supremo',
                defaults={
                    'codigo': 'SUP-01',
                    'nivel_hierarquico': 1,
                    'categoria': 'diretoria',
                    'selecionar_todos': True,
                    'pode_vender': True,
                    'pode_ver_vendas': True,
                    'pode_gerenciar_estoque': True,
                    'pode_fazer_compras': True,
                    'pode_aprovar_pedidos': True,
                    'pode_gerenciar_funcionarios': True,
                    'pode_editar_produtos': True,
                    'pode_acessar_rh': True,
                    'pode_acessar_financeiro': True,
                    'pode_acessar_fornecedores': True,
                    'pode_alterar_dados_fiscais': True,
                    'pode_fazer_backup_manual': True,
                    'pode_ver_configuracoes': True,
                    'pode_acessar_configuracoes': True,
                    'pode_exportar_saft': True,
                    'pode_ver_historico_saft': True,
                    'pode_baixar_saft': True,
                    'pode_validar_saft': True,
                    'pode_visualizar_saft': True,
                    'pode_ver_status_saft': True,
                    'pode_acessar_dashboard_fiscal': True,
                    'pode_validar_documentos_fiscais': True,
                    'pode_verificar_integridade_hash': True,
                    'pode_acessar_painel_principal_fiscal': True,
                    'pode_ver_taxas_iva': True,
                    'pode_criar_taxas_iva': True,
                    'pode_apagar_taxas_iva': True,
                    'pode_gerir_assinatura_digital': True,
                    'pode_configurar_assinatura_digital': True,
                    'pode_ver_relatorio_fiscal': True,
                    'pode_ver_relatorio_retencoes': True,
                    'pode_ver_relatorio_taxas_iva': True,
                    'pode_acessar_dashboard_saft': True,
                    'pode_baixar_chave_publica': True,
                    'pode_baixar_retencoes': True,
                    'pode_baixar_saft_backup_fiscal': True,
                    'pode_baixar_relatorio_retencoes': True,
                    'pode_acessar_configuracao_fiscal': True,
                    'pode_verificar_integridade_cadeia_hash_fiscal': True,
                },
            )

            dept, _ = Departamento.objects.get_or_create(
                codigo='DEP-001',
                defaults={'nome': 'Administração Geral', 'ativo': True},
            )

            bi_placeholder = f"SUP{user.id:011d}"[:14]
            funcionario, _ = Funcionario.objects.update_or_create(
                usuario=user,
                defaults={
                    'cargo':         cargo,
                    'departamento':  dept,
                    'nome_completo': user.username.upper(),
                    'bi':            bi_placeholder,
                    'data_nascimento': date(2000, 1, 1),
                    'sexo':          'O',
                    'endereco':      'A definir',
                    'numero':        'S/N',
                    'bairro':        'A definir',
                    'cidade':        getattr(tenant_obj, 'cidade', 'Luanda') or 'Luanda',
                    'provincia':     getattr(tenant_obj, 'provincia', 'Luanda') or 'Luanda',
                    'postal':        '0000000',
                    'data_admissao': timezone.now().date(),
                    'salario_atual': 1.00,
                    'ativo':         True,
                },
            )

            app_labels = [
                'produtos', 'analytics', 'clientes', 'vendas', 'funcionarios',
                'fiscal', 'saft', 'financeiro', 'estoque', 'fornecedores',
                'compras', 'relatorios', 'configuracoes', 'servicos',
            ]
            perms = Permission.objects.filter(content_type__app_label__in=app_labels)
            user.user_permissions.set(perms)

            if not user.is_staff:
                user.is_staff = True
                user.save(update_fields=['is_staff'])

    print(f"✔ Estrutura administrativa preparada no tenant '{schema_name}'.")
    print(f"⚠ Funcionário '{funcionario.nome_completo}' usa dados placeholder; complete no painel.")


# ──────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────────────────────────────────────

def listar_empresas():
    format_header("Empresas / Tenants Cadastrados")
    with schema_context(PUBLIC_SCHEMA):
        empresas = Empresa.objects.all().order_by('id')
        if not empresas.exists():
            print("ℹ Nenhuma empresa cadastrada.")
            return
        for emp in empresas:
            ativa = '✔' if emp.ativa else '✘'
            print(f"ID: {emp.id:<4} | {ativa} | Schema: {emp.schema_name:<20} | Nome: {emp.nome}")


def listar_usuarios():
    format_header("Usuários do Sistema — Schema Public")
    with schema_context(PUBLIC_SCHEMA):
        usuarios = Usuario.objects.all().order_by('id')
        if not usuarios.exists():
            print("ℹ Nenhum usuário cadastrado.")
            return
        for user in usuarios:
            sup = '⭐ superuser' if user.is_superuser else ''
            print(f"ID: {user.id:<4} | User: {user.username:<20} | Email: {user.email:<35} | {sup}")


def listar_dominios():
    format_header("Domínios Cadastrados")
    with schema_context(PUBLIC_SCHEMA):
        dominios = Domain.objects.all().select_related('tenant').order_by('tenant__id')
        if not dominios.exists():
            print("ℹ Nenhum domínio cadastrado.")
            return
        for dom in dominios:
            primario = '(principal)' if dom.is_primary else ''
            print(f"ID: {dom.id:<4} | Domínio: {dom.domain:<35} | Tenant: {dom.tenant.schema_name} {primario}")


def resetar_senha_usuario():
    format_header("Resetar Senha de Usuário")
    u_id   = input("ID do Usuário: ").strip()
    nova   = getpass("Nova Senha: ")
    conf   = getpass("Confirmar Nova Senha: ")

    if nova != conf:
        print("❌ As senhas não coincidem.")
        return
    if not nova:
        print("❌ A senha não pode estar vazia.")
        return

    with schema_context(PUBLIC_SCHEMA):
        try:
            user = Usuario.objects.get(id=u_id)
            user.set_password(nova)
            user.save(update_fields=['password'])
            print(f"✔ Senha de '{user.username}' actualizada.")
        except Usuario.DoesNotExist:
            print("❌ Usuário não encontrado.")
        except Exception as exc:
            print(f"❌ Erro: {exc}")


def apagar_empresa():
    format_header("Apagar Empresa / Tenant")
    e_id = input("ID da Empresa: ").strip()

    with schema_context(PUBLIC_SCHEMA):
        try:
            emp = Empresa.objects.get(id=e_id)
            if emp.schema_name == PUBLIC_SCHEMA:
                print("❌ Não é permitido apagar o schema 'public'.")
                return

            confirmacao = input(
                f"⚠️ Apagar '{emp.nome}' e o schema '{emp.schema_name}' (TODOS os dados)? (s/n): "
            ).strip().lower()
            if confirmacao != 's':
                print("❌ Operação cancelada.")
                return
            if not confirmar_producao("apagar este tenant"):
                return

            # force_drop=True: sem isto o django-tenants só apaga o schema se o
            # modelo tiver auto_drop_schema=True; caso contrário o registo some e
            # o schema fica órfão na base de dados. O Domain cai por CASCADE.
            emp.delete(force_drop=True)
            print("✔ Tenant, schema e domínios removidos com sucesso.")

        except Empresa.DoesNotExist:
            print("❌ Empresa não encontrada.")
        except Exception as exc:
            print(f"❌ Erro: {exc}")


def apagar_usuario():
    format_header("Apagar Usuário")
    u_id = input("ID do Usuário: ").strip()

    with schema_context(PUBLIC_SCHEMA):
        try:
            user = Usuario.objects.get(id=u_id)
            if user.is_superuser:
                print("❌ Por segurança, este console não apaga superusers globais.")
                return

            conf = input(f"⚠️ Apagar o usuário '{user.username}'? (s/n): ").strip().lower()
            if conf != 's':
                print("❌ Operação cancelada.")
                return

            user.delete()
            print("✔ Usuário removido com sucesso.")

        except Usuario.DoesNotExist:
            print("❌ Usuário não encontrado.")
        except Exception as exc:
            print(f"❌ Erro: {exc}")


def verificar_licenca_tenant():
    format_header("Verificar Licença de um Tenant")
    e_id = input("ID ou Schema da Empresa: ").strip()

    try:
        emp = obter_empresa(e_id)
        with schema_context(PUBLIC_SCHEMA):
            from apps.licenca.models import Licenca
            try:
                lic = Licenca.objects.get(empresa=emp)
                print(f"\n  Empresa    : {emp.nome} ({emp.schema_name})")
                print(f"  Plano      : {lic.plano.nome}")
                print(f"  Status     : {lic.status}")
                print(f"  Início     : {lic.data_inicio}")
                print(f"  Vencimento : {lic.data_vencimento}")
                print(f"  Vencida?   : {'SIM ⚠' if lic.esta_vencida else 'Não'}")
                print(f"  Dias p/ vencer: {lic.dias_para_vencer}")
            except Licenca.DoesNotExist:
                print(f"  ⚠ Empresa '{emp.schema_name}' não tem licença registada.")

    except Empresa.DoesNotExist:
        print("❌ Empresa não encontrada.")
    except Exception as exc:
        print(f"❌ Erro: {exc}")


def _estado_ambiente_agt():
    """Resumo do que é do SISTEMA (variáveis de ambiente), sem mostrar segredos."""
    print("  ── Sistema (.env) ──")
    print(f"  AGT_ENVIRONMENT        : {getattr(settings, 'AGT_ENVIRONMENT', '') or '(NÃO definido)'}")
    for nome in ('AGT_BASE_URL_HOMOLOGACAO', 'AGT_BASE_URL_PRODUCAO'):
        print(f"  {nome:<23}: {'definida' if getattr(settings, nome, '') else '(não definida)'}")
    print(f"  AGT_API_USERNAME       : {'definido' if getattr(settings, 'AGT_API_USERNAME', '') else '(NÃO definido)'}")
    print(f"  AGT_API_PASSWORD       : {'definida' if getattr(settings, 'AGT_API_PASSWORD', '') else '(NÃO definida)'}")
    software_ok = bool(getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY_PEM', '')
                       or getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY_PATH', ''))
    print(f"  Chave do software (SOTARQ): {'definida' if software_ok else '(NÃO definida)'}")


def verificar_assinatura_tenant():
    format_header("Verificar AssinaturaDigital de um Tenant")
    e_id = input("ID ou Schema da Empresa: ").strip()

    try:
        emp = obter_empresa(e_id)

        with schema_context(emp.schema_name):
            from apps.fiscal.models import AssinaturaDigital
            config = AssinaturaDigital.objects.filter(pk=1).first()
            print(f"\n  ── Tenant: {emp.schema_name} ──")
            if config is None:
                print("  Sem registo de assinatura (chaves nunca configuradas).")
            else:
                print(f"  NIF Contribuinte : {config.nif_contribuinte or '(não preenchido)'}")
                print(f"  Chave privada    : {'gravada (cifrada)' if config.chave_contribuinte_privada else 'em falta'}")
                print(f"  Chave pública    : {'gravada' if config.chave_contribuinte_publica else 'em falta'}")
                print(f"  Configurada?     : {'SIM ✔' if config.esta_configurada else 'NÃO ✘'}")
                if config.data_configuracao_chave:
                    print(f"  Configurada em   : {config.data_configuracao_chave}")
        print()
        _estado_ambiente_agt()

    except Empresa.DoesNotExist:
        print("❌ Empresa não encontrada.")
    except Exception as exc:
        print(f"❌ Erro: {exc}")


def testar_conexao_agt():
    """Chamada REAL e assinada a listarSeries, só-leitura (não grava séries)."""
    format_header("Testar Conexão à API AGT (listarSeries)")
    e_id = input("ID ou Schema da Empresa: ").strip()

    try:
        emp = obter_empresa(e_id)
        if emp.schema_name == PUBLIC_SCHEMA:
            print("❌ Escolha um tenant empresarial (as chaves do contribuinte são por tenant).")
            return

        from apps.fiscal.services.agt_client import AGTClient, AGTError

        client = AGTClient()
        print(f"  Ambiente : {client.ambiente}")
        print(f"  URL base : {client.base_url}")
        if not AGTClient.credenciais_configuradas():
            print("❌ AGT_API_USERNAME / AGT_API_PASSWORD não estão definidos no ambiente.")
            return
        if client.ambiente == 'PRODUCTION' and not confirmar_producao("consultar a AGT em PRODUÇÃO"):
            return

        with schema_context(emp.schema_name):
            try:
                series = client.listar_series()
            except AGTError as exc:
                print(f"❌ A AGT respondeu com erro: {exc}")
                if exc.erros:
                    for e in exc.erros:
                        print(f"     - {e}")
                if exc.rede:
                    print("  (falha de rede/timeout — resultado desconhecido)")
                return

        print(f"✔ Resposta válida da AGT. {len(series)} série(s) devolvida(s) (nada foi gravado).")
        for info in series[:10]:
            print(f"   - {info.get('documentType', '?'):<3} {info.get('seriesCode', '?'):<20} "
                  f"ano {info.get('seriesYear', '?')} estado {info.get('seriesStatus', '?')}")
        if len(series) > 10:
            print(f"   ... e mais {len(series) - 10}.")

    except Empresa.DoesNotExist:
        print("❌ Empresa não encontrada.")
    except Exception as exc:
        print(f"❌ Erro: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 11. RESETAR BANCO
# ──────────────────────────────────────────────────────────────────────────────

def resetar_banco():
    """
    OPERAÇÃO DESTRUTIVA. Remove todos os tenants empresariais, os seus domínios e
    os utilizadores não-superuser. Mantém o tenant 'public', o seu domínio e os
    superusers.
    """
    format_header("⚠️ RESETAR BANCO — OPERAÇÃO IRREVERSÍVEL ⚠️")

    if not confirmar_producao("RESETAR O BANCO"):
        return

    with schema_context(PUBLIC_SCHEMA):
        tenants_a_apagar = list(Empresa.objects.exclude(schema_name=PUBLIC_SCHEMA))
        dominios_a_apagar = Domain.objects.exclude(tenant__schema_name=PUBLIC_SCHEMA)
        total_dominios    = dominios_a_apagar.count()
        usuarios_a_apagar = list(Usuario.objects.filter(is_superuser=False))
        total_superusers  = Usuario.objects.filter(is_superuser=True).count()

    if not tenants_a_apagar and total_dominios == 0 and not usuarios_a_apagar:
        print("ℹ Nada a resetar: já existe apenas a área global.")
        return

    print("\nEsta acção vai apagar PERMANENTEMENTE:")
    print(f"  • {len(tenants_a_apagar)} tenant(s) e seus schemas físicos:")
    for t in tenants_a_apagar:
        print(f"    - ID:{t.id:<4} | Schema:{t.schema_name:<20} | {t.nome}")
    print(f"  • {total_dominios} domínio(s) de tenants empresariais")
    print(f"  • {len(usuarios_a_apagar)} utilizador(es) não-superuser")
    print("\nSerá MANTIDO:")
    print(f"  • schema public e o seu domínio | {total_superusers} superuser(s) | catálogo de licenciamento")

    if input("\nTens a CERTEZA? (s/n): ").strip().lower() != 's':
        print("❌ Operação cancelada.")
        return

    if input("Escreve 'RESETAR TUDO' para confirmar: ").strip() != 'RESETAR TUDO':
        print("❌ Frase incorrecta. Operação cancelada.")
        return

    try:
        with schema_context(PUBLIC_SCHEMA):
            with transaction.atomic():
                # Domínios dos tenants empresariais (o do public é preservado).
                Domain.objects.exclude(tenant__schema_name=PUBLIC_SCHEMA).delete()

                # force_drop=True: apaga também o schema físico (ver apagar_empresa).
                for tenant in tenants_a_apagar:
                    tenant.delete(force_drop=True)

                Usuario.objects.filter(is_superuser=False).delete()

        print("\n✔ RESET CONCLUÍDO:")
        print(f"   • {len(tenants_a_apagar)} tenant(s) removido(s)")
        print(f"   • {total_dominios} domínio(s) removido(s)")
        print(f"   • {len(usuarios_a_apagar)} utilizador(es) removido(s)")
        print("ℹ schema public, o seu domínio e os superusers permanecem intactos.")

    except Exception as exc:
        print(f"❌ Erro crítico durante o reset: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# MENU PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def menu():
    dj_version = django.get_version()

    while True:
        env_label = 'PRODUÇÃO ⚡' if EM_PRODUCAO else 'Desenvolvimento'
        print(f"\n{'=' * 50}")
        print("  SOTARQ VENDOR — Console Supremo")
        print(f"  Django {dj_version} | Ambiente: {env_label}")
        print(f"{'=' * 50}")
        print("  00. Configurar Infra Base (PUBLIC)")
        print("   1. Criar Domínio Global")
        print("   2. Criar Superuser Global")
        print("   3. Criar Empresa + Admin (Full Setup)")
        print("   4. Listar Empresas")
        print("   5. Listar Usuários")
        print("   6. Aplicar Migrações a Tenant")
        print("   7. Apagar Empresa/Tenant")
        print("   8. Apagar Usuário")
        print("   9. Resetar Senha")
        print("  10. Empossar Admin em Tenant Existente")
        print("  11. ⚠️  Resetar Banco")
        print("  12. Listar Domínios")
        print("  13. Verificar Licença de Tenant")
        print("  14. Verificar Assinatura Fiscal + ambiente AGT")
        print("  15. Testar Conexão à API AGT (listarSeries)")
        print("   0. Sair")

        opcao = input("\nEscolha uma opção: ").strip()

        try:
            if   opcao == "00": configurar_public_inicial()
            elif opcao == "1":  criar_dominio_global()
            elif opcao == "2":  criar_superuser_global()
            elif opcao == "3":  criar_empresa_completa()
            elif opcao == "4":  listar_empresas()
            elif opcao == "5":  listar_usuarios()
            elif opcao == "6":  aplicar_migracoes_tenant()
            elif opcao == "7":  apagar_empresa()
            elif opcao == "8":  apagar_usuario()
            elif opcao == "9":  resetar_senha_usuario()
            elif opcao == "10": vincular_admin_supremo_tenant()
            elif opcao == "11": resetar_banco()
            elif opcao == "12": listar_dominios()
            elif opcao == "13": verificar_licenca_tenant()
            elif opcao == "14": verificar_assinatura_tenant()
            elif opcao == "15": testar_conexao_agt()
            elif opcao == "0":
                print("Saindo...")
                return
            else:
                print("❌ Opção inválida.")

        except KeyboardInterrupt:
            print("\n\n⚠ Operação interrompida pelo utilizador.")
        except Exception as exc:
            print(f"\n❌ Erro não tratado: {exc}")


if __name__ == '__main__':
    menu()
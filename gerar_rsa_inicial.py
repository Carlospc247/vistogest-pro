import os
import sys
import django

# RIGOR SOTARQ: Identificação dinâmica de ambiente
if os.environ.get('RENDER'):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django.setup()

from django_tenants.utils import (
    get_tenant_model,
    get_public_schema_name,
    schema_context,
)
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService

# Resolução dinâmica do modelo de Tenant
Empresa = get_tenant_model()


def preparar_soberania_fiscal(identificador):
    """
    RIGOR SOTARQ: Gera chaves RSA 2048 e blinda a chave privada no banco via AES-256.
    Aceita ID numérico ou o nome do schema (ex: 'mundo_maquinas' ou '1').
    """
    public_schema = get_public_schema_name()

    # 1. Localizar a empresa/tenant no schema 'public'
    with schema_context(public_schema):
        try:
            if str(identificador).isdigit():
                empresa = Empresa.objects.get(id=int(identificador))
            else:
                empresa = Empresa.objects.get(schema_name=identificador)
        except Empresa.DoesNotExist:
            print(f"✘ ERRO: Empresa com identificador '{identificador}' não foi encontrada no schema '{public_schema}'.")
            return
        except Exception as e:
            print(f"✘ ERRO ao buscar a empresa: {e}")
            return

    print(f"--- Iniciando Soberania Fiscal: {empresa.nome} (Schema: '{empresa.schema_name}') ---")

    # 2. Executar a geração no schema isolado do Tenant
    try:
        with schema_context(empresa.schema_name):
            print("[1/2] Gerando par RSA 2048 e encriptando chave privada...")
            
            # Chama o serviço de assinatura digital no contexto do tenant
            assinatura = AssinaturaDigitalService.gerar_chaves_rsa(empresa=empresa)

            # Validar se as chaves foram persistidas no modelo de TENANT_APPS
            if assinatura and getattr(assinatura, 'chave_privada', None) and getattr(assinatura, 'chave_publica', None):
                print(f"[2/2] Chaves RSA persistidas com sucesso no schema: '{empresa.schema_name}'")
                print(f"✔ SUCESSO: Empresa '{empresa.nome}' pronta para faturar com integridade AGT!")
            else:
                print("✘ FALHA: As chaves não foram geradas/persistidas corretamente.")

    except Exception as e:
        print(f"✘ ERRO CRÍTICO SOTARQ no schema '{empresa.schema_name}': {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python gerar_rsa_inicial.py <ID_OU_SCHEMA_DA_EMPRESA>")
        print("Exemplos:")
        print("  python gerar_rsa_inicial.py 1")
        print("  python gerar_rsa_inicial.py mundo_maquinas")
    else:
        preparar_soberania_fiscal(sys.argv[1])
#python gerar_rsa_inicial.py 25
#(Substitua 25 pelo ID real da empresa que você acabou de criar).
import os
import django

# RIGOR SOTARQ: Identificação dinâmica de ambiente
# Se a variável RENDER existir, usa production. Caso contrário, development.
if os.environ.get('RENDER'):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmassys.settings.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmassys.settings.development")

django.setup()

from django_tenants.utils import schema_context
from apps.empresas.models import Empresa
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService
from apps.fiscal.models import AssinaturaDigital

def preparar_soberania_fiscal(empresa_id):
    """
    RIGOR SOTARQ: Gera chaves RSA 2048 e blinda a privada no banco via AES-256.
    """
    try:
        empresa = Empresa.objects.get(id=empresa_id)
        print(f"--- Iniciando Soberania Fiscal: {empresa.nome} (ID: {empresa_id}) ---")

        # Entrar no contexto do schema para garantir integridade multi-tenant
        with schema_context(empresa.schema_name):
            
            # 1. Gerar Chaves via Serviço Oficial (que já usa seu novo AESService)
            print("[1/2] Gerando par RSA 2048 e encriptando chave privada...")
            assinatura = AssinaturaDigitalService.gerar_chaves_rsa(empresa)
            
            # 2. Validar se gravou corretamente
            if assinatura.chave_privada and assinatura.chave_publica:
                print(f"[2/2] Chaves persistidas no schema: {empresa.schema_name}")
                print(f"✔ SUCESSO: Empresa {empresa.nome} pronta para faturar com integridade AGT.")
            else:
                print("✘ FALHA: As chaves não foram geradas corretamente.")

    except Empresa.DoesNotExist:
        print(f"✘ ERRO: Empresa com ID {empresa_id} não encontrada no banco principal.")
    except Exception as e:
        print(f"✘ ERRO CRÍTICO SOTARQ: {str(e)}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python gerar_rsa_inicial.py <ID_DA_EMPRESA>")
    else:
        preparar_soberania_fiscal(sys.argv[1])
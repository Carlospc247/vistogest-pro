# scripts/run_saft_test.py
import os
import django
from datetime import datetime, date

# Configuração do Ambiente Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings')
django.setup()

# Imports Necessários
from apps.empresas.models import Empresa 
from apps.saft.services.saft_xml_generator_service import SaftXmlGeneratorService
from apps.saft.utils.saft_validator import SaftValidator 
#from scripts.seed_data import create_test_transactions # 🚨 Assumindo um script de seed

def run_saft_generation_and_validation():
    print("--- INÍCIO DO TESTE DE CONFORMIDADE SAF-T ---")

    # 1. Preparar o Ambiente
    try:
        empresa_teste = Empresa.objects.get(nif="5000000000") # Usar a sua NIF de teste
    except Empresa.DoesNotExist:
        print("ERRO: Empresa de teste não encontrada. Crie uma instância.")
        return

    # 2. Inserir Dados de Teste
    start_date = datetime(date.today().year, 1, 1)
    end_date = datetime.now()
    # create_test_transactions(empresa_teste, start_date, end_date) # 🚨 Descomentar quando o seed estiver pronto
    print("Dados de teste preparados na base de dados.")


    # 3. Geração do XML
    print(f"\nGerando SAF-T para o período: {start_date.date()} a {end_date.date()}...")
    generator = SaftXmlGeneratorService(empresa_teste, start_date, end_date)
    xml_content = generator.generate_xml() # Chama o método que retorna a string XML

    # 4. Validação do XML
    validator = SaftValidator()
    validation_errors = validator.validate_xml_string(xml_content)

    if validation_errors:
        print("\n--- RESULTADO CRÍTICO: FALHA NA CONFORMIDADE ---")
        for error in validation_errors:
            print(f"  > {error}")
        print("\nCORREÇÃO URGENTE NECESSÁRIA.")
    else:
        print("\n--- RESULTADO: SAF-T PRONTO PARA PRODUÇÃO ---")
        # O XML pode ser salvo aqui:
        with open('saft_final.xml', 'w', encoding='utf-8') as f:
            f.write(xml_content)
    
    if not validation_errors:
        print("\n--- RESULTADO: SAF-T PRONTO PARA PRODUÇÃO ---")
        
        # 🚨 CÓDIGO PARA CRIAR O FICHEIRO .XML
        file_name = f"SAFT_AO_{empresa_teste.nif}_{start_date.year}{start_date.month:02d}_{end_date.year}{end_date.month:02d}.xml"
        output_path = os.path.join(os.getcwd(), 'saft_output', file_name) # Salvar na pasta 'saft_output'
        
        # Criar a pasta se não existir
        os.makedirs(os.path.dirname(output_path), exist_ok=True) 
        
        # Salvar o conteúdo XML validado
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
            
        print(f"✅ Ficheiro XML criado e salvo em: {output_path}")

if __name__ == '__main__':
    run_saft_generation_and_validation()


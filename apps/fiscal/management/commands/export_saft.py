# export_saft vai usar direta,ente o serviço SaftXmlGeneratorService
import os
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context
from datetime import datetime
from apps.empresas.models import Empresa
from apps.saft.services.saft_xml_generator_service import SaftXmlGeneratorService

class Command(BaseCommand):
    """
    Comando Unificado SOTARQ: Exporta o SAF-T AO 1.01_01.
    Utiliza o SaftXmlGeneratorService para garantir conformidade com Namespaces AGT.
    """
    help = 'Exporta o ficheiro SAF-T (Angola) garantindo integridade de schema e multi-tenancy.'

    def add_arguments(self, parser):
        parser.add_argument('--empresa_id', type=int, required=True, help='ID da Empresa')
        parser.add_argument('--data_inicio', type=str, required=True, help='Formato YYYY-MM-DD')
        parser.add_argument('--data_fim', type=str, required=True, help='Formato YYYY-MM-DD')
        parser.add_argument('--output', type=str, default=None, help='Nome personalizado do ficheiro .xml')

    def handle(self, *args, **options):
        empresa_id = options['empresa_id']
        
        try:
            inicio = datetime.strptime(options['data_inicio'], '%Y-%m-%d').date()
            fim = datetime.strptime(options['data_fim'], '%Y-%m-%d').date()
        except ValueError:
            raise CommandError("Data inválida. Use o padrão YYYY-MM-DD.")

        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            raise CommandError(f"Empresa ID {empresa_id} não encontrada no schema public.")

        # RIGOR SOTARQ: Todo o processamento ocorre dentro do Schema do Cliente
        with schema_context(empresa.schema_name):
            self.stdout.write(self.style.NOTICE(f"--- Iniciando Exportação SOTARQ: {empresa.nome} ---"))
            
            try:
                # Inicializa o serviço unificado
                generator = SaftXmlGeneratorService(empresa, inicio, fim)
                
                # Gera o conteúdo XML em bytes
                xml_bytes = generator.generate_xml(None)
                
                # Define o nome do arquivo
                if options['output']:
                    filename = options['output']
                else:
                    filename = f"SAFT_{empresa.nif}_{inicio.strftime('%Y%m')}.xml"

                # Escrita física do ficheiro
                with open(filename, 'wb') as f:
                    # Adiciona o cabeçalho XML padrão que o ElementTree às vezes omite
                    f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                    f.write(xml_bytes)

                self.stdout.write(self.style.SUCCESS(f"✔ Sucesso: Ficheiro '{filename}' gerado no diretório raiz."))
                self.stdout.write(self.style.NOTICE(f"Consistência: Versão AO_1.01_01 | Schema: {empresa.schema_name}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✘ Erro na geração do XML: {str(e)}"))
                raise CommandError("Falha crítica na exportação SAF-T.")
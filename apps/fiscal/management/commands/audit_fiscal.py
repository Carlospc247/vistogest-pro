# verificar integridade das assinaturas digital dos tenants. COnfirmar se tentaram manipular
import logging
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context
from apps.empresas.models import Empresa
from apps.fiscal.services.assinatura_service import VerificadorIntegridadeService
from django.utils import timezone

logger = logging.getLogger('fiscal.audit')

class Command(BaseCommand):
    help = 'Executa auditoria de integridade da cadeia de hash e assinaturas RSA em todos os tenants.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(f"--- INICIANDO AUDITORIA FISAL SOTARQ ({timezone.now().strftime('%d/%m/%Y %H:%M')}) ---"))
        
        # Filtra apenas tenants reais (exclui o public)
        tenants = Empresa.objects.exclude(schema_name='public')
        
        resumo_sucesso = 0
        resumo_falha = 0
        total_erros = 0

        for tenant in tenants:
            self.stdout.write(self.style.WARNING(f"\n[AUDITORIA] Empresa: {tenant.nome} (Schema: {tenant.schema_name})"))
            
            # Muda o contexto para o schema do cliente para validar as faturas dele
            with schema_context(tenant.schema_name):
                try:
                    sucesso, erros = VerificadorIntegridadeService.verificar_empresa(tenant.id)
                    
                    if sucesso:
                        self.stdout.write(self.style.SUCCESS(f"  ✔ INTEGRIDADE OK: Cadeia de documentos validada."))
                        resumo_sucesso += 1
                    else:
                        self.stdout.write(self.style.ERROR(f"  ✘ FALHA DETECTADA: Encontrados {len(erros)} erros de integridade."))
                        for erro in erros:
                            self.stdout.write(f"    - {erro}")
                        resumo_falha += 1
                        total_erros += len(erros)
                
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ⚠ ERRO CRÍTICO NO SCHEMA: {str(e)}"))
                    resumo_falha += 1

        # Relatório Final
        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "="*50))
        self.stdout.write(self.style.MIGRATE_HEADING(" RELATÓRIO FINAL DE AUDITORIA SOTARQ "))
        self.stdout.write(self.style.MIGRATE_HEADING("="*50))
        self.stdout.write(f"Empresas Auditadas: {tenants.count()}")
        self.stdout.write(self.style.SUCCESS(f"Empresas Saudáveis: {resumo_sucesso}"))
        if resumo_falha > 0:
            self.stdout.write(self.style.ERROR(f"Empresas com Falhas: {resumo_falha}"))
            self.stdout.write(self.style.ERROR(f"Total de Violações: {total_erros}"))
        else:
            self.stdout.write(self.style.SUCCESS("Conclusão: Sistema 100% em conformidade com as normas AGT."))
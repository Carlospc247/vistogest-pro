# apps/licenca/management/commands/verificar_licencas.py
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from apps.licenca.models import Licenca
from datetime import date, timedelta

class Command(BaseCommand):
    help = 'Verifica licenças próximas ao vencimento e envia alertas'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=30,
            help='Dias de antecedência para alertar (padrão: 30)'
        )
        parser.add_argument(
            '--enviar-email',
            action='store_true',
            help='Enviar emails de alerta'
        )
    
    def handle(self, *args, **options):
        dias_alerta = options['dias']
        enviar_email = options['enviar_email']
        
        # Data limite para alertas
        data_limite = date.today() + timedelta(days=dias_alerta)
        
        # Busca licenças vencendo
        licencas_vencendo = Licenca.objects.filter(
            ativa=True,
            data_expiracao__lte=data_limite,
            data_expiracao__gt=date.today()
        ).select_related('empresa')
        
        # Busca licenças já vencidas
        licencas_vencidas = Licenca.objects.filter(
            ativa=True,
            data_expiracao__lt=date.today()
        ).select_related('empresa')
        
        self.stdout.write(f"Encontradas {len(licencas_vencendo)} licenças vencendo em {dias_alerta} dias")
        self.stdout.write(f"Encontradas {len(licencas_vencidas)} licenças já vencidas")
        
        # Exibe licenças vencendo
        if licencas_vencendo:
            self.stdout.write("\n=== LICENÇAS VENCENDO ===")
            for licenca in licencas_vencendo:
                dias_restantes = (licenca.data_expiracao - date.today()).days
                self.stdout.write(
                    f"• {licenca.license_key} - {licenca.empresa.nome} "
                    f"(vence em {dias_restantes} dias - {licenca.data_expiracao})"
                )
        
        # Exibe licenças vencidas
        if licencas_vencidas:
            self.stdout.write("\n=== LICENÇAS VENCIDAS ===")
            for licenca in licencas_vencidas:
                dias_vencida = (date.today() - licenca.data_expiracao).days
                self.stdout.write(
                    f"• {licenca.license_key} - {licenca.empresa.nome} "
                    f"(vencida há {dias_vencida} dias - {licenca.data_expiracao})"
                )
        
        # Envio de emails
        if enviar_email and (licencas_vencendo or licencas_vencidas):
            self._enviar_alertas_email(licencas_vencendo, licencas_vencidas)
        
        self.stdout.write(
            self.style.SUCCESS(f"Verificação concluída! Total processado: {len(licencas_vencendo) + len(licencas_vencidas)}")
        )
    
    def _enviar_alertas_email(self, licencas_vencendo, licencas_vencidas):
        """Envia emails de alerta para administradores"""
        try:
            # Email para administradores
            admins_emails = [email for name, email in settings.ADMINS]
            if not admins_emails:
                self.stdout.write("Nenhum email de admin configurado")
                return
            
            # Monta conteúdo do email
            conteudo = ["ALERTA DE LICENÇAS - \n"]
            
            if licencas_vencidas:
                conteudo.append("=== LICENÇAS VENCIDAS ===")
                for licenca in licencas_vencidas:
                    dias_vencida = (date.today() - licenca.data_expiracao).days
                    conteudo.append(
                        f"• {licenca.license_key} - {licenca.empresa.nome} "
                        f"(vencida há {dias_vencida} dias)"
                    )
                conteudo.append("")
            
            if licencas_vencendo:
                conteudo.append("=== LICENÇAS VENCENDO ===")
                for licenca in licencas_vencendo:
                    dias_restantes = (licenca.data_expiracao - date.today()).days
                    conteudo.append(
                        f"• {licenca.license_key} - {licenca.empresa.nome} "
                        f"(vence em {dias_restantes} dias)"
                    )
            
            conteudo.append("\n\nAcesse o admin do sistema para renovar as licenças.")
            
            send_mail(
                subject='[Vistogest] Alerta de Licenças',
                message='\n'.join(conteudo),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admins_emails,
                fail_silently=False
            )
            
            self.stdout.write("Emails de alerta enviados com sucesso!")
            
        except Exception as e:
            self.stderr.write(f"Erro ao enviar emails: {e}")
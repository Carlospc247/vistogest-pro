from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Testa as credenciais de SMTP configuradas no production.py'

    def handle(self, *args, **options):
        self.stdout.write(f"Iniciando teste de e-mail para: {settings.EMAIL_HOST}")
        try:
            send_mail(
                'SOTARQ TESTE - VistoGEST',
                'Se você recebeu isto, o SMTP do production.py está 100% OK.',
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('SUCESSO: E-mail enviado com sucesso!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'FALHA: Erro ao enviar e-mail: {str(e)}'))
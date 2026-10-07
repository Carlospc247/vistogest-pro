# apps/parceiros/management/commands/criar_partner.py
"""
Management command: criar_partner
Uso: python manage.py criar_partner --settings=config.settings.development
"""
from getpass import getpass
from django.core.management.base import BaseCommand
from apps.parceiros.services import PartnerService, PartnerServiceError


class Command(BaseCommand):
    help = 'Cria um novo parceiro interactivamente via CLI'

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('\n=== Criar Novo Parceiro ===\n'))
        dados = {
            'nome':      input('Nome completo / Empresa: ').strip(),
            'tipo':      input('Tipo [empresa/pessoa_singular]: ').strip() or 'empresa',
            'nif':       input('NIF: ').strip(),
            'email':     input('Email: ').strip(),
            'telefone':  input('Telefone: ').strip(),
            'username':  input('Username (acesso ao portal): ').strip(),
            'password':  getpass('Password: '),
        }
        confirmar = getpass('Confirmar password: ')
        if dados['password'] != confirmar:
            self.stderr.write('As passwords não coincidem.')
            return

        # Usar o primeiro superuser como criado_por
        from django.contrib.auth import get_user_model
        User = get_user_model()
        criado_por = User.objects.filter(is_superuser=True).first()
        if not criado_por:
            self.stderr.write('Nenhum superuser encontrado. Crie um primeiro.')
            return

        try:
            partner = PartnerService.criar_partner(dados, criado_por)
            self.stdout.write(self.style.SUCCESS(
                f"\n✔ Parceiro '{partner.nome}' criado (ID: {partner.pk}).\n"
                f"  Username: {partner.usuario.username}\n"
                f"  URL portal: /portal-parceiros/\n"
            ))
        except PartnerServiceError as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))

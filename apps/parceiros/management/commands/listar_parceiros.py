# apps/parceiros/management/commands/listar_parceiros.py
"""Lista parceiros com métricas do modelo comercial novo.

Uso: python manage.py listar_parceiros --settings=config.settings.development
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone
from django_tenants.utils import schema_context
from apps.parceiros.models import Partner, PartnerClient, PartnerAudit
from apps.parceiros.models_comercial import PartnerCommission


class Command(BaseCommand):
    help = 'Lista parceiros, estado de actividade, tenants e comissões'

    def handle(self, *args, **options):
        with schema_context('public'):
            partners = Partner.objects.order_by('nome').iterator(chunk_size=200)
            hoje = timezone.localdate()
            self.stdout.write(f"{'ID':<6} {'Parceiro':<30} {'Estado':<12} {'Tenants':>8} {'Última actividade':<18} {'Comissão paga':>18}")
            self.stdout.write('-' * 105)
            encontrou = False
            for partner in partners:
                encontrou = True
                ultima = PartnerAudit.objects.filter(
                    partner=partner,
                    acao__in=('CLIENT_CREATED', 'CLIENT_LICENSE_RENEWED'),
                ).order_by('-created_at').values_list('created_at', flat=True).first()
                ultima_data = timezone.localtime(ultima).date() if ultima else partner.created_at.date()
                total = PartnerClient.objects.filter(partner=partner).count()
                paga = PartnerCommission.objects.filter(partner=partner, status='paga').aggregate(v=Sum('valor_comissao'))['v'] or Decimal('0.00')
                self.stdout.write(
                    f"{partner.pk:<6} {partner.nome[:30]:<30} {partner.status:<12} {total:>8} "
                    f"{str(ultima_data):<18} {paga:>18,.2f} AOA"
                )
            if not encontrou:
                self.stdout.write('Nenhum parceiro cadastrado.')

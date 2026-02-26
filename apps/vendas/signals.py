from django.db import connection, models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from decimal import Decimal

from apps.vendas.models import Venda
from apps.clientes.models import Ponto
from apps.empresas.models import Empresa

@receiver(post_save, sender=Venda)
def gerar_pontos(sender, instance, created, **kwargs):
    """
    🎯 FIDELIZAÇÃO: Converte Kz em pontos para o cliente.
    Executado dentro do schema do Tenant.
    """
    if created and instance.cliente:
        # 1 ponto = 1 Kz gasto (Rigor de Cálculo)
        Ponto.objects.create(
            cliente=instance.cliente,
            valor=instance.total,
        )


@receiver(post_save, sender=Venda)
def alertar_venda_elite(sender, instance, created, **kwargs):
    """
    💎 MONITOR ELITE: Notifica a diretoria sobre faturamentos de alto valor.
    Email inserido manualmente para garantir estabilidade multi-tenant.
    """
    GATILHO_VALOR = 500000 # 500.000 Kz
    
    if created and instance.status == 'finalizada' and instance.total >= GATILHO_VALOR:
        try:
            # 1. Identificar a empresa no schema atual (Tenants compartilham a tabela Empresa no public)
            # O Django-tenants permite acessar a Empresa do schema atual com segurança.
            empresa = Empresa.objects.get(schema_name=connection.schema_name)
            
            # Verificação rigorosa do plano
            if empresa.plano and empresa.plano.nome.lower() == 'elite bypass':
                comissao = instance.total * Decimal('0.02')
                
                # 2. Preparar e-mail com contexto dinâmico
                subject = f"💎 COMISSÃO: {empresa.nome} faturou {instance.total:,.2f} Kz"
                contexto = {
                    'empresa_nome': empresa.nome,
                    'valor_venda': instance.total,
                    'valor_comissao': comissao,
                    'link_admin': "https://vistogest.com/bypass-control/"
                }
                
                html_message = render_to_string('emails/alerta_comissao.html', contexto)

                # 3. Disparo Direto (Hardcoded para carlosnhsebastiao@protonmail.com)
                send_mail(
                    subject,
                    f"Nova venda Elite de {instance.total} Kz", # Fallback texto
                    settings.DEFAULT_FROM_EMAIL,
                    ['carlosnhsebastiao@protonmail.com'], 
                    html_message=html_message,
                    fail_silently=True,
                )
        except Exception as e:
            # Em produção, falhas no sinal não devem impedir a conclusão da venda
            if settings.DEBUG:
                print(f"⚠️ Erro no Sinal Elite: {e}")
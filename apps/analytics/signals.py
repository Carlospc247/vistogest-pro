from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.forms.models import model_to_dict
from django.db import connection # RIGOR: Essencial para detectar o schema
import json

from .models import RegistroAuditoriaOperacional
from .services import AnalyticsService

# Lista rigorosa de apps monitoradas (TENANT_APPS)
APPS_MONITORADAS = [
    'produtos', 'analytics', 'fornecedores', 'estoque', 'clientes', 
    'vendas', 'funcionarios', 'servicos', 'comandas', 'financeiro', 
    'fiscal', 'compras'
]

# ============================================================
# AUDITORIA DE ACESSO (LOGIN)
# ============================================================
@receiver(user_logged_in)
def registrar_login_sucesso(sender, request, user, **kwargs):
    """Regista o evento de login no AnalyticsService."""
    # RIGOR 1: Se for o Administrador do Sistema no schema public, ignoramos
    if connection.schema_name == 'public':
        return

    empresa = getattr(user, 'empresa', None)
    
    # RIGOR 2: Se o usuário não tiver empresa vinculada, não há o que auditar no tenant
    if not empresa:
        return
        
    analytics_service = AnalyticsService(empresa=empresa, usuario=user)
    analytics_service.track_login(request)

# ============================================================
# AUDITORIA OPERACIONAL (CREATE, UPDATE, DELETE)
# ============================================================
@receiver(post_save)
def auditoria_pos_salvamento(sender, instance, created, **kwargs):
    """Monitora criações e atualizações de registros."""
    # RIGOR 3: Operações no schema PUBLIC não geram logs operacionais de tenant
    if connection.schema_name == 'public':
        return

    app_label = sender._meta.app_label
    
    if app_label in APPS_MONITORADAS:
        if sender == RegistroAuditoriaOperacional:
            return

        operacao = 'CREATE' if created else 'UPDATE'
        
        # RIGOR 4: Blindagem contra objetos sem empresa (ex: Superuser criando algo)
        empresa = getattr(instance, 'empresa', None)
        if not empresa:
            return

        user = getattr(instance, 'usuario_modificacao', None) or getattr(instance, 'usuario', None)

        # Rastreio de Ativos
        lote = None
        fab = None
        if app_label == 'produtos':
            if sender.__name__ == 'Lote':
                lote = instance
            elif hasattr(instance, 'fabricante'):
                fab = instance.fabricante
        elif hasattr(instance, 'lote'):
            lote = instance.lote

        RegistroAuditoriaOperacional.objects.create(
            empresa=empresa,
            usuario=user,
            app_origem=app_label,
            operacao=operacao,
            content_type=ContentType.objects.get_for_model(sender),
            object_id=instance.pk,
            dados_posteriores=json.dumps(model_to_dict(instance), default=str),
            lote_relacionado=lote,
            fabricante_relacionado=fab
        )

@receiver(post_delete)
def auditoria_pos_exclusao(sender, instance, **kwargs):
    """Monitora exclusões de registros."""
    if connection.schema_name == 'public':
        return

    app_label = sender._meta.app_label
    
    if app_label in APPS_MONITORADAS:
        if sender == RegistroAuditoriaOperacional:
            return

        empresa = getattr(instance, 'empresa', None)
        if not empresa:
            return

        user = getattr(instance, 'usuario', None)

        RegistroAuditoriaOperacional.objects.create(
            empresa=empresa,
            usuario=user,
            app_origem=app_label,
            operacao='DELETE',
            content_type=ContentType.objects.get_for_model(sender),
            object_id=instance.pk,
            dados_anteriores=json.dumps(model_to_dict(instance), default=str)
        )
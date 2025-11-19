# apps/fiscal/apps.py ou permissions.py
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from .models import AssinaturaDigital

def create_permissions():
    content_type = ContentType.objects.get_for_model(AssinaturaDigital)
    Permission.objects.get_or_create(
        codename='can_download_agt_keys',
        name='Pode baixar chaves da AGT',
        content_type=content_type,
    )

    # apps/fiscal/models.py
class Meta:
    permissions = [
        ("can_download_agt_keys", "Pode descarregar chaves públicas AGT"),
    ]


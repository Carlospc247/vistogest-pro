
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core_tenants'

    def ready(self):
        import apps.core_tenants.signals

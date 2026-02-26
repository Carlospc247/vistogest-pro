from django.apps import AppConfig


class AuditoriaPublicaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.auditoria_publica'
    verbose_name = 'SOTARQ - Auditoria de Infraestrutura'

    def ready(self):
            # Importa os sinais para que sejam registados quando a app iniciar
            import apps.auditoria_publica.signals

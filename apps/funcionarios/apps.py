from django.apps import AppConfig


class FuncionariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.funcionarios'

    def ready(self):
        from . import signals  # noqa: F401
from django.apps import AppConfig


class FuncionariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.funcionarios'

    def ready(self):
        # Importa os sinais quando a aplicação estiver pronta
        import apps.funcionarios.signals # Garante que o Django detecte os @receiver
        
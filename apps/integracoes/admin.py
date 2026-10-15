from django.contrib import admin

from .models import ConfiguracaoIntegracao, LogIntegracao, TipoIntegracao, WebhookIntegracao


@admin.register(TipoIntegracao)
class TipoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'codigo', 'categoria', 'ativo', 'ordem')


@admin.register(ConfiguracaoIntegracao)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ('tipo_integracao', 'ambiente', 'ativa', 'ultimo_teste_ok', 'ultima_sincronizacao')
    exclude = ('credenciais_criptografadas', 'webhook_segredo_cifrado')
    readonly_fields = ('webhook_token',)


@admin.register(LogIntegracao)
class LogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'configuracao', 'direcao', 'status', 'status_code', 'metodo')
    list_filter = ('status', 'direcao', 'configuracao')


@admin.register(WebhookIntegracao)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ('recebido_em', 'configuracao', 'evento', 'processado')
    list_filter = ('processado', 'configuracao')


from django.contrib import admin
from .models import PlanoConta

@admin.register(PlanoConta)
class PlanoContaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'classe', 'natureza', 'agrupamento_saft', 'aceita_lancamentos', 'ativa')
    list_filter = ('classe', 'natureza', 'agrupamento_saft', 'ativa', 'aceita_lancamentos')
    search_fields = ('codigo', 'nome', 'descricao')
    ordering = ('codigo',)
    list_per_page = 50

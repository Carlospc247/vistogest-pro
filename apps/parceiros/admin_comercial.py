# apps/parceiros/admin_comercial.py
"""Registo administrativo dos modelos comerciais e de comunicação.

Importar este módulo no fim de apps/parceiros/admin.py; não voltar a registar Partner.
"""
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse, NoReverseMatch
from django.utils.html import format_html
from django.utils import timezone

from apps.parceiros.models_comercial import (
    PartnerCommission, PartnerBusinessEvent, PartnerConversation,
    PartnerConversationParticipant, PartnerMessage, PartnerReactivationRequest,
)
from apps.parceiros.commercial_services import confirmar_comissao, marcar_comissao_paga, rejeitar_comissao, reativar_parceiro_superuser


@admin.register(PartnerCommission)
class PartnerCommissionAdmin(admin.ModelAdmin):
    list_display = ("partner", "partner_client", "tipo", "base_calculo", "percentagem", "valor_comissao", "status", "created_at")
    list_filter = ("status", "tipo", "created_at")
    search_fields = ("partner__nome", "partner_client__empresa__nome", "comprovativo_referencia")
    readonly_fields = tuple(f.name for f in PartnerCommission._meta.fields)
    fields = tuple(f.name for f in PartnerCommission._meta.fields)
    actions = ("confirmar_pagamento", "liquidar_comissao", "rejeitar_comissao")

    def has_add_permission(self, request):
        # As comissões só são criadas por eventos de negócio, nunca manualmente.
        return False

    def has_delete_permission(self, request, obj=None):
        # Livro-razão financeiro: corrigir por estorno/evento compensatório, não apagar.
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser or request.user.has_perm("parceiros.change_partnercommission"))

    @admin.action(description="Confirmar recebimento (reconhecer comissão de 10%)")
    def confirmar_pagamento(self, request, queryset):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.change_partnercommission")):
            raise PermissionDenied
        count = 0
        for row in queryset:
            try:
                confirmar_comissao(row.pk, request.user, referencia=row.comprovativo_referencia)
                count += 1
            except Exception as exc:
                self.message_user(request, f"Comissão #{row.pk}: {exc}", level=messages.ERROR)
        self.message_user(request, f"{count} pagamento(s) confirmado(s).")

    @admin.action(description="Marcar comissões confirmadas como pagas")
    def liquidar_comissao(self, request, queryset):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.change_partnercommission")):
            raise PermissionDenied
        count = 0
        for row in queryset:
            try:
                marcar_comissao_paga(row.pk, request.user, referencia=row.comprovativo_referencia)
                count += 1
            except Exception as exc:
                self.message_user(request, f"Comissão #{row.pk}: {exc}", level=messages.ERROR)
        self.message_user(request, f"{count} comissão(ões) liquidada(s).")

    @admin.action(description="Rejeitar pagamentos seleccionados")
    def rejeitar_comissao(self, request, queryset):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.change_partnercommission")):
            raise PermissionDenied
        count = 0
        for row in queryset.filter(status="aguarda_confirmacao"):
            try:
                rejeitar_comissao(row.pk, request.user, "Rejeitada pela equipa SOTARQ; contactar o parceiro para esclarecimentos.")
                count += 1
            except Exception as exc:
                self.message_user(request, f"Comissão #{row.pk}: {exc}", level=messages.ERROR)
        self.message_user(request, f"{count} registo(s) rejeitado(s).")


@admin.register(PartnerBusinessEvent)
class PartnerBusinessEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "partner", "tipo", "titulo", "resolvido", "visivel_parceiro")
    list_filter = ("tipo", "resolvido", "visivel_parceiro", "created_at")
    search_fields = ("partner__nome", "partner_client__empresa__nome", "titulo", "descricao")
    readonly_fields = tuple(f.name for f in PartnerBusinessEvent._meta.fields)
    actions = ("marcar_resolvidos",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Eventos comerciais são trilho de auditoria e não devem ser apagados.
        return False

    @admin.action(description="Marcar alertas seleccionados como resolvidos")
    def marcar_resolvidos(self, request, queryset):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.change_partnerbusinessevent")):
            raise PermissionDenied
        count = 0
        for evento in queryset.filter(resolvido=False):
            evento.marcar_resolvido(request.user)
            count += 1
        self.message_user(request, f"{count} evento(s) resolvido(s).")


class PartnerConversationParticipantInline(admin.TabularInline):
    model = PartnerConversationParticipant
    extra = 0
    fields = tuple(f.name for f in PartnerConversationParticipant._meta.fields)
    readonly_fields = tuple(f.name for f in PartnerConversationParticipant._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class PartnerMessageInline(admin.TabularInline):
    model = PartnerMessage
    extra = 0
    can_delete = False
    max_num = 0
    fields = ("created_at", "autor_display", "texto", "anexo_admin", "comissao")
    readonly_fields = ("created_at", "autor_display", "texto", "anexo_admin", "comissao")

    @admin.display(description="Autor")
    def autor_display(self, obj):
        return obj.autor_partner.nome if obj.autor_partner_id else str(obj.autor_usuario or "Sistema")

    @admin.display(description="Anexo (acesso autenticado)")
    def anexo_admin(self, obj):
        if not obj.anexo:
            return "—"
        try:
            url = reverse("parceiros:mensagem_anexo", kwargs={"pk": obj.pk})
        except NoReverseMatch:
            return obj.nome_original_anexo or "Anexo disponível (configurar rota de download)"
        return format_html('<a href="{}">Transferir {} (autenticado)</a>', url, obj.nome_original_anexo or "anexo")


@admin.register(PartnerConversation)
class PartnerConversationAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "ativa", "ultimo_evento_em", "created_at")
    list_filter = ("tipo", "ativa", "created_at")
    search_fields = ("titulo", "mensagens__texto", "participantes__partner__nome", "participantes__usuario__username")
    readonly_fields = tuple(f.name for f in PartnerConversation._meta.fields)
    fields = tuple(f.name for f in PartnerConversation._meta.fields)
    inlines = (PartnerConversationParticipantInline, PartnerMessageInline)

    def get_inline_instances(self, request, obj=None):
        """Não mostrar texto/anexos a quem só pode ver metadados das conversas."""
        instances = super().get_inline_instances(request, obj)
        if not (request.user.is_superuser or request.user.has_perm("parceiros.view_partnermessage")):
            instances = [inline for inline in instances if not isinstance(inline, PartnerMessageInline)]
        return instances

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PartnerMessage)
class PartnerMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "conversa", "autor_display", "texto_resumo", "comissao", "anexo_admin")
    list_filter = ("created_at",)
    search_fields = ("conversa__titulo", "texto", "autor_partner__nome", "autor_usuario__username", "comissao__partner__nome")
    readonly_fields = ("conversa", "autor_partner", "autor_usuario", "texto", "nome_original_anexo", "tipo_conteudo_anexo", "comissao", "created_at", "updated_at", "anexo_admin")
    fields = ("conversa", "autor_partner", "autor_usuario", "texto", "anexo_admin", "nome_original_anexo", "tipo_conteudo_anexo", "comissao", "created_at", "updated_at")

    @admin.display(description="Autor")
    def autor_display(self, obj):
        return obj.autor_partner.nome if obj.autor_partner_id else str(obj.autor_usuario or "Sistema")

    @admin.display(description="Mensagem")
    def texto_resumo(self, obj):
        text = (obj.texto or "[Anexo]").strip()
        return (text[:100] + "…") if len(text) > 100 else text

    @admin.display(description="Anexo (acesso autenticado)")
    def anexo_admin(self, obj):
        if not obj.anexo:
            return "—"
        try:
            url = reverse("parceiros:mensagem_anexo", kwargs={"pk": obj.pk})
        except NoReverseMatch:
            return obj.nome_original_anexo or "Anexo disponível (configurar rota de download)"
        return format_html('<a href="{}">Transferir {} (autenticado)</a>', url, obj.nome_original_anexo or "anexo")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Conversas/anexos são evidência operacional; a remoção não é permitida no admin.
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser or request.user.has_perm("parceiros.view_partnermessage"))


@admin.register(PartnerReactivationRequest)
class PartnerReactivationRequestAdmin(admin.ModelAdmin):
    list_display = ("partner", "status", "created_at", "respondido_por", "respondido_em")
    list_filter = ("status", "created_at")
    search_fields = ("partner__nome", "partner__email", "motivo")
    readonly_fields = tuple(f.name for f in PartnerReactivationRequest._meta.fields)
    fields = tuple(f.name for f in PartnerReactivationRequest._meta.fields)
    actions = ("aprovar_reativacao", "rejeitar_reativacao")

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    @admin.action(description="Aprovar e reactivar (só superuser)")
    def aprovar_reativacao(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied("Só o superuser pode reactivar parceiros.")
        count = 0
        for pedido in queryset.select_related("partner").filter(status="pendente"):
            try:
                reativar_parceiro_superuser(pedido.partner_id, request.user, pedido.motivo)
                pedido.status = "aprovado"
                pedido.resposta = "Conta reactivada pela administração SOTARQ."
                pedido.respondido_por = request.user
                pedido.respondido_em = timezone.now()
                pedido.save(update_fields=("status", "resposta", "respondido_por", "respondido_em", "updated_at"))
                count += 1
            except Exception as exc:
                self.message_user(request, f"Pedido #{pedido.pk}: {exc}", level=messages.ERROR)
        self.message_user(request, f"{count} parceiro(s) reactivado(s).")

    @admin.action(description="Rejeitar pedidos seleccionados")
    def rejeitar_reativacao(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied("Só o superuser pode decidir pedidos de reactivação.")
        from apps.parceiros.models import PartnerAudit, PartnerNotification
        count = 0
        for pedido in queryset.select_related("partner").filter(status="pendente"):
            pedido.status = "rejeitado"
            pedido.respondido_por = request.user
            pedido.respondido_em = timezone.now()
            pedido.resposta = "Pedido rejeitado pela administração SOTARQ."
            pedido.save(update_fields=("status", "respondido_por", "respondido_em", "resposta", "updated_at"))
            PartnerAudit.objects.create(
                partner=pedido.partner, acao="PARTNER_REACTIVATION_REJECTED",
                objeto_tipo="PartnerReactivationRequest", objeto_id=str(pedido.pk),
                executado_por=request.user, origem="admin",
                valor_novo={"status": "rejeitado", "motivo": pedido.motivo[:300]},
            )
            PartnerNotification.objects.create(
                partner=pedido.partner, tipo="rejeicao", titulo="Pedido de reactivação rejeitado",
                mensagem=pedido.resposta,
            )
            count += 1
        self.message_user(request, f"{count} pedido(s) rejeitado(s).")

# apps/core/admin.py
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django_tenants.utils import schema_context
from django.forms import modelform_factory

from .provisionamento import vincular_usuario_ao_cargo, campos_permissao
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.db import connection
from .models import Usuario, AuditoriaAcesso, IPConhecido, VerificacaoSeguranca

# Importar é seguro, o erro só surge ao consultar fora do schema_context:
from apps.funcionarios.models import Cargo, Funcionario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """
    RIGOR SOTARQ: Painel de Gestão de Utilizadores Multi-tenant.
    Permite vincular o utilizador à Empresa (Tenant) específica.
    """
    # Exibição na lista principal
    list_display = ('username', 'email', 'empresa', 'e_administrador_empresa', 'is_staff', 'link_cargo')
    list_filter = ('empresa', 'is_staff', 'is_superuser', 'e_administrador_empresa')

    # ---------- botão na lista ----------
    @admin.display(description="Cargo")
    def link_cargo(self, obj):
        if not obj.empresa_id or obj.empresa.schema_name == "public":
            return "-"
        url = reverse("admin:core_usuario_atribuir_cargo", args=[obj.pk])
        return format_html('<a href="{}">Atribuir cargo</a>', url)

    # ---------- provisionamento automático ----------
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        mudou_vinculo = (not change) or any(
            c in form.changed_data for c in ("empresa", "e_administrador_empresa")
        )
        if obj.empresa_id and obj.e_administrador_empresa and mudou_vinculo:
            try:
                vincular_usuario_ao_cargo(obj)
                messages.success(
                    request,
                    f"Cargo 'Administrador' garantido no tenant '{obj.empresa.nome}'."
                )
            except Exception as e:
                messages.error(request, f"Usuário criado, mas falhou o vínculo ao cargo: {e}")


    def cargo_permissoes_view(self, request, object_id, cargo_id):
        if not self.has_change_permission(request):
            raise PermissionDenied

        usuario = get_object_or_404(Usuario.objects.select_related("empresa"), pk=object_id)
        if not usuario.empresa_id or usuario.empresa.schema_name == "public":
            messages.error(request, "Este usuário não está ligado a nenhuma empresa.")
            return redirect("admin:core_usuario_changelist")

        nomes_pode = campos_permissao()
        Form = modelform_factory(Cargo, fields=nomes_pode + ["limite_desconto_percentual"])

        salvo = False
        # Tudo o que toca na BD do tenant fica DENTRO do contexto
        with schema_context(usuario.empresa.schema_name):
            cargo = get_object_or_404(Cargo, pk=cargo_id)

            if request.method == "POST":
                form = Form(request.POST, instance=cargo)
                if form.is_valid():
                    form.save()
                    salvo = True
            else:
                form = Form(instance=cargo)

            cargo_nome, cargo_codigo = cargo.nome, cargo.codigo

        # messages e render ficam FORA, de volta ao schema public
        if salvo:
            messages.success(request, f"Permissões do cargo '{cargo_nome}' atualizadas.")
            return redirect("admin:core_usuario_atribuir_cargo", object_id=usuario.pk)

        ctx = {**self.admin_site.each_context(request),
               "title": f"Permissões — {cargo_nome} ({usuario.empresa.nome})",
               "usuario": usuario, "form": form,
               "campos_pode": [form[n] for n in nomes_pode],
               "cargo_nome": cargo_nome, "cargo_codigo": cargo_codigo,
               "opts": self.model._meta}
        return render(request, "admin/core/cargo_permissoes.html", ctx)
    
    # ---------- view para escolher o cargo ----------
    def get_urls(self):
        custom = [
            path("<path:object_id>/cargo/<int:cargo_id>/permissoes/",
                 self.admin_site.admin_view(self.cargo_permissoes_view),
                 name="core_usuario_cargo_permissoes"),
            path("<path:object_id>/cargo/",
                 self.admin_site.admin_view(self.atribuir_cargo_view),
                 name="core_usuario_atribuir_cargo"),
        ]
        return custom + super().get_urls()

    def atribuir_cargo_view(self, request, object_id):
        if not self.has_change_permission(request):
            raise PermissionDenied

        usuario = get_object_or_404(Usuario.objects.select_related("empresa"), pk=object_id)
        if not usuario.empresa_id or usuario.empresa.schema_name == "public":
            messages.error(request, "Este usuário não está ligado a nenhuma empresa.")
            return redirect("admin:core_usuario_changelist")

        if request.method == "POST":
            valor = request.POST.get("cargo")
            if not valor:
                messages.error(request, "Selecione um cargo.")
            else:
                try:
                    vincular_usuario_ao_cargo(usuario, None if valor == "admin" else valor)
                    messages.success(request, "Cargo atribuído com sucesso.")
                    return redirect("admin:core_usuario_changelist")
                except Exception as e:
                    messages.error(request, f"Erro: {e}")

        # list()/values() avaliados DENTRO do contexto do tenant
        with schema_context(usuario.empresa.schema_name):
            cargos = list(
                Cargo.objects.filter(ativo=True)
                .order_by("nivel_hierarquico", "nome")
                .values("id", "nome", "categoria")
            )
            atual = Funcionario.objects.filter(usuario_id=usuario.pk)\
                .values_list("cargo_id", flat=True).first()

        ctx = {**self.admin_site.each_context(request),
               "title": f"Cargo de {usuario.username} — {usuario.empresa.nome}",
               "usuario": usuario, "cargos": cargos, "atual": atual,
               "opts": self.model._meta}
        return render(request, "admin/core/atribuir_cargo.html", ctx)
    
    # Se a lista de empresas for grande, facilita a busca com autocomplete
    autocomplete_fields = ('empresa',) 
    
    # Organização dos campos no formulário de edição
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Informações Pessoais'), {'fields': ('first_name', 'last_name', 'email', 'telefone', 'foto')}),
        (_('Vínculo Empresarial (Multi-tenant)'), {
            'fields': ('empresa', 'e_administrador_empresa'),
            'description': 'Selecione o Tenant (Empresa) e defina a função deste utilizador.'
        }),
        (_('Permissões de Sistema'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Datas Importantes'), {'fields': ('last_login', 'date_joined')}),
    )

    # Campos para criação de novo usuário
    add_fieldsets = UserAdmin.add_fieldsets + (
        (_('Vínculo Empresarial'), {
            'fields': ('empresa', 'e_administrador_empresa'),
        }),
    )

    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)

    
    def eliminar_usuarios_public(self, request, queryset):
        """
        🛡️ RIGOR SOTARQ: Elimina utilizadores no schema public ignorando 
        tabelas de inquilinos que causam erro de 'relation does not exist'.
        """
        try:
            total = queryset.count()
            # Deletamos diretamente para ignorar o Collector do Django e as tabelas de tenant
            queryset.delete() 
            self.message_user(request, f"✔ SUCESSO SOTARQ: {total} utilizadores eliminados permanentemente.")
        except Exception as e:
            self.message_user(request, f"❌ Erro ao eliminar: {str(e)}", level='ERROR')
    
    # Define os metadados da ação
    #eliminar_usuarios_public.short_description = "ELIMINAR utilizadores selecionados (Rigoroso)"

    def get_actions(self, request):
        # Primeiro, pegamos as ações base (o Django já vai incluir eliminar_usuarios_public automaticamente se estiver na classe)
        actions = super().get_actions(request)
        
        if connection.schema_name == 'public':
            # Removemos a ação padrão do Django que causa o JOIN fatal com analytics
            if 'delete_selected' in actions:
                del actions['delete_selected']
        else:
            # Se não estiver no public (dentro de um tenant), talvez você queira remover a nossa ação "bruta"
            if 'eliminar_usuarios_public' in actions:
                del actions['eliminar_usuarios_public']
                
        return actions
    
    #def delete_model(self, request, obj):
    #    """
    #    🛡️ RIGOR SOTARQ: Executa a deleção direta no schema public.
    #    """
    #    if connection.schema_name == 'public':
    #        obj.delete()
    #    else:
    #        super().delete_model(request, obj)
    
    def delete_model(self, request, obj):
        """
        🛡️ RIGOR SOTARQ: Interceptação de Segurança com Redirecionamento.
        """
        from apps.core.models import IPConhecido
        from django.shortcuts import redirect
        from django.urls import reverse
        
        # 1. Pega o IP real (considerando proxies como o Render)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_atual = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        
        # 2. Verifica se o vínculo IP+User já foi autenticado via 2FA
        foi_validado = IPConhecido.objects.filter(usuario=request.user, ip_address=ip_atual).exists()

        if connection.schema_name == 'public':
            if foi_validado:
                # 🚀 EXECUÇÃO BRUTA (O comando que o senhor guardou)
                obj.delete() 
                self.message_user(request, f"✔ {obj._meta.verbose_name} eliminado com Rigor Sênior.")
            else:
                # 🛡️ BLOQUEIO ATIVO: Se não validou, manda para a view de Token
                self.message_user(request, "⚠️ Validação 2FA necessária para eliminar registos globais.", level='WARNING')
                
                # Guardamos a intenção na sessão para voltar depois (opcional)
                request.session['pending_action'] = f"delete_{obj.pk}"
                
                # Redireciona para a view que o senhor já criou anteriormente
                return redirect(reverse('core:verify_ip')) 
        else:
            # Comportamento padrão dentro dos inquilinos (Tenants)
            super().delete_model(request, obj)
    

    def get_deleted_objects(self, objs, request):
        """
        🛡️ RIGOR SOTARQ: Sobrescreve a coleta de objetos relacionados.
        No schema public, forçamos o Django a ignorar relações com apps de Tenant.
        """
        from django.db import connection
        from django.contrib.admin.utils import get_deleted_objects
        
        if connection.schema_name == 'public':
            # 🚀 Truque Sênior: Se estivermos no public, retornamos uma lista de 
            # dependências vazia para evitar que o Collector tente ler tabelas inexistentes.
            return [], {}, set(), []
        
        return super().get_deleted_objects(objs, request)

        

@admin.register(AuditoriaAcesso)
class AuditoriaAcessoAdmin(admin.ModelAdmin):
    """Monitorização de Segurança em tempo real."""
    list_display = ('timestamp', 'usuario', 'acao', 'ip_address', 'user_agent')
    list_filter = ('acao', 'timestamp')
    search_fields = ('usuario__username', 'ip_address')
    readonly_fields = ('usuario', 'acao', 'ip_address', 'user_agent', 'timestamp')

    def has_add_permission(self, request): return False # Proibido criar logs manuais


@admin.register(IPConhecido)
class IPConhecidoAdmin(admin.ModelAdmin):
    """Gestão de dispositivos autorizados."""
    list_display = ('usuario', 'ip_address', 'primeiro_acesso', 'ultimo_acesso')
    search_fields = ('usuario__username', 'ip_address')
    readonly_fields = ('primeiro_acesso', 'ultimo_acesso')


@admin.register(VerificacaoSeguranca)
class VerificacaoSegurancaAdmin(admin.ModelAdmin):
    """Controle de Tokens de 2FA."""
    list_display = ('usuario', 'ip_address', 'token', 'criado_em', 'expira_em', 'foi_verificado')
    list_filter = ('foi_verificado', 'criado_em')
    search_fields = ('usuario__username', 'token')
    readonly_fields = ('criado_em', 'expira_em')
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.db import connection
from .models import Usuario, AuditoriaAcesso, IPConhecido, VerificacaoSeguranca



@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """
    RIGOR SOTARQ: Painel de Gestão de Utilizadores Multi-tenant.
    Permite vincular o utilizador à Empresa (Tenant) e à Loja específica.
    """
    # Exibição na lista principal
    list_display = ('username', 'email', 'empresa', 'loja', 'e_administrador_empresa', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'e_administrador_empresa', 'empresa')
    
    # Organização dos campos no formulário de edição
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Informações Pessoais'), {'fields': ('first_name', 'last_name', 'email', 'telefone', 'foto')}),
        (_('Vínculo Empresarial (Multi-tenant)'), {
            'fields': ('empresa', 'loja', 'e_administrador_empresa'),
            'description': 'Selecione o Tenant e a Unidade de Negócio deste utilizador.'
        }),
        (_('Permissões de Sistema'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Datas Importantes'), {'fields': ('last_login', 'date_joined')}),
    )

    # Campos para criação de novo usuário
    add_fieldsets = UserAdmin.add_fieldsets + (
        (_('Vínculo Empresarial'), {
            'fields': ('empresa', 'loja', 'e_administrador_empresa'),
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
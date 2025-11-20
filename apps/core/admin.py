# Em apps/core/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.services import AssinaturaDigitalService
from .models import Empresa, Loja, Usuario, Categoria
from apps.licenca.models import Licenca 

# =============================================================================
# DEFINIÇÃO DOS INLINES (AQUI, NO MESMO FICHEIRO)
# =============================================================================

class LojaInline(admin.TabularInline):
    model = Loja
    extra = 0


class LicencaInline(admin.TabularInline):
    model = Licenca
    extra = 0


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    """
    Interface de administração para o modelo Categoria.
    """
    
    # Campos a serem exibidos na lista
    list_display = (
        'nome', 
        'empresa',
        'codigo', 
        'ativa'
    )
    
    # Campos que podem ser editados diretamente na lista
    list_editable = (
        'ativa',
    )
    
    # Opções de filtro na barra lateral
    list_filter = (
        'ativa', 
        'empresa' # Essencial para sistemas multi-empresa
    )
    
    # Campos pelos quais se pode pesquisar
    search_fields = (
        'nome', 
        'codigo', 
        'empresa__nome' # Permite pesquisar pelo nome da empresa
    )
    
    # Otimiza a seleção de 'empresa' se houver muitas
    autocomplete_fields = (
        'empresa',
    )

    # Organização do formulário de edição/criação
    fieldsets = (
        (None, {
            'fields': ('empresa', ('nome', 'codigo'), 'ativa')
        }),
        ('Detalhes Adicionais', {
            'classes': ('collapse',),
            'fields': ('descricao',)
        }),
    )


# =============================================================================
# ADMINS DOS MODELOS
# =============================================================================

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'nif', 'cidade', 'status_licenca', 'ativa', 'total_usuarios']
    actions = ['action_gerar_chaves']

    list_filter = ['ativa', 'provincia', 'licenca__status', 'licenca__plano']
    search_fields = ['nome', 'nif', 'cidade']
    
    # Use os inlines definidos localmente
    inlines = [LicencaInline, LojaInline]
    
    fieldsets = (
        ('Dados Básicos', {'fields': ('nome', 'nome_fantasia', 'codigo_validacao', 'nif')}),
        ('Endereço', {'fields': (('endereco', 'numero'), ('bairro', 'cidade'), ('provincia', 'postal'))}),
        ('Contato', {'fields': ('telefone', 'email')}),
        ('Status', {'fields': ('ativa',)}),
    )
    actions = ['ativar_empresas', 'desativar_empresas']

    def status_licenca(self, obj):
        """Exibe status da licença com cores e informações detalhadas"""
        try:
            licenca = obj.licenca
            
            # Verificar se está vencida
            if licenca.esta_vencida:
                return format_html(
                    '<div style="text-align: center;">'
                    '<span style="background-color: #dc2626; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; display: block; margin-bottom: 2px;">❌ VENCIDA</span>'
                    '<small style="color: #dc2626; font-weight: bold;">Há {} dias</small>'
                    '</div>',
                    abs(licenca.dias_para_vencer)
                )
            
            # Status baseado no campo status da licença
            if licenca.status == 'ativa':
                dias = licenca.dias_para_vencer
                
                if dias <= 7:  # Prestes a vencer
                    cor_fundo = '#f59e0b'
                    icone = '⚠️'
                    texto_status = 'EXPIRA EM BREVE'
                    cor_texto = '#f59e0b'
                elif dias <= 30:  # Vencimento próximo
                    cor_fundo = '#3b82f6'
                    icone = '🔵'
                    texto_status = 'ATIVA'
                    cor_texto = '#3b82f6'
                else:  # Tudo OK
                    cor_fundo = '#10b981'
                    icone = '✅'
                    texto_status = 'ATIVA'
                    cor_texto = '#10b981'
                
                return format_html(
                    '<div style="text-align: center;">'
                    '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; display: block; margin-bottom: 2px;">{} {}</span>'
                    '<small style="color: {};">Vence em {} dias</small><br>'
                    '<small style="color: #6b7280;">Plano: {}</small>'
                    '</div>',
                    cor_fundo,
                    icone,
                    texto_status,
                    cor_texto,
                    dias,
                    licenca.plano.nome
                )
            
            elif licenca.status == 'suspensa':
                return format_html(
                    '<div style="text-align: center;">'
                    '<span style="background-color: #f59e0b; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; display: block; margin-bottom: 2px;">⏸️ SUSPENSA</span>'
                    '<small style="color: #f59e0b;">Verificar pagamento</small>'
                    '</div>'
                )
            
            elif licenca.status == 'cancelada':
                return format_html(
                    '<div style="text-align: center;">'
                    '<span style="background-color: #6b7280; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; display: block; margin-bottom: 2px;">❌ CANCELADA</span>'
                    '<small style="color: #6b7280;">Licença cancelada</small>'
                    '</div>'
                )
            
            else:  # Status desconhecido
                return format_html(
                    '<div style="text-align: center;">'
                    '<span style="background-color: #6b7280; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>'
                    '</div>',
                    licenca.get_status_display()
                )
                
        except Licenca.DoesNotExist:
            return format_html(
                '<div style="text-align: center;">'
                '<span style="background-color: #ef4444; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; display: block; margin-bottom: 2px;">❌ SEM LICENÇA</span>'
                '<small style="color: #ef4444;">Licença não encontrada</small>'
                '</div>'
            )
        except Exception as e:
            return format_html(
                '<span style="color: #ef4444;">Erro: {}</span>',
                str(e)
            )
    
    status_licenca.short_description = 'Status da Licença'

    def total_usuarios(self, obj):
        """Exibe total de usuários atual vs limite do plano"""
        try:
            licenca = obj.licenca
            
            # Contar usuários ativos da empresa
            usuarios_atual = obj.usuarios.filter(is_active=True).count()
            
            # Obter limite do plano
            limite_usuarios = licenca.plano.limite_usuarios
            
            # Calcular percentual de uso
            percentual_uso = (usuarios_atual / limite_usuarios) * 100 if limite_usuarios > 0 else 0
            percentual_str = f"{percentual_uso:.1f}"  # ✅ já formatado como string
            
            # Definir cor e status
            if percentual_uso >= 100:
                cor = '#dc2626'
                icone = '❌'
                status_texto = 'LIMITE EXCEDIDO'
            elif percentual_uso >= 90:
                cor = '#f59e0b'
                icone = '⚠️'
                status_texto = 'PRÓXIMO DO LIMITE'
            elif percentual_uso >= 70:
                cor = '#3b82f6'
                icone = '🔵'
                status_texto = 'USO ALTO'
            else:
                cor = '#10b981'
                icone = '✅'
                status_texto = 'OK'
            
            return format_html(
                '<div style="text-align: center; font-family: monospace;">'
                '<div style="font-size: 14px; font-weight: bold; color: {};">'
                '{} <span style="font-size: 18px;">{}</span> / {}'
                '</div>'
                '<div style="margin-top: 2px;">'
                '<span style="background-color: {}; color: white; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: bold;">{} {}</span>'
                '</div>'
                '<div style="margin-top: 2px;">'
                '<small style="color: #6b7280;">({}% usado)</small>'
                '</div>'
                '</div>',
                cor,
                icone,
                usuarios_atual,
                limite_usuarios,
                cor,
                icone,
                status_texto,
                percentual_str  # ✅ valor já seguro
            )
                
        except Licenca.DoesNotExist:
            usuarios_atual = obj.usuarios.filter(is_active=True).count()
            return format_html(
                '<div style="text-align: center; font-family: monospace;">'
                '<div style="font-size: 14px; font-weight: bold; color: #ef4444;">'
                '❌ {} / ?'
                '</div>'
                '<div style="margin-top: 2px;">'
                '<span style="background-color: #ef4444; color: white; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: bold;">SEM LICENÇA</span>'
                '</div>'
                '</div>',
                usuarios_atual
            )
        except Exception as e:
            return format_html(
                '<span style="color: #ef4444; font-family: monospace;">Erro: {}</span>',
                str(e)
            )


    total_usuarios.short_description = 'Usuários (Atual/Limite)'

    def ativar_empresas(self, request, queryset):
        count = queryset.update(ativa=True)
        self.message_user(request, f'{count} empresas ativadas.')
    ativar_empresas.short_description = "Ativar empresas selecionadas"

    def desativar_empresas(self, request, queryset):
        count = queryset.update(ativa=False)
        self.message_user(request, f'{count} empresas desativadas.')
    desativar_empresas.short_description = "Desativar empresas selecionadas"

    def acoes_assinatura(self, obj):
        try:
            assinatura = AssinaturaDigital.objects.get(empresa=obj)
            url = reverse('fiscal:baixar_chave_publica', args=[assinatura.empresa.id])
            return format_html('<a class="button" href="{}">Baixar Chave Pública</a>', url)
        except AssinaturaDigital.DoesNotExist:
            return format_html('<span style="color: #999">—</span>')


    def action_gerar_chaves(self, request, queryset):
        # Só superusers podem regenerar — verifica request.user.is_superuser
        if not request.user.is_superuser:
            self.message_user(request, "Somente superusers podem regenerar chaves.", level='error')
            return
        for empresa in queryset:
            AssinaturaDigitalService.gerar_chaves_rsa(empresa)
        self.message_user(request, "Chaves geradas/regeneradas com sucesso.")
    action_gerar_chaves.short_description = "Gerar/Regenerar chaves RSA"



@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """
    Define a interface de administração para o modelo de Utilizador personalizado.
    """
    # 1. CAMPOS A EXIBIR NA LISTA DE UTILIZADORES
    # Adicionamos 'empresa' e 'e_administrador_empresa' à lista.
    list_display = (
        'username', 
        'email', 
        'first_name', 
        'last_name', 
        'empresa', 
        'e_administrador_empresa', 
        'is_staff'
    )

    # 2. FILTROS DA BARRA LATERAL
    # Adicionamos 'empresa' como uma opção de filtro.
    list_filter = ('is_staff', 'is_superuser', 'groups', 'empresa')

    search_fields = ('username', 'first_name', 'last_name', 'email', 'empresa__nome')
    
    fieldsets = (

        *UserAdmin.fieldsets,

        ('Perfil Profissional e Vínculos', {
            'fields': (
                'empresa', 
                'loja', 
                'telefone', 
                'e_administrador_empresa'
            ),
        }),
    )


@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'empresa', 'codigo', 'cidade', 'eh_matriz', 'ativa']
    list_filter = ['ativa', 'eh_matriz', 'empresa']
    search_fields = ['nome', 'codigo', 'cidade']  # ✅ OBRIGATÓRIO para autocomplete

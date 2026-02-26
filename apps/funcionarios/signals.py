# apps/funcionarios/signals.py
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save, pre_delete, m2m_changed
from django.contrib.auth.models import Group, Permission # Modelos globais, OK importar
from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.db import connection

# RIGOR SOTARQ: Removi os imports de Funcionario, Cargo, Departamento do topo.
# Eles serão importados dentro das funções apenas se não for schema 'public'.

@receiver(post_save, sender='core.Usuario') # Usamos string para evitar import circular
def sincronizar_status_usuario_e_funcionario(sender, instance, **kwargs):
    if connection.schema_name == 'public':
        return
    
    # Importação local: Só acontece se estivermos num Tenant
    from .models import Funcionario
    
    try:
        funcionario = Funcionario.objects.get(usuario=instance)
        # Sincroniza is_active com o status do funcionário
        if not funcionario.ativo or funcionario.data_demissao:
            if instance.is_active:
                sender.objects.filter(id=instance.id).update(is_active=False)
    except:
        pass

@receiver(post_save, sender='empresas.Empresa')
def criar_padroes_empresa(sender, instance, created, **kwargs):
    # RIGOR SOTARQ: Ignorar o schema public e focar apenas no que foi solicitado
    if instance.schema_name == 'public' or not created:
        return

    from django.db import transaction
    from django_tenants.utils import schema_context

    def executar_inicializacao_tenant():
        from .models import Departamento
        
        with schema_context(instance.schema_name):
            try:
                # Mantemos apenas departamentos ou deixamos vazio conforme sua ordem
                # Se não quiser departamentos também, basta apagar este bloco
                depts_globais = [] 
                with schema_context('public'):
                    depts_globais = list(Departamento.objects.filter(loja__isnull=True))

                for dept in depts_globais:
                    Departamento.objects.create(
                        nome=dept.nome,
                        codigo=f"{dept.codigo}_{instance.id}",
                        loja=None,
                        ativo=True
                    )
                print(f"[SUCESSO SOTARQ] Tenant {instance.nome} inicializado sem cargos globais.")
            except Exception as e:
                print(f"[AVISO] Erro na inicialização básica: {e}")

    transaction.on_commit(executar_inicializacao_tenant)      



@receiver(pre_save, sender='funcionarios.Funcionario')
def gerar_matricula_e_validar_funcionario(sender, instance, **kwargs):
    if connection.schema_name == 'public':
        return
    
    if not instance.matricula:
        instance.matricula = instance.gerar_matricula()
    
    if instance.data_demissao and instance.data_demissao <= instance.data_admissao:
        raise ValidationError("A data de demissão deve ser posterior à admissão.")

@receiver(post_save, sender='funcionarios.Funcionario')
def sincronizar_usuario_cargo(sender, instance, created, **kwargs):
    if connection.schema_name == 'public':
        return
    
    from .models import Cargo # Import local
    usuario = instance.usuario
    cargo = instance.cargo

    if not usuario or not cargo:
        return

    if hasattr(usuario, "empresa") and usuario.empresa != instance.empresa:
        usuario.empresa = instance.empresa
        usuario.save(update_fields=["empresa"])

    group, _ = Group.objects.get_or_create(name=cargo.nome)
    usuario.groups.clear()
    usuario.groups.add(group)

@receiver(m2m_changed, sender=Group.user_set.through)
def sincronizar_cargo_a_partir_do_grupo(sender, instance, action, reverse, **kwargs):
    if connection.schema_name == 'public' or action not in ["post_add", "post_remove", "post_clear"]:
        return

    from .models import Funcionario, Cargo # Import local
    
    if not reverse:
        usuario = instance
        try:
            funcionario = Funcionario.objects.get(usuario=usuario)
            grupos = usuario.groups.all()
            if grupos.exists():
                cargo = Cargo.objects.filter(nome=grupos.first().name).first()
                if cargo and funcionario.cargo_id != cargo.id:
                    Funcionario.objects.filter(id=funcionario.id).update(cargo=cargo)
        except:
            pass




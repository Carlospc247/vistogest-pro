# apps/empresas/views_public.py
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from .forms import CadastroEmpresaForm
from .models import Empresa, Domain

Usuario = get_user_model()
logger = logging.getLogger(__name__)


class CadastroEmpresaView(FormView):
    """
    Self-signup público. Corre inteiramente no schema 'public'.

    RIGOR SOTARQ — separação SHARED_APPS / TENANT_APPS:
    Esta view só escreve em Empresa e Domain (apps.empresas) e Usuario
    (apps.core) — os três são SHARED_APPS, logo vivem no schema 'public'.
    Nunca criamos aqui um Funcionario, Cargo ou qualquer outro modelo
    TENANT_APP: essas tabelas só passam a existir DEPOIS do passo 1,
    quando o django_tenants migra o schema novo sozinho. Popular esses
    dados (cargo do admin, departamento, etc.) fica para um assistente de
    onboarding a correr já dentro do tenant, no primeiro login — não aqui.
    """
    template_name = 'empresas/cadastro.html'
    form_class = CadastroEmpresaForm

    def form_valid(self, form):
        dados = form.cleaned_data
        schema_name = form.gerar_schema_name()
        empresa = None
        domain = None

        try:
            # 1. Empresa (SHARED_APP). O TenantMixin.save() do django_tenants
            #    dispara sozinho (AUTO_CREATE_SCHEMA=True) a criação do schema
            #    físico no PostgreSQL + migração de TODAS as TENANT_APPS lá
            #    dentro. Propositadamente NÃO envolvemos isto num
            #    transaction.atomic() externo — a criação/migração do schema
            #    gere as suas próprias transações internas, e aninhar podia
            #    causar deadlock/rollback parcial do schema físico.
            empresa = Empresa.objects.create(
                schema_name=schema_name,
                nome=dados['nome'],
                nome_fantasia=dados['nome_fantasia'],
                nif=dados['nif'],
                regime=dados['regime'],           # tipo de actividade (Comércio/Serviços/Misto)
                regime_fiscal=dados.get('regime_fiscal', 'GERAL'),  # regime fiscal AGT
                endereco=dados['endereco'],
                numero=dados['numero'],
                bairro=dados['bairro'],
                cidade=dados['cidade'],
                provincia=dados['provincia'],
                postal=dados['postal'],
                telefone=dados['telefone_empresa'],
                email=dados['email_empresa'],
                ativa=True,
            )

            # 2. Domain (SHARED_APP) — dev usa *.localhost, produção usa o
            #    domínio raiz atual (ex: vistogest.pro).
            host_atual = self.request.get_host().split(':')[0]
            if host_atual in ('localhost', '127.0.0.1'):
                dominio_completo = f"{schema_name}.localhost"
            else:
                partes = host_atual.split('.')
                raiz = '.'.join(partes[-2:]) if len(partes) >= 2 else host_atual
                dominio_completo = f"{schema_name}.{raiz}"

            domain = Domain.objects.create(domain=dominio_completo, tenant=empresa, is_primary=True)

            # 3. Usuario (SHARED_APP, apps.core). Mesmo sendo o "admin da
            #    empresa X", este registo vive SEMPRE no schema public —
            #    a ligação ao tenant é o FK Usuario.empresa, não o schema.
            #    is_staff fica False de propósito: não deve ter acesso ao
            #    /admin/ global, só ao painel do seu próprio tenant.
            with transaction.atomic():
                admin_user = Usuario.objects.create_user(
                    username=dados['admin_username'],
                    email=dados['admin_email'],
                    password=dados['admin_password'],
                    first_name=dados['admin_first_name'],
                    last_name=dados['admin_last_name'],
                    e_administrador_empresa=True,
                    is_active=True,
                )

        except Exception as e:
            # Rollback manual em ORDEM INVERSA de criação: Domain primeiro
            # (tem FK para Empresa), só depois o schema físico + a linha
            # de Empresa. Qualquer falha aqui é logada, nunca escondida —
            # se o rollback falhar a meio, fica lixo na base e precisamos
            # de saber para limpar manualmente.
            try:
                if domain is not None:
                    Domain.objects.filter(pk=domain.pk).delete()
                if empresa is not None:
                    if empresa.schema_name != 'public':
                        empresa._drop_schema(force_drop=True)
                    Empresa.objects.filter(pk=empresa.pk)._raw_delete(Empresa.objects.db)
            except Exception as rollback_error:
                logger.error(
                    "Falha no rollback do registo de empresa (schema=%s): %s",
                    schema_name, rollback_error
                )
            form.add_error(None, f"Não foi possível concluir o registo: {e}")
            return self.form_invalid(form)

        # Os IDs só ficam na sessão até serem mostrados uma vez na página
        # de sucesso — não persistem para lá disso.
        protocolo = 'https' if self.request.is_secure() else 'http'
        porta_atual = self.request.get_host().split(':')[1] if ':' in self.request.get_host() else None

        # só inclui porta se o host de registo também tinha porta explícita (ambiente dev)
        if porta_atual and host_atual in ('localhost', '127.0.0.1'):
            url_acesso = f"{protocolo}://{dominio_completo}:{porta_atual}/"
        else:
            url_acesso = f"{protocolo}://{dominio_completo}/"

        self.request.session['cadastro_sucesso'] = {
            'empresa_id': empresa.id,
            'empresa_nome': empresa.nome,
            'schema_name': empresa.schema_name,
            'usuario_id': admin_user.id,
            'usuario_username': admin_user.username,
            'dominio': dominio_completo,
            'url_acesso': url_acesso,
        }
        return redirect(reverse('empresas:cadastro_sucesso'))


class CadastroSucessoView(TemplateView):
    """Mostra, uma única vez, o ID da Empresa e o ID do Usuario Admin
    criados, para o utilizador guardar. Dados vêm da sessão e são
    removidos (pop) assim que exibidos."""
    template_name = 'empresas/cadastro_sucesso.html'

    def get(self, request, *args, **kwargs):
        dados = request.session.pop('cadastro_sucesso', None)
        if not dados:
            return redirect(reverse('empresas:cadastro'))
        self.dados = dados
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dados'] = self.dados
        return context
# apps/fiscal/admin.py
"""
apps/fiscal/admin.py — chaves fiscais do contribuinte (AGT), a partir do schema PUBLIC.

AssinaturaDigital só existe nos schemas dos tenants, por isso não tem ModelAdmin
próprio: um proxy de Empresa lista as empresas e abre o formulário de chaves,
que grava dentro de schema_context(<tenant>).

Segurança
* Só superuser E só no schema public (um superuser de tenant não pode tocar
  noutro tenant alterando o <schema_name> da URL).
* O NIF vem da Empresa; nunca é digitado.
* A chave privada é write-only e fora dos relatórios de erro.
* Grava, relê e verifica na mesma transacção: se algo falhar, rollback.
"""
import logging

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import ProgrammingError, connection, transaction
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.debug import sensitive_post_parameters
from django_tenants.utils import get_public_schema_name, schema_context

from apps.empresas.models import Empresa
from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.utility import chaves

logger = logging.getLogger(__name__)

# O índice do django-tenants esconde a app "fiscal" no public; este template deixa-a passar.
admin.site.index_template = "fiscal/admin/index.html"


def _pode_gerir(request) -> bool:
    no_public = connection.schema_name == get_public_schema_name()
    return no_public and request.user.is_active and request.user.is_superuser


class ChavesFiscaisForm(forms.Form):
    chave_privada = forms.CharField(
        label="Chave privada (PEM)",
        widget=forms.Textarea(attrs={"rows": 10, "cols": 80, "autocomplete": "off", "spellcheck": "false"}),
        help_text="Emitida pela AGT para este contribuinte. Nunca é mostrada de volta.",
    )
    chave_publica = forms.CharField(
        label="Chave pública (PEM)", required=False,
        widget=forms.Textarea(attrs={"rows": 7, "cols": 80, "spellcheck": "false"}),
        help_text="Se em branco, é derivada da privada. Se preenchida, tem de corresponder.",
    )

    def clean_chave_privada(self):
        pem = self.cleaned_data["chave_privada"]
        try:
            chaves.carregar_privada(pem)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return pem

    def clean_chave_publica(self):
        pem = self.cleaned_data["chave_publica"]
        if pem:
            try:
                chaves.carregar_publica(pem)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        return pem

    def clean(self):
        dados = super().clean()
        privada, publica = dados.get("chave_privada"), dados.get("chave_publica")
        if privada and publica:
            try:
                chaves.validar_par(chaves.carregar_privada(privada), chaves.carregar_publica(publica))
            except ValueError as exc:
                self.add_error("chave_publica", str(exc))
        return dados


def _estado(empresa) -> dict:
    """Estado do tenant, sem segredos."""
    estado = {"configurada": False, "data": None, "por": "", "fingerprint": "",
              "problemas": [], "erro": ""}
    try:
        with schema_context(empresa.schema_name), transaction.atomic():
            ass = AssinaturaDigital.objects.filter(pk=1).first()
            if ass and ass.esta_configurada:
                estado.update(
                    configurada=True,
                    data=ass.data_configuracao_chave,
                    por=ass.configurada_por_nome,
                    fingerprint=ass.chave_publica_fingerprint,
                    problemas=ass.verificar_integridade(),
                )
    except ProgrammingError as exc:  # tabelas em falta: migrate_schemas por correr
        logger.warning("Estado fiscal indisponível para %s: %s", empresa.schema_name, exc)
        estado["erro"] = "Schema sem tabelas fiscais (migrate_schemas em falta?)"
    return estado


def _gravar(empresa, dados, usuario):
    with schema_context(empresa.schema_name), transaction.atomic():
        AssinaturaDigital.get_solo()
        ass = AssinaturaDigital.objects.select_for_update().get(pk=1)
        ass.definir_chaves(
            dados["chave_privada"],
            dados["chave_publica"] or None,
            autor=usuario.get_username(),
        )
        ass.refresh_from_db()  # round-trip real
        problemas = ass.verificar_integridade()
        if problemas:
            raise ValidationError(problemas)  # rollback


class EmpresaChavesFiscais(Empresa):
    """Proxy sem tabela: serve só para a app Fiscal aparecer no índice do admin."""

    class Meta:
        proxy = True
        app_label = "fiscal"
        verbose_name = "Chaves fiscais da empresa"
        verbose_name_plural = "Chaves fiscais das empresas"


@admin.register(EmpresaChavesFiscais)
class EmpresaChavesFiscaisAdmin(admin.ModelAdmin):
    list_display = ("__str__", "schema_name", "estado_chaves", "configurar")
    search_fields = ("schema_name",)
    list_display_links = None
    actions = None

    # Só leitura: a Empresa edita-se em EmpresaAdmin (assim a fonte é uma só).
    def has_module_permission(self, request):
        return _pode_gerir(request)

    def has_view_permission(self, request, obj=None):
        return _pode_gerir(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(schema_name=get_public_schema_name())

    def get_urls(self):
        url = path("<str:schema_name>/chaves/", self.admin_site.admin_view(self.chaves_view),
                   name="fiscal_chaves_empresa")
        return [url] + super().get_urls()

    @admin.display(description="Estado")
    def estado_chaves(self, obj):
        estado = _estado(obj)
        if estado["erro"]:
            return format_html('<span style="color:#b91c1c">{}</span>', estado["erro"])
        if estado["problemas"]:
            return format_html('<span style="color:#b91c1c">⚠ {}</span>', "; ".join(estado["problemas"]))
        return "✔ configurada" if estado["configurada"] else "✖ não configurada"

    @admin.display(description="")
    def configurar(self, obj):
        return format_html('<a href="{}">Inserir / editar chaves</a>',
                           reverse("admin:fiscal_chaves_empresa", args=[obj.schema_name]))

    @method_decorator(sensitive_post_parameters("chave_privada", "chave_publica"))
    def chaves_view(self, request, schema_name):
        if not _pode_gerir(request):
            raise PermissionDenied
        empresas = Empresa.objects.exclude(schema_name=get_public_schema_name())
        empresa = get_object_or_404(empresas, schema_name=schema_name)

        form = ChavesFiscaisForm(request.POST or None)
        if form.is_valid():
            try:
                _gravar(empresa, form.cleaned_data, request.user)
            except ValidationError as exc:
                messages.error(request, "Chaves recusadas: " + " ".join(exc.messages))
            except Exception:
                logger.exception("Falha a gravar chaves fiscais (schema=%s)", schema_name)
                messages.error(request, "Não foi possível gravar. Verifique AES_KEY e as migrações do tenant.")
            else:
                logger.info("Chaves fiscais actualizadas schema=%s user_id=%s", schema_name, request.user.pk)
                messages.success(request, f"Chaves fiscais de {empresa} guardadas.")
                return redirect("admin:fiscal_chaves_empresa", schema_name=schema_name)

        contexto = {**self.admin_site.each_context(request), "title": f"Chaves fiscais — {empresa}",
                    "empresa": empresa, "estado": _estado(empresa), "form": form, "opts": self.model._meta}
        return TemplateResponse(request, "admin/fiscal/chaves_form.html", contexto)


class ChavesFiscaisLinkMixin:
    """Para EmpresaAdmin: coluna com o link para as chaves fiscais."""

    @admin.display(description="Chaves fiscais")
    def chaves_fiscais(self, obj):
        if obj.schema_name == get_public_schema_name():
            return "—"
        return format_html('<a href="{}">Configurar</a>',
                           reverse("admin:fiscal_chaves_empresa", args=[obj.schema_name]))
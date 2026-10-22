# apps/saft/views.py
"""Interface web SAF-T (AO), centralizada nos serviços e modelos da app fiscal."""
from __future__ import annotations

import inspect
import logging
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta
from xml.dom import minidom

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.fiscal.models import TaxaIVAAGT
from apps.fiscal.services.utils import SAFTExportService

logger = logging.getLogger("saft")
SAFT_NAMESPACE = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _tenant(request):
    tenant = getattr(request, "tenant", None)
    if not tenant or getattr(tenant, "schema_name", "public") == "public":
        return None
    return tenant


def _field_names(model):
    return {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}


def _export_model():
    """Usa o modelo de histórico fiscal existente, sem duplicá-lo em apps.saft."""
    try:
        return apps.get_model("fiscal", "SAFTExport")
    except LookupError as exc:
        raise ImproperlyConfigured(
            "Confirme o nome do modelo de histórico existente na app Fiscal. "
            "Este módulo não deve criar um segundo modelo SAFTExport."
        ) from exc


def _tenant_qs(request, qs):
    tenant = _tenant(request)
    if tenant is None:
        return qs.none()
    if "empresa" in _field_names(qs.model):
        return qs.filter(empresa=tenant)
    # Em schemas separados, o schema activo já é a fronteira de isolamento.
    return qs


def _field(model, candidates):
    names = _field_names(model)
    return next((name for name in candidates if name in names), None)


def _normalizar_exportacao(obj):
    model = type(obj)
    date_field = _field(model, ("data_exportacao", "created_at", "data_criacao", "criado_em", "timestamp"))
    start_field = _field(model, ("data_inicio", "periodo_inicio", "start_date"))
    end_field = _field(model, ("data_fim", "periodo_fim", "end_date"))
    path_field = _field(model, ("caminho_arquivo", "ficheiro", "arquivo", "file_path"))
    size_field = _field(model, ("tamanho_arquivo", "tamanho_bytes", "file_size", "tamanho"))
    error_field = _field(model, ("erro_message", "mensagem_erro", "erro", "error_message"))
    status_field = _field(model, ("status", "estado"))
    success_field = _field(model, ("sucesso", "success", "is_success"))
    status = getattr(obj, status_field, "") if status_field else ""
    success = getattr(obj, success_field, None) if success_field else None
    if success is None:
        success = str(status).lower() in {"gerado", "enviado", "sucesso", "success", "concluido", "concluído"}
    path = getattr(obj, path_field, None) if path_field else None
    return {
        "id": obj.pk, "data_exportacao": getattr(obj, date_field, None) if date_field else None,
        "data_inicio": getattr(obj, start_field, None) if start_field else None,
        "data_fim": getattr(obj, end_field, None) if end_field else None,
        "status": status or ("Gerado" if success else "Falhou"), "sucesso": bool(success),
        "tamanho_arquivo": getattr(obj, size_field, 0) if size_field else 0,
        "tamanho_mb": round((getattr(obj, size_field, 0) or 0) / (1024 * 1024), 2) if size_field else 0,
        "erro_message": getattr(obj, error_field, "") if error_field else "",
        "caminho_arquivo": path, "tem_ficheiro": bool(path),
        "usuario": getattr(obj, "usuario", getattr(obj, "criado_por", None)),
    }


def _filtered_exports(request):
    model = _export_model()
    qs = _tenant_qs(request, model.objects.all())
    date_field = _field(model, ("data_exportacao", "created_at", "data_criacao", "criado_em", "timestamp"))
    qs = qs.order_by(f"-{date_field}" if date_field else "-pk")
    if request.GET.get("periodo") and date_field:
        try:
            dias = max(1, min(int(request.GET["periodo"]), 3650))
            qs = qs.filter(**{f"{date_field}__gte": timezone.now() - timedelta(days=dias)})
        except (ValueError, TypeError):
            pass
    status = request.GET.get("status", "")
    ok_field = _field(model, ("sucesso", "success", "is_success"))
    status_field = _field(model, ("status", "estado"))
    if status in ("sucesso", "erro"):
        if ok_field:
            qs = qs.filter(**{ok_field: status == "sucesso"})
        elif status_field:
            states = ["gerado", "enviado", "sucesso", "success", "concluido", "concluído"] if status == "sucesso" else ["falhou", "erro", "error", "failed"]
            qs = qs.filter(**{f"{status_field}__in": states})
    for param, operator in (("data_inicio", "gte"), ("data_fim", "lte")):
        raw = request.GET.get(param, "")
        if raw and date_field:
            try:
                qs = qs.filter(**{f"{date_field}__date__{operator}": date.fromisoformat(raw)})
            except (ValueError, TypeError):
                pass
    user_field = _field(model, ("usuario", "criado_por", "created_by"))
    username = request.GET.get("usuario", "").strip()
    if username and user_field and request.user.has_perm("fiscal.view_all_exports"):
        qs = qs.filter(**{f"{user_field}__username__icontains": username})
    return qs


def _call_with_supported_kwargs(callable_obj, values):
    """Passa apenas argumentos reconhecidos pela assinatura pública do serviço fiscal."""
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return callable_obj(**values)
    params = signature.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return callable_obj(**values)
    accepted = {k: v for k, v in values.items() if k in params}
    missing = [p.name for p in params.values() if p.name != "self" and p.default is inspect.Parameter.empty
               and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
               and p.name not in accepted]
    if missing:
        return callable_obj(**values)
    return callable_obj(**accepted)


def _extract_xml(result):
    if isinstance(result, HttpResponse):
        return bytes(result.content)
    if isinstance(result, bytes):
        return result
    if isinstance(result, str):
        if result.lstrip().startswith("<"):
            return result.encode("utf-8")
        if default_storage.exists(result):
            with default_storage.open(result, "rb") as fh:
                return fh.read()
    if isinstance(result, dict):
        for key in ("xml_content", "conteudo_xml", "xml", "content", "conteudo"):
            value = result.get(key)
            if isinstance(value, str): return value.encode("utf-8")
            if isinstance(value, bytes): return value
        for key in ("caminho_arquivo", "file_path", "path"):
            path = result.get(key)
            if path and default_storage.exists(str(path)):
                with default_storage.open(str(path), "rb") as fh: return fh.read()
    # Alguns serviços devolvem a instância do registo de exportação em vez do XML.
    for attr in ("caminho_arquivo", "ficheiro", "arquivo", "file_path"):
        candidate = getattr(result, attr, None)
        if not candidate:
            continue
        if hasattr(candidate, "open"):
            with candidate.open("rb") as fh:
                return fh.read()
        if default_storage.exists(str(candidate)):
            with default_storage.open(str(candidate), "rb") as fh:
                return fh.read()
    for attr in ("xml_content", "conteudo_xml", "xml", "content", "conteudo"):
        candidate = getattr(result, attr, None)
        if isinstance(candidate, str): return candidate.encode("utf-8")
        if isinstance(candidate, bytes): return candidate
    if hasattr(result, "read"):
        value = result.read()
        return value.encode("utf-8") if isinstance(value, str) else value
    raise RuntimeError("O serviço fiscal não devolveu XML nem um caminho de ficheiro reconhecido; confirme a API pública de SAFTExportService.")


def _gerar_xml_pela_app_fiscal(empresa, inicio, fim, usuario):
    """Invoca a implementação SAF-T de apps.fiscal; não duplica o gerador dentro de apps.saft."""
    values = {"empresa": empresa, "tenant": empresa, "data_inicio": inicio, "data_fim": fim,
              "inicio": inicio, "fim": fim, "usuario": usuario, "user": usuario,
              "taxa_iva_model": TaxaIVAAGT, "modelo_taxas": TaxaIVAAGT, "taxas_iva": TaxaIVAAGT,
              "taxas": TaxaIVAAGT, "taxa_iva": TaxaIVAAGT, "modelo_taxa": TaxaIVAAGT, "TaxaIVAAGT": TaxaIVAAGT}
    service = SAFTExportService
    if inspect.isclass(service):
        service = _call_with_supported_kwargs(service, values)
    methods = [getattr(service, name, None) for name in
               ("gerar_xml", "generate_xml", "exportar_xml", "gerar_saft", "exportar_saft", "exportar", "gerar", "execute", "run")]
    methods = [method for method in methods if callable(method)]
    if not methods and callable(service):
        methods = [service]
    if not methods:
        raise ImproperlyConfigured("SAFTExportService não apresenta um método público de geração conhecido; ligue a view ao método real da app Fiscal.")
    last_error = None
    for method in methods:
        try:
            return _extract_xml(_call_with_supported_kwargs(method, values))
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Falha ao gerar SAF-T através de apps.fiscal: {last_error}") from last_error


def _registar_exportacao(empresa, inicio, fim, usuario, filename, xml_content):
    """Cria registo de histórico no modelo fiscal existente, quando o respectivo contrato o permite."""
    model = _export_model()
    names = _field_names(model)
    company = "empresa" if "empresa" in names else None
    start = _field(model, ("data_inicio", "periodo_inicio", "start_date"))
    end = _field(model, ("data_fim", "periodo_fim", "end_date"))
    user = _field(model, ("usuario", "criado_por", "created_by"))
    size = _field(model, ("tamanho_arquivo", "tamanho_bytes", "file_size", "tamanho"))
    status = _field(model, ("status", "estado"))
    success = _field(model, ("sucesso", "success", "is_success"))
    path = _field(model, ("caminho_arquivo", "file_path", "ficheiro", "arquivo"))
    filename_field = _field(model, ("nome_arquivo", "filename", "file_name", "nome_ficheiro"))
    exported_at_field = _field(model, ("data_exportacao", "data_geracao", "gerado_em", "created_at", "data_criacao", "criado_em"))
    values = {}
    start_value, end_value = inicio, fim
    if start and model._meta.get_field(start).get_internal_type() == "DateField": start_value = inicio.date() if isinstance(inicio, datetime) else inicio
    if end and model._meta.get_field(end).get_internal_type() == "DateField": end_value = fim.date() if isinstance(fim, datetime) else fim
    for field, value in ((company, empresa), (start, start_value), (end, end_value), (user, usuario), (size, len(xml_content)), (success, True), (filename_field, filename)):
        if field: values[field] = value
    if exported_at_field:
        time_field = model._meta.get_field(exported_at_field)
        values[exported_at_field] = timezone.localdate() if time_field.get_internal_type() == "DateField" else timezone.now()
    if status:
        choices = {value for value, _ in model._meta.get_field(status).choices}
        values[status] = "gerado" if not choices or "gerado" in choices else next(iter(choices))
    try:
        record = model(**values)
        if path:
            field_obj = model._meta.get_field(path)
            storage_path = f"saft/{getattr(empresa, 'schema_name', 'tenant')}/{filename}"
            if field_obj.get_internal_type() in ("FileField", "ImageField"):
                getattr(record, path).save(filename, ContentFile(xml_content), save=False)
            else:
                setattr(record, path, default_storage.save(storage_path, ContentFile(xml_content)))
        record.save()
        return record
    except Exception:
        # A exportação poderá ter sido registada pelo serviço fiscal. Não ocultamos a falha: fica no log.
        logger.exception("XML gerado, mas não foi possível registar o histórico no modelo fiscal SAFTExport.")
        return None


class PermissaoAcaoMixin:
    """Aplica a acção RBAC se o utilizador tiver funcionário associado; permissões Django continuam obrigatórias."""
    acao_requerida = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        funcionario = None
        for attr in ("funcionario", "funcionario_relacionado", "employee"):
            try: funcionario = getattr(request.user, attr, None)
            except Exception: funcionario = None
            if funcionario: break
        if self.acao_requerida and funcionario and hasattr(funcionario, "pode_realizar_acao"):
            if not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"O seu perfil não permite realizar a acção '{self.acao_requerida}'.")
                return redirect("home")
        return super().dispatch(request, *args, **kwargs)


class SaftExportView(LoginRequiredMixin, PermissionRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "exportar_saft"
    permission_required = ("fiscal.add_saftexport", "fiscal.export_saft")
    template_name = "saft/saft_export_form.html"

    def has_permission(self):
        return self.request.user.is_superuser or any(self.request.user.has_perm(p) for p in self.get_permission_required())

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()
        return render(request, self.template_name, {"empresa": _tenant(request), "data_inicio_default": today.replace(day=1).isoformat(), "data_fim_default": today.isoformat()})

    def post(self, request, *args, **kwargs):
        empresa = _tenant(request)
        if empresa is None:
            return render(request, self.template_name, {"error": "Empresa/tenant não encontrado."}, status=400)
        try:
            inicio = date.fromisoformat(request.POST.get("data_inicio", ""))
            fim = date.fromisoformat(request.POST.get("data_fim", ""))
            if inicio > fim: raise ValueError("A data inicial não pode ser posterior à data final.")
        except ValueError as exc:
            return render(request, self.template_name, {"error": str(exc), "empresa": empresa, "data_inicio_default": request.POST.get("data_inicio", ""), "data_fim_default": request.POST.get("data_fim", "")}, status=400)
        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(datetime.combine(inicio, time.min), tz)
        end_dt = timezone.make_aware(datetime.combine(fim, time.max), tz)
        try:
            xml_content = _gerar_xml_pela_app_fiscal(empresa, start_dt, end_dt, request.user)
            ET.fromstring(xml_content)  # verifica XML bem formado; não substitui validação XSD.
            filename = f"{getattr(empresa, 'nif', 'empresa') or 'empresa'}_{inicio:%Y%m%d}_{fim:%Y%m%d}.xml"
            _registar_exportacao(empresa, start_dt, end_dt, request.user, filename, xml_content)
            logger.info("SAF-T gerado: user_id=%s tenant=%s intervalo=%s..%s", request.user.pk, empresa.schema_name, inicio, fim)
            response = HttpResponse(xml_content, content_type="application/xml; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception as exc:
            logger.exception("Falha na exportação SAF-T do tenant %s", getattr(empresa, "schema_name", "?"))
            return render(request, self.template_name, {"error": "Não foi possível gerar o SAF-T. Confirme a API pública do serviço fiscal e consulte os logs.", "error_detail": str(exc) if settings.DEBUG else "", "empresa": empresa, "data_inicio_default": inicio.isoformat(), "data_fim_default": fim.isoformat()}, status=500)


class SaftHistoricoView(LoginRequiredMixin, PermissionRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "ver_historico_saft"
    permission_required = "fiscal.view_saftexport"
    template_name = "saft/saft_historico.html"
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        empresa = _tenant(request)
        if empresa is None: return render(request, self.template_name, {"error": "Empresa/tenant não encontrado.", "exports": []}, status=400)
        try:
            qs = _filtered_exports(request)
            page_obj = Paginator(qs, self.paginate_by).get_page(request.GET.get("page", 1))
            rows = [_normalizar_exportacao(obj) for obj in page_obj.object_list]
            all_rows = [_normalizar_exportacao(obj) for obj in _tenant_qs(request, _export_model().objects.all())]
            total = len(all_rows); successful = sum(1 for row in all_rows if row["sucesso"])
            recent_cutoff = timezone.now() - timedelta(days=30)
            def _is_recent(value):
                if value is None: return False
                if isinstance(value, datetime): return value >= recent_cutoff
                return value >= recent_cutoff.date()
            recent = sum(1 for row in all_rows if _is_recent(row["data_exportacao"]))
            size_sum = sum((row["tamanho_arquivo"] or 0) for row in all_rows if row["sucesso"])
            stats = {"total_exports": total, "exports_sucesso": successful, "exports_erro": total-successful, "exports_recentes": recent, "total_size_mb": round(size_sum / (1024*1024), 2), "taxa_sucesso": round(successful*100/total, 1) if total else 0}
            return render(request, self.template_name, {"page_obj": page_obj, "exports": rows, "total_exports": page_obj.paginator.count, "stats": stats, "empresa": empresa, "pode_filtrar_usuario": request.user.has_perm("fiscal.view_all_exports"), "filtros_ativos": {key: request.GET.get(key, "") for key in ("periodo", "status", "data_inicio", "data_fim", "usuario")}})
        except Exception as exc:
            logger.exception("Falha ao carregar histórico SAF-T")
            return render(request, self.template_name, {"error": str(exc) if settings.DEBUG else "Erro interno ao carregar histórico.", "exports": []}, status=500)


class SaftDownloadView(LoginRequiredMixin, PermissionRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "baixar_saft"
    permission_required = "fiscal.view_saftexport"

    def get(self, request, export_id, *args, **kwargs):
        if _tenant(request) is None: raise Http404("Tenant não encontrado.")
        obj = get_object_or_404(_tenant_qs(request, _export_model().objects.all()), pk=export_id)
        row = _normalizar_exportacao(obj)
        if not row["sucesso"] or not row["caminho_arquivo"]: raise Http404("O ficheiro não está disponível para download.")
        try:
            file_obj = row["caminho_arquivo"]
            if hasattr(file_obj, "open"):
                fh = file_obj.open("rb"); filename = os.path.basename(file_obj.name)
            else:
                path = str(file_obj)
                if not default_storage.exists(path): raise Http404("Ficheiro não encontrado no armazenamento.")
                fh = default_storage.open(path, "rb"); filename = os.path.basename(path)
            logger.info("Download SAF-T export_id=%s user_id=%s", export_id, request.user.pk)
            return FileResponse(fh, as_attachment=True, filename=filename or f"saft-{export_id}.xml", content_type="application/xml")
        except Http404: raise
        except Exception:
            logger.exception("Falha no download SAF-T id=%s", export_id)
            messages.error(request, "Não foi possível descarregar o ficheiro.")
            return redirect("saft:historico")


class SaftValidarView(LoginRequiredMixin, PermissionRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "validar_saft"
    permission_required = "fiscal.view_saftexport"
    template_name = "saft/saft_validar.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"max_file_size_mb": MAX_UPLOAD_BYTES // (1024*1024), "saft_version": "SAF-T AO — versão definida pela app Fiscal"})

    def post(self, request, *args, **kwargs):
        uploaded = request.FILES.get("saft_file")
        if not uploaded: return self._response(request, {"success": False, "valid": False, "error": "Seleccione um ficheiro XML."}, 400)
        if uploaded.size > MAX_UPLOAD_BYTES: return self._response(request, {"success": False, "valid": False, "error": f"O ficheiro excede {MAX_UPLOAD_BYTES//(1024*1024)} MB."}, 400)
        if uploaded.size == 0 or not uploaded.name.lower().endswith(".xml"): return self._response(request, {"success": False, "valid": False, "error": "Envie um ficheiro .xml não vazio."}, 400)
        try:
            raw = uploaded.read()
            try: xml_text = raw.decode("utf-8-sig")
            except UnicodeDecodeError: return self._response(request, {"success": False, "valid": False, "error": "O ficheiro deve estar codificado em UTF-8."}, 400)
            result = self._validar_com_fiscal(xml_text)
            result.setdefault("success", True); result.setdefault("details", {})
            result["details"].update({"filename": uploaded.name, "file_size_bytes": len(raw), "validation_date": timezone.now().isoformat()})
            logger.info("SAF-T validation user_id=%s filename=%s valid=%s", request.user.pk, uploaded.name, result.get("valid"))
            return self._response(request, result)
        except Exception as exc:
            logger.exception("Falha de validação SAF-T")
            return self._response(request, {"success": False, "valid": False, "error": "Falha interna durante a validação.", "debug": str(exc) if settings.DEBUG else ""}, 500)

    def _validar_com_fiscal(self, xml_text):
        # Se a app fiscal tiver um validador público, usa-o primeiro.
        for module_name, class_name in (("apps.fiscal.services.utils", "SAFTValidationService"), ("apps.fiscal.services.utils", "SaftValidationService"), ("apps.fiscal.services.saft_validation_service", "SAFTValidator"), ("apps.fiscal.services.saft_validation_service", "SaftValidationService")):
            try:
                module = __import__(module_name, fromlist=[class_name]); cls = getattr(module, class_name); validator = cls()
                for method_name in ("validar_xml", "validate_xml", "validar", "validate"):
                    method = getattr(validator, method_name, None)
                    if callable(method):
                        result = _call_with_supported_kwargs(method, {"xml_content": xml_text, "xml_text": xml_text, "conteudo": xml_text, "xml": xml_text})
                        return result if isinstance(result, dict) else {"success": True, "valid": bool(result), "title": "Resultado da validação", "message": str(result)}
            except (ImportError, AttributeError, TypeError):
                continue
        try:
            ET.fromstring(xml_text)
        except ET.ParseError as exc:
            return {"success": True, "valid": False, "title": "XML malformado", "message": str(exc),
                    "errors": [str(exc)], "warnings": [], "validation_level": "xml_well_formed_only"}
        # Não duplicar aqui as regras fiscais nem afirmar conformidade com o XSD.
        # Sem um validador central confirmado, o estado fiscal é inconclusivo.
        return {"success": True, "valid": None, "title": "Validação fiscal não configurada",
                "message": "O ficheiro é XML bem formado, mas não foi encontrada uma implementação de validação SAF-T/XSD na app Fiscal. A validade fiscal não pode ser confirmada.",
                "errors": [], "warnings": ["A validação XML bem formado não substitui o XSD oficial da AGT."],
                "validation_level": "xml_well_formed_only_no_fiscal_validator"}

    def _response(self, request, payload, status=200):
        if "application/json" in request.headers.get("Accept", "") or request.headers.get("X-Requested-With") == "XMLHttpRequest": return JsonResponse(payload, status=status)
        return render(request, self.template_name, {"max_file_size_mb": MAX_UPLOAD_BYTES // (1024*1024), "saft_version": "SAF-T AO", "validation_result": payload, "upload_error": payload.get("error")}, status=status)


class SaftVisualizarView(LoginRequiredMixin, PermissionRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "visualizar_saft"
    permission_required = "fiscal.view_saftexport"
    template_name = "saft/saft_visualizar.html"

    def get(self, request, export_id, *args, **kwargs):
        if _tenant(request) is None: raise Http404("Tenant não encontrado.")
        obj = get_object_or_404(_tenant_qs(request, _export_model().objects.all()), pk=export_id)
        row = _normalizar_exportacao(obj)
        if not row["sucesso"] or not row["caminho_arquivo"]: raise Http404("O ficheiro SAF-T não está disponível.")
        try:
            f = row["caminho_arquivo"]
            if hasattr(f, "open"):
                with f.open("rb") as fh: xml_text = fh.read().decode("utf-8-sig")
            else:
                with default_storage.open(str(f), "rb") as fh: xml_text = fh.read().decode("utf-8-sig")
            root = ET.fromstring(xml_text); ns = {"saft": SAFT_NAMESPACE}; header = root.find("saft:Header", ns)
            header_data = {child.tag.split("}")[-1]: child.text or "" for child in list(header)} if header is not None else {}
            count_tags = {"Clientes": "Customer", "Fornecedores": "Supplier", "Produtos": "Product", "Facturas": "Invoice", "Taxas de imposto": "TaxTableEntry"}
            counts = {label: len(root.findall(f".//saft:{tag}", ns)) for label, tag in count_tags.items()}
            lines = minidom.parseString(xml_text.encode("utf-8")).toprettyxml(indent="  ").splitlines()
            return render(request, self.template_name, {"export_log": row, "parsed_data": {"header": header_data, "counts": counts, "file_size": len(xml_text.encode("utf-8")), "total_elements": sum(1 for _ in root.iter())}, "xml_preview": "\n".join(lines[:100])})
        except Exception:
            logger.exception("Falha ao visualizar SAF-T id=%s", export_id)
            messages.error(request, "Não foi possível processar o XML para visualização.")
            return redirect("saft:historico")


class SaftStatusAjaxView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "ver_status_saft"
    def get(self, request, *args, **kwargs):
        if _tenant(request) is None: return JsonResponse({"success": False, "error": "Tenant inválido."}, status=400)
        try:
            model = _export_model(); qs = _tenant_qs(request, model.objects.all())
            field = _field(model, ("data_exportacao", "created_at", "data_criacao", "criado_em"))
            if field: qs = qs.filter(**{f"{field}__gte": timezone.now()-timedelta(hours=24)}).order_by(f"-{field}")
            else: qs = qs.order_by("-pk")
            payload = []
            for obj in qs[:5]:
                row = _normalizar_exportacao(obj)
                payload.append({"id": row["id"], "data_exportacao": row["data_exportacao"],
                                "data_inicio": row["data_inicio"], "data_fim": row["data_fim"],
                                "status": row["status"], "sucesso": row["sucesso"],
                                "tamanho_mb": row["tamanho_mb"], "erro_message": row["erro_message"]})
            return JsonResponse({"success": True, "exports": payload, "timestamp": timezone.now().isoformat()})
        except Exception as exc:
            logger.exception("Falha a obter estado SAF-T")
            return JsonResponse({"success": False, "error": str(exc) if settings.DEBUG else "Erro interno."}, status=500)

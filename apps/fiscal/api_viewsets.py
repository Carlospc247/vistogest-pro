# apps/fiscal/api_viewsets.py
"""ViewSets da API fiscal corrigidos para modelos tenant-local.

Não filtram modelos tenant-local por `empresa_id` quando o campo não existe.
O schema activo do django-tenants faz o isolamento; DocumentoFiscal/SAFTExport
mantêm adicionalmente a referência ao registo global da empresa actual.
"""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.empresas.models import Empresa
from apps.fiscal.models import AssinaturaDigital, DocumentoFiscal, RetencaoFonte, TaxaIVAAGT
from apps.fiscal.serializers import (
    AssinaturaDigitalSerializer,
    DocumentoFiscalSerializer,
    RetencaoFonteSerializer,
    TaxaIVAAGTSerializer,
)
from .services.documento_fiscal_service import DocumentoFiscalService
from .services.utils import FiscalServiceError, RetencaoFonteService


def _empresa_do_schema():
    schema_name = getattr(connection, "schema_name", "public")
    tenant = getattr(connection, "tenant", None)
    if schema_name == "public" or tenant is None or getattr(tenant, "schema_name", None) != schema_name:
        raise PermissionDenied("A operação deve ser executada no schema de um tenant válido.")
    return tenant


class TenantFiscalAPIViewMixin:
    """Bloqueia consultas de tabelas tenant-local a partir do schema public."""
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _empresa_do_schema()


class FiscalDashboardAPIView(TenantFiscalAPIViewMixin, APIView):
    """Resumo da área fiscal limitado ao schema do tenant autenticado."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        empresa = _empresa_do_schema()
        docs = DocumentoFiscal.objects.filter(empresa_id=empresa.pk)
        estados = {v for v, _ in DocumentoFiscal._meta.get_field("status").choices}
        draft_values = [v for v in ("draft", "rascunho") if v in estados]
        data_inicio = request.query_params.get("data_inicio")
        data_fim = request.query_params.get("data_fim")
        if data_inicio:
            try:
                date.fromisoformat(data_inicio)
            except ValueError:
                return Response({"detail": "data_inicio deve usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
            docs = docs.filter(data_emissao__gte=data_inicio)
        if data_fim:
            try:
                date.fromisoformat(data_fim)
            except ValueError:
                return Response({"detail": "data_fim deve usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
            docs = docs.filter(data_emissao__lte=data_fim)
        retencoes = RetencaoFonte.objects.all()
        total_retido = retencoes.aggregate(total=Sum("valor_retido"))["total"] or Decimal("0.00")
        return Response({
            "empresa": {"id": empresa.pk, "nome": empresa.nome, "nif": getattr(empresa, "nif", "")},
            "periodo": {"data_inicio": data_inicio, "data_fim": data_fim},
            "metricas": {
                "total_documentos": docs.count(),
                "documentos_rascunho": docs.filter(status__in=draft_values).count() if draft_values else 0,
                "total_taxas_ativas": TaxaIVAAGT.objects.filter(ativo=True).count(),
                "total_retencoes": retencoes.count(),
                "total_valor_retido": str(total_retido),
            },
            "gerado_em": timezone.now().isoformat(),
        })


class TaxaIVAAGTViewSet(TenantFiscalAPIViewMixin, viewsets.ModelViewSet):
    serializer_class = TaxaIVAAGTSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["tax_type", "tax_code", "ativo"]
    search_fields = ["nome", "tax_code"]
    ordering_fields = ["tax_percentage", "created_at"]
    ordering = ["-tax_percentage"]

    def get_queryset(self):
        if getattr(connection, "schema_name", "public") == "public":
            return TaxaIVAAGT.objects.none()
        # TaxaIVAAGT não contém FK empresa: o schema separa cada tenant.
        return TaxaIVAAGT.objects.all()

    def perform_create(self, serializer):
        _empresa_do_schema()
        serializer.save()

    @action(detail=False, methods=["get"])
    def ativas(self, request):
        qs = self.get_queryset().filter(ativo=True)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def calcular_iva(self, request, pk=None):
        taxa = self.get_object()
        try:
            base = Decimal(str(request.data.get("valor_base", "")))
        except Exception:
            return Response({"error": "valor_base inválido."}, status=status.HTTP_400_BAD_REQUEST)
        if base < 0:
            return Response({"error": "valor_base não pode ser negativo."}, status=status.HTTP_400_BAD_REQUEST)
        percentagem = taxa.tax_percentage if taxa.tax_type == "IVA" else Decimal("0")
        valor_iva = (base * percentagem / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Response({
            "taxa_id": taxa.pk,
            "valor_base": str(base),
            "taxa_percentagem": str(percentagem),
            "valor_iva": str(valor_iva),
            "valor_total": str(base + valor_iva),
        })

    @action(detail=False, methods=["get"])
    def export_saft(self, request):
        empresa = _empresa_do_schema()
        taxa_data = []
        for taxa in self.get_queryset():
            item = {
                "TaxType": taxa.tax_type,
                "TaxCode": taxa.tax_code,
                "Description": taxa.nome,
                "TaxCountryRegion": taxa.codigo_pais,
            }
            if taxa.tax_type == "IVA":
                item["TaxPercentage"] = float(taxa.tax_percentage)
            elif taxa.exemption_reason:
                item["TaxExemptionCode"] = taxa.exemption_reason
            taxa_data.append(item)
        return Response({
            "TaxTable": taxa_data,
            "GeneratedAt": timezone.now().isoformat(),
            "Company": empresa.nome,
        })


class AssinaturaDigitalViewSet(TenantFiscalAPIViewMixin, viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        _empresa_do_schema()
        assinatura = AssinaturaDigital.get_solo()
        return Response(AssinaturaDigitalSerializer(assinatura, context={"request": request}).data)

    @action(detail=False, methods=["post"])
    def configurar_chave(self, request):
        _empresa_do_schema()
        nif = (request.data.get("nif_contribuinte") or "").strip()
        chave_privada = (request.data.get("chave_privada") or "").strip()
        chave_publica = (request.data.get("chave_contribuinte_publica") or request.data.get("chave_publica") or "").strip()
        if not nif or not chave_privada or not chave_publica:
            return Response(
                {"error": "NIF, chave privada e chave pública emitidas pela AGT são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            config = AssinaturaDigital.get_solo()
            config.definir_chaves(
                nif=nif,
                chave_privada_pem=chave_privada,
                chave_publica_pem=chave_publica,
                usuario=request.user,
            )
            return Response(AssinaturaDigitalSerializer(config, context={"request": request}).data)
        except (FiscalServiceError, ValidationError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def assinar_documento(self, request):
        _empresa_do_schema()
        from .services.assinatura_service import AssinaturaDigitalService
        dados_documento = request.data.get("documento")
        if not isinstance(dados_documento, dict) or not dados_documento:
            return Response({"error": "Envie o objecto 'documento'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            jws = AssinaturaDigitalService.assinar_documento(dados_documento)
            return Response({"jwsDocumentSignature": jws})
        except FiscalServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def status_cadeia(self, request):
        _empresa_do_schema()
        config = AssinaturaDigital.get_solo()
        return Response({
            "configurada": config.esta_configurada,
            "nif_contribuinte": config.nif_contribuinte,
            "ultimo_hash": config.ultimo_hash,
            "series_fiscais": config.dados_series_fiscais,
        })


class RetencaoFonteViewSet(TenantFiscalAPIViewMixin, viewsets.ModelViewSet):
    serializer_class = RetencaoFonteSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["tipo_retencao", "paga_ao_estado", "data_retencao"]
    search_fields = ["referencia_documento", "fornecedor__razao_social"]
    ordering_fields = ["data_retencao", "valor_retido"]
    ordering = ["-data_retencao"]

    def get_queryset(self):
        if getattr(connection, "schema_name", "public") == "public":
            return RetencaoFonte.objects.none()
        # O modelo fornecido não tem empresa_id; fornecedores/contas e retenções
        # já residem no schema do tenant actual.
        return RetencaoFonte.objects.select_related("fornecedor", "conta_pagar").all()

    def perform_create(self, serializer):
        # Preserva o serviço contabilístico existente; a empresa é contexto do
        # tenant e não um campo persistido em RetencaoFonte. O serviço deve
        # remover/consumir esta informação antes de criar o modelo.
        empresa = _empresa_do_schema()
        dados = dict(serializer.validated_data)
        dados["empresa"] = empresa
        retencao = RetencaoFonteService.criar_retencao(dados)
        serializer.instance = retencao

    @action(detail=True, methods=["post"])
    def marcar_paga(self, request, pk=None):
        retencao = self.get_object()
        raw_date = request.data.get("data_pagamento")
        try:
            data_pagamento = datetime.strptime(raw_date, "%Y-%m-%d").date() if raw_date else date.today()
        except (TypeError, ValueError):
            return Response({"error": "data_pagamento deve usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            actualizada = RetencaoFonteService.processar_pagamento_estado(retencao.pk, data_pagamento)
            return Response(self.get_serializer(actualizada).data)
        except FiscalServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def relatorio_mensal(self, request):
        try:
            ano = int(request.query_params.get("ano", date.today().year))
            mes = int(request.query_params.get("mes", date.today().month))
            if mes < 1 or mes > 12:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "ano/mes inválidos."}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset().filter(data_retencao__year=ano, data_retencao__month=mes)
        resumo = {}
        for item in qs:
            row = resumo.setdefault(item.tipo_retencao, {
                "total_valor": Decimal("0.00"), "total_count": 0,
                "pagas_count": 0, "pendentes_count": 0,
            })
            row["total_valor"] += item.valor_retido
            row["total_count"] += 1
            row["pagas_count" if item.paga_ao_estado else "pendentes_count"] += 1
        for row in resumo.values():
            row["total_valor"] = str(row["total_valor"])
        return Response({"periodo": f"{mes:02d}/{ano}", "relatorio": resumo, "gerado_em": timezone.now().isoformat()})


class DocumentoFiscalViewSet(TenantFiscalAPIViewMixin, viewsets.ModelViewSet):
    serializer_class = DocumentoFiscalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(connection, "schema_name", "public") == "public":
            return DocumentoFiscal.objects.none()
        tenant = _empresa_do_schema()
        return DocumentoFiscal.objects.filter(empresa_id=tenant.pk).select_related(
            "cliente", "empresa", "usuario_criacao", "documento_original"
        ).order_by("-data_emissao", "-numero")

    def perform_create(self, serializer):
        empresa = _empresa_do_schema()
        serializer.save(empresa=empresa, usuario_criacao=self.request.user, status="draft")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != "draft":
            tentativa = set(request.data.keys()) & DocumentoFiscalService.CAMPOS_FISCAIS_READONLY
            if tentativa:
                return Response({"detail": "Campos fiscais de documentos emitidos não podem ser alterados: " + ", ".join(sorted(tentativa))}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Documentos fiscais não podem ser apagados; use cancelar ou rectificar."}, status=status.HTTP_403_FORBIDDEN)

    @action(detail=True, methods=["post"])
    def emitir(self, request, pk=None):
        try:
            doc = DocumentoFiscalService.emitir(self.get_object(), request.user)
            return Response(self.get_serializer(doc).data)
        except (FiscalServiceError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def lancar(self, request, pk=None):
        try:
            doc = DocumentoFiscalService.lancar(self.get_object(), request.user)
            return Response(self.get_serializer(doc).data)
        except (FiscalServiceError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def pagar(self, request, pk=None):
        try:
            doc = DocumentoFiscalService.registar_pagamento(self.get_object(), request.user, request.data or None)
            return Response(self.get_serializer(doc).data)
        except (FiscalServiceError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        try:
            doc = DocumentoFiscalService.cancelar(
                self.get_object(), request.user,
                motivo_codigo=request.data.get("motivo_codigo", "N"),
                motivo_texto=request.data.get("motivo_texto", ""),
            )
            return Response(self.get_serializer(doc).data)
        except (FiscalServiceError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def rectificar(self, request, pk=None):
        try:
            doc = DocumentoFiscalService.rectificar(
                self.get_object(), request.user,
                tipo_rectificativo=request.data.get("tipo_rectificativo", "NC"),
                motivo=request.data.get("motivo", ""),
            )
            return Response(self.get_serializer(doc).data, status=status.HTTP_201_CREATED)
        except (FiscalServiceError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["patch"], url_path="comentarios")
    def actualizar_comentarios(self, request, pk=None):
        try:
            doc = DocumentoFiscalService.actualizar_comentarios(
                self.get_object(), request.user, request.data.get("comentarios", "")
            )
            return Response({"comentarios": doc.comentarios})
        except (FiscalServiceError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

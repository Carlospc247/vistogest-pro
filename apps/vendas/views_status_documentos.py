"""Painel de estados de documentos fiscais, isolado por schema/tenant.

As transições usam os métodos de domínio de DocumentoFiscal; a view nunca
atribui directamente um novo valor a `status`.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django_tenants.utils import get_public_schema_name

from apps.fiscal.models import DocumentoFiscal


logger = logging.getLogger("fiscal.status_documentos")



class PermissaoAcaoMixin(AccessMixin):
    # CRÍTICO: Definir esta variável na View
    acao_requerida = None 

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            # Tenta obter o Funcionario (ligação fundamental)
            funcionario = request.user.funcionario 
        except Exception:
            messages.error(request, "Acesso negado. O seu usuário não está ligado a um registro de funcionário.")
            return self.handle_no_permission()

        if self.acao_requerida:
            # Usa a lógica dinâmica do modelo Funcionario (que já criámos)
            if not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.")
                return redirect(reverse_lazy('core_tenants:dashboard'))

        return super().dispatch(request, *args, **kwargs)

 
class StatusDocumento(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """Lista documentos por estado e permite transições explicitamente válidas."""
    acao_requerida = 'acessar_documentos'
    template_name = "vendas/status_documentos.html"
    paginate_by = 30

    ESTADOS = (
        ("draft", "Rascunho", "Documentos ainda não confirmados", "file-pen", "amber"),
        ("confirmed", "Confirmado", "Documentos confirmados no VistoGest", "file-circle-check", "blue"),
        ("posted", "Lançado", "Documentos lançados no fluxo interno", "book-open", "indigo"),
        ("paid", "Pago", "Documentos marcados como pagos", "circle-check", "green"),
        ("cancelled", "Cancelado", "Documentos cancelados com histórico preservado", "ban", "red"),
        ("rectified", "Retificado", "Documentos substituídos por documento correctivo", "file-pen-line", "purple"),
    )

    TIPOS_RECTIFICATIVO = ("NC", "ND", "RE")
    FORMAS_PAGAMENTO = (
        ("dinheiro", "Dinheiro"),
        ("transferencia", "Transferência bancária"),
        ("tpa", "TPA / Cartão"),
        ("cheque", "Cheque"),
        ("outro", "Outro"),
    )

    def _validar_tenant(self):
        schema = getattr(connection, "schema_name", None)
        if not schema or schema == get_public_schema_name():
            raise PermissionDenied(
                "O painel de documentos fiscais só está disponível dentro de um tenant."
            )

    def _base_queryset(self):
        self._validar_tenant()
        # A separação é garantida pelo schema activo do django-tenants.
        return DocumentoFiscal.objects.select_related(
            "cliente", "usuario_criacao", "usuario_confirmacao"
        )

    @staticmethod
    def _texto_erro(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            return "; ".join(exc.messages)
        return str(exc)

    def _url_retorno(self, request):
        params = {}
        for chave in ("estado_filtro", "q_filtro", "tipo_filtro"):
            valor = (request.POST.get(chave) or "").strip()
            if valor:
                nome = {"estado_filtro": "estado", "q_filtro": "q", "tipo_filtro": "tipo"}[chave]
                params[nome] = valor
        url = reverse("vendas:status_documento")
        return f"{url}?{urlencode(params)}" if params else url

    def get(self, request, *args, **kwargs):
        contexto = self._contexto(request)
        return render(request, self.template_name, contexto)

    def _contexto(self, request):
        qs_base = self._base_queryset().order_by("-data_emissao", "-numero")
        q = (request.GET.get("q") or "").strip()
        tipo = (request.GET.get("tipo") or "").strip().upper()
        estado = (request.GET.get("estado") or "").strip().lower()
        codigos_estado = {codigo for codigo, *_ in self.ESTADOS}

        # Os cartões mostram a distribuição global por estado no tenant.
        contagens_qs = (
            self._base_queryset()
            .values("status")
            .order_by()
            .annotate(total=Count("pk"))
        )
        contagens = {linha["status"]: linha["total"] for linha in contagens_qs}
        total_global = sum(contagens.values())

        if q:
            qs_base = qs_base.filter(
                Q(numero_documento__icontains=q)
                | Q(cliente_nome__icontains=q)
                | Q(cliente_nif__icontains=q)
                | Q(atcud__icontains=q)
            )
        if tipo:
            qs_base = qs_base.filter(tipo_documento=tipo)
        estado_valido = estado in codigos_estado
        if estado_valido:
            qs_base = qs_base.filter(status=estado)

        paginator = Paginator(qs_base, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get("page"))
        for documento in page_obj.object_list:
            documento.status_actions = self._acoes_disponiveis(documento.status)

        cards = []
        for codigo, label, descricao, icone, cor in self.ESTADOS:
            params = {"estado": codigo}
            if q:
                params["q"] = q
            if tipo:
                params["tipo"] = tipo
            cards.append({
                "codigo": codigo,
                "label": label,
                "descricao": descricao,
                "icone": icone,
                "cor": cor,
                "quantidade": contagens.get(codigo, 0),
                "url": f"{reverse('vendas:status_documento')}?{urlencode(params)}",
                "seleccionado": estado_valido and estado == codigo,
            })

        params_pag = {"estado": estado, "q": q, "tipo": tipo}
        params_pag = {k: v for k, v in params_pag.items() if v}
        query_base = urlencode(params_pag)
        anterior_url = None
        seguinte_url = None
        if page_obj.has_previous():
            anterior_url = f"?{query_base + '&' if query_base else ''}page={page_obj.previous_page_number()}"
        if page_obj.has_next():
            seguinte_url = f"?{query_base + '&' if query_base else ''}page={page_obj.next_page_number()}"

        return {
            "cards_estado": cards,
            "total_global": total_global,
            "total_filtrado": paginator.count,
            "documentos": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": paginator.num_pages > 1,
            "q": q,
            "tipo": tipo,
            "estado": estado if estado_valido else "",
            "estado_choices": [(c, l) for c, l, *_ in self.ESTADOS],
            "tipo_choices": DocumentoFiscal.TIPO_DOCUMENTO_CHOICES,
            "formas_pagamento": self.FORMAS_PAGAMENTO,
            "anterior_url": anterior_url,
            "seguinte_url": seguinte_url,
            "schema_actual": getattr(connection, "schema_name", ""),
        }

    @staticmethod
    def _acoes_disponiveis(status):
        acoes = {
            "draft": [
                {"valor": "confirmar", "rotulo": "Confirmar", "classe": "blue", "confirmar": "Confirmar este documento? A confirmação exige que os dados fiscais e a assinatura estejam configurados."},
                {"valor": "cancelar_rascunho", "rotulo": "Cancelar rascunho", "classe": "red", "confirmar": "Cancelar este rascunho?"},
            ],
            "confirmed": [
                {"valor": "lancar", "rotulo": "Lançar", "classe": "indigo"},
                {"valor": "pagar", "rotulo": "Marcar pago", "classe": "green"},
                {"valor": "cancelar_I", "rotulo": "Cancelar (I)", "classe": "red", "motivo": True},
                {"valor": "cancelar_N", "rotulo": "Cancelar (N)", "classe": "red", "motivo": True},
                {"valor": "rectificar_NC", "rotulo": "Criar NC", "classe": "purple", "motivo": True},
                {"valor": "rectificar_ND", "rotulo": "Criar ND", "classe": "purple", "motivo": True},
                {"valor": "rectificar_RE", "rotulo": "Criar RE", "classe": "purple", "motivo": True},
            ],
            "posted": [
                {"valor": "pagar", "rotulo": "Marcar pago", "classe": "green"},
                {"valor": "cancelar_I", "rotulo": "Cancelar (I)", "classe": "red", "motivo": True},
                {"valor": "cancelar_N", "rotulo": "Cancelar (N)", "classe": "red", "motivo": True},
                {"valor": "rectificar_NC", "rotulo": "Criar NC", "classe": "purple", "motivo": True},
                {"valor": "rectificar_ND", "rotulo": "Criar ND", "classe": "purple", "motivo": True},
                {"valor": "rectificar_RE", "rotulo": "Criar RE", "classe": "purple", "motivo": True},
            ],
            "paid": [
                {"valor": "rectificar_NC", "rotulo": "Criar NC", "classe": "purple", "motivo": True},
                {"valor": "rectificar_ND", "rotulo": "Criar ND", "classe": "purple", "motivo": True},
                {"valor": "rectificar_RE", "rotulo": "Criar RE", "classe": "purple", "motivo": True},
            ],
        }
        return acoes.get(status, [])

    @staticmethod
    def _validar_jws_documental(documento):
        """Não confirma um documento cuja JWS não contenha a estrutura AGT exigida."""
        from apps.fiscal.models import AssinaturaDigital
        from apps.fiscal.services.assinatura_service import verificar_jws_rs256

        config = AssinaturaDigital.get_solo()
        chave_publica = (config.chave_contribuinte_publica or "").strip()
        if not chave_publica:
            raise ValidationError(
                "A confirmação foi revertida: não existe chave pública do contribuinte para validar a assinatura."
            )

        try:
            payload = verificar_jws_rs256(documento.assinatura_digital, chave_publica)
        except Exception as exc:
            raise ValidationError(
                "A confirmação foi revertida: a assinatura JWS não pode ser verificada com a chave pública configurada."
            ) from exc

        if not isinstance(payload, dict):
            raise ValidationError(
                "A confirmação foi revertida: o conteúdo assinado não é um objecto JSON."
            )

        campos_obrigatorios = {
            "documentNo", "taxRegistrationNumber", "documentType", "documentDate",
            "customerTaxID", "customerCountry", "companyName", "documentTotals",
        }
        em_falta = sorted(campos_obrigatorios.difference(payload))
        if em_falta:
            raise ValidationError(
                "A confirmação foi revertida: a assinatura documental não contém os campos exigidos pela AGT: "
                + ", ".join(em_falta)
                + ". Corrige a montagem da assinatura em DocumentoFiscal._aplicar_assinatura_digital()."
            )

        totais = payload.get("documentTotals")
        if not isinstance(totais, dict) or not {"netTotal", "taxPayable", "grossTotal"}.issubset(totais):
            raise ValidationError(
                "A confirmação foi revertida: documentTotals precisa de conter netTotal, taxPayable e grossTotal."
            )
        if str(payload.get("documentNo")) != str(documento.numero_documento):
            raise ValidationError(
                "A confirmação foi revertida: o número dentro da assinatura não coincide com o documento."
            )

    def post(self, request, *args, **kwargs):
        # A autorização já foi verificada por PermissaoAcaoMixin.dispatch()
        # usando a acção personalizada definida nesta view:
        # acao_requerida = "acessar_documentos".
        # Não voltar a exigir fiscal.change_documentofiscal, pois isso
        # reintroduziria a permissão Django padrão que o projecto substituiu.
        acao = (request.POST.get("acao") or "").strip()
        documento_id = request.POST.get("documento_id")
        if not documento_id or not acao:
            messages.error(request, "Não foi possível identificar o documento ou a operação.")
            return redirect(self._url_retorno(request))

        try:
            with transaction.atomic():
                self._validar_tenant()
                documento = DocumentoFiscal.objects.select_for_update().get(pk=documento_id)
                estado_anterior = documento.status

                if acao == "confirmar":
                    documento.confirmar_documento(request.user)
                    documento.refresh_from_db()
                    # O model antigo captura a falha da assinatura e pode continuar.
                    # Aqui não permitimos que um estado confirmado fique sem assinatura/hash.
                    if not documento.hash_documento or not documento.assinatura_digital:
                        raise ValidationError(
                            "A confirmação foi revertida: falta hash ou assinatura digital. "
                            "Verifica a configuração da chave do contribuinte e os logs fiscais."
                        )
                    self._validar_jws_documental(documento)
                    mensagem = "Documento confirmado internamente. Isto não significa que a AGT já o validou."

                elif acao == "lancar":
                    documento.lancar_documento(request.user)
                    mensagem = "Documento lançado com sucesso."

                elif acao == "pagar":
                    forma = (request.POST.get("forma_pagamento") or "").strip()
                    formas_validas = {codigo for codigo, _ in self.FORMAS_PAGAMENTO}
                    if forma not in formas_validas:
                        raise ValidationError("Selecciona uma forma de pagamento válida antes de marcar como pago.")
                    referencia = (request.POST.get("referencia_pagamento") or "").strip()
                    dados_pagamento = {
                        "forma_pagamento": forma,
                        "referencia": referencia,
                        "data_registo": timezone.now().isoformat(),
                        "registado_por": request.user.get_username(),
                        "origem": "painel_status_documento",
                    }
                    documento.forma_pagamento = forma
                    documento.registar_pagamento(request.user, dados_pagamento=dados_pagamento)
                    mensagem = "Documento marcado como pago. Confirma que o pagamento foi efectivamente recebido."

                elif acao == "cancelar_rascunho":
                    documento.cancelar_documento(
                        request.user,
                        motivo_codigo="N",
                        motivo_texto="Rascunho cancelado no painel de estados.",
                    )
                    mensagem = "Rascunho cancelado; o registo foi preservado."

                elif acao in {"cancelar_I", "cancelar_N"}:
                    codigo = acao.rsplit("_", 1)[1]
                    motivo = (request.POST.get("motivo") or "").strip()
                    if not motivo:
                        raise ValidationError("Indica o motivo do cancelamento.")
                    documento.cancelar_documento(
                        request.user, motivo_codigo=codigo, motivo_texto=motivo
                    )
                    mensagem = "Documento cancelado; o histórico foi preservado."

                elif acao in {f"rectificar_{tipo}" for tipo in self.TIPOS_RECTIFICATIVO}:
                    tipo_rectificativo = acao.rsplit("_", 1)[1]
                    motivo = (request.POST.get("motivo") or "").strip()
                    if not motivo:
                        raise ValidationError("Indica o motivo da rectificação.")
                    correctivo = documento.rectificar_documento(
                        request.user,
                        tipo_rectificativo=tipo_rectificativo,
                        motivo=motivo,
                    )
                    mensagem = (
                        f"Documento de origem marcado como rectificado. "
                        f"Foi criado o rascunho {correctivo.numero_documento} ({tipo_rectificativo})."
                    )

                else:
                    raise ValidationError("Operação de transição desconhecida.")

                logger.info(
                    "Transição de documento fiscal via painel: schema=%s doc=%s estado=%s→%s acao=%s user=%s",
                    connection.schema_name,
                    documento_id,
                    estado_anterior,
                    getattr(documento, "status", ""),
                    acao,
                    request.user.get_username(),
                )
                messages.success(request, mensagem)

        except DocumentoFiscal.DoesNotExist:
            messages.error(request, "O documento não existe neste tenant.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, self._texto_erro(exc))
        except Exception:
            logger.exception(
                "Erro ao alterar estado documental: schema=%s doc=%s acao=%s",
                getattr(connection, "schema_name", None), documento_id, acao,
            )
            messages.error(request, "Ocorreu um erro ao executar a operação. Consulta os logs fiscais para mais detalhes.")

        return redirect(self._url_retorno(request))

# Auditoria Fase 1 - Inspector AGT

Raiz analisada: `apps`

## Resumo

| Categoria | Ocorrencias | Ficheiros |
|---|---|---|
| A1_transporte_directo: Chamadas HTTP directas (candidatas a contornar o AGTClient) | 15 | 11 |
| A2_registarFactura: Referencias a registarFactura | 32 | 10 |
| A3_agtclient: AGTClient e o seu ponto central _chamar | 21 | 5 |
| A4_inspector_actual: Uso actual do Inspector (PayloadInspectorService / PayloadAGT) | 47 | 7 |
| B1_emissao_documento: Criacao/emissao de DocumentoFiscal | 9 | 3 |
| B2_transicoes_estado: Transicoes de estado (draft/confirmed/posted/paid) | 21 | 13 |
| B3_signals: Signals (pre_save/post_save/receiver) | 41 | 12 |
| B4_bypass_do_save: Escritas que nao disparam signals (.update / bulk_update / bulk_create) | 28 | 17 |
| C1_celery: Tarefas Celery e disparos | 67 | 22 |
| C2_polling: Polling / obterEstado | 30 | 5 |
| C3_comandos: Management commands relacionados | 44 | 22 |
| D1_credenciais_risco: Locais onde cabecalhos/credenciais podem ser persistidos (rever manualmente) | 54 | 16 |

## Riscos sinalizados (rever primeiro)

- HTTP directo fora do AGTClient: apps\analytics\utils.py:32 -> response = requests.get(url, timeout=2)
- HTTP directo fora do AGTClient: apps\analytics\utils.py:236 -> response = requests.get(url, timeout=5)
- HTTP directo fora do AGTClient: apps\core\management\commands\test_whatsapp_config.py:34 -> response = requests.get(debug_url, timeout=10)
- HTTP directo fora do AGTClient: apps\core\services\captcha_service.py:54 -> resp = requests.post(
- HTTP directo fora do AGTClient: apps\core\utils.py:73 -> response_upload = requests.post(
- HTTP directo fora do AGTClient: apps\core\utils.py:97 -> response_send = requests.post(self.url_base, headers=self.headers, json=payload, timeout=30)
- HTTP directo fora do AGTClient: apps\core_tenants\utils.py:73 -> response_upload = requests.post(
- HTTP directo fora do AGTClient: apps\core_tenants\utils.py:97 -> response_send = requests.post(self.url_base, headers=self.headers, json=payload, timeout=30)
- HTTP directo fora do AGTClient: apps\fiscal\services\pdf_agt_service.py:695 -> resposta = requests.get(str(url), timeout=(2, 5), stream=True)
- HTTP directo fora do AGTClient: apps\fiscal\services\pdf_agt_service.py:2156 -> r = requests.get(foto.url, timeout=5)
- HTTP directo fora do AGTClient: apps\fiscal\services\submissao_fatura_service.py:120 -> response = requests.post(
- HTTP directo fora do AGTClient: apps\fiscal\services\whatsapp_service.py:55 -> response = requests.post(self.url, json=payload, headers=headers, timeout=20)
- HTTP directo fora do AGTClient: apps\integracoes\services\cliente.py:104 -> resp = requests.request(metodo, url, headers=headers, json=json_body, data=data, params=params,
- HTTP directo fora do AGTClient: apps\integracoes\services\correios.py:19 -> response = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/")
- HTTP directo fora do AGTClient: apps\produtos\views.py:1822 -> resp = requests.get(url_logo, timeout=5)
- registarFactura sem Inspector no mesmo ficheiro: apps\fiscal\services\agt_payload_builder.py
- registarFactura sem Inspector no mesmo ficheiro: apps\fiscal\services\assinatura_service.py
- registarFactura sem Inspector no mesmo ficheiro: apps\fiscal\services\numero_documento_agt.py
- registarFactura sem Inspector no mesmo ficheiro: apps\fiscal\tasks.py
- registarFactura sem Inspector no mesmo ficheiro: apps\vendas\models.py
- Escrita sem signals (pode escapar ao listener): apps\analytics\views.py:272
- Escrita sem signals (pode escapar ao listener): apps\analytics\views.py:279
- Escrita sem signals (pode escapar ao listener): apps\core\provisionamento.py:49
- Escrita sem signals (pode escapar ao listener): apps\estoque\models.py:537
- Escrita sem signals (pode escapar ao listener): apps\estoque\models.py:539
- Escrita sem signals (pode escapar ao listener): apps\financeiro\management\commands\setup_formas_pagamento.py:24
- Escrita sem signals (pode escapar ao listener): apps\financeiro\views.py:319
- Escrita sem signals (pode escapar ao listener): apps\fiscal\models.py:1872
- Escrita sem signals (pode escapar ao listener): apps\fiscal\services\serie_service.py:31
- Escrita sem signals (pode escapar ao listener): apps\funcionarios\motor_salarial.py:437
- Escrita sem signals (pode escapar ao listener): apps\funcionarios\views_recibo.py:506
- Escrita sem signals (pode escapar ao listener): apps\produtos\management\commands\setup_produtos_lotes.py:189
- Escrita sem signals (pode escapar ao listener): apps\produtos\management\commands\setup_produtos_lotes.py:192
- Escrita sem signals (pode escapar ao listener): apps\produtos\management\commands\setup_produtos_lotes.py:196
- Escrita sem signals (pode escapar ao listener): apps\produtos\views.py:518
- Escrita sem signals (pode escapar ao listener): apps\produtos\views.py:1428
- Escrita sem signals (pode escapar ao listener): apps\produtos\views.py:1454
- Escrita sem signals (pode escapar ao listener): apps\servicos\management\commands\setup_servicos.py:98
- Escrita sem signals (pode escapar ao listener): apps\servicos\tasks.py:183
- Escrita sem signals (pode escapar ao listener): apps\site\views.py:2165
- Escrita sem signals (pode escapar ao listener): apps\vendas\fiscal_bridge.py:331
- Escrita sem signals (pode escapar ao listener): apps\vendas\v_views.py:361
- Escrita sem signals (pode escapar ao listener): apps\vendas\v_views.py:582
- Escrita sem signals (pode escapar ao listener): apps\vendas\v_views.py:621
- Escrita sem signals (pode escapar ao listener): apps\vendas\v_views.py:2071
- Escrita sem signals (pode escapar ao listener): apps\vendas\views.py:513
- Escrita sem signals (pode escapar ao listener): apps\vendas\views.py:521
- Escrita sem signals (pode escapar ao listener): apps\vendas\views.py:525

## Detalhe por categoria

### A1_transporte_directo - Chamadas HTTP directas (candidatas a contornar o AGTClient)

**apps\analytics\utils.py**
- L32: `response = requests.get(url, timeout=2)`
- L236: `response = requests.get(url, timeout=5)`

**apps\core\management\commands\test_whatsapp_config.py**
- L34: `response = requests.get(debug_url, timeout=10)`

**apps\core\services\captcha_service.py**
- L54: `resp = requests.post(`

**apps\core\utils.py**
- L73: `response_upload = requests.post(`
- L97: `response_send = requests.post(self.url_base, headers=self.headers, json=payload, timeout=30)`

**apps\core_tenants\utils.py**
- L73: `response_upload = requests.post(`
- L97: `response_send = requests.post(self.url_base, headers=self.headers, json=payload, timeout=30)`

**apps\fiscal\services\pdf_agt_service.py**
- L695: `resposta = requests.get(str(url), timeout=(2, 5), stream=True)`
- L2156: `r = requests.get(foto.url, timeout=5)`

**apps\fiscal\services\submissao_fatura_service.py**
- L120: `response = requests.post(`

**apps\fiscal\services\whatsapp_service.py**
- L55: `response = requests.post(self.url, json=payload, headers=headers, timeout=20)`

**apps\integracoes\services\cliente.py**
- L104: `resp = requests.request(metodo, url, headers=headers, json=json_body, data=data, params=params,`

**apps\integracoes\services\correios.py**
- L19: `response = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/")`

**apps\produtos\views.py**
- L1822: `resp = requests.get(url_logo, timeout=5)`

### A2_registarFactura - Referencias a registarFactura

**apps\fiscal\models.py**
- L783: `"Obrigatório no payload registarFactura (Decreto 683/25, Anexo I)."`

**apps\fiscal\services\agt_client.py**
- L10: `- Capturar o envelope de registarFactura no Inspector antes de qualquer envio.`
- L68: `"registarFactura": {"schema": "2.0", "timeout": (5, 45), "retry": False},`
- L186: `def _validar_envelope_registar_factura(self, payload: Dict[str, Any]) -> None:`
- L189: `raise FiscalServiceError("O payload registarFactura tem de ser um objecto JSON.")`
- L204: `"Envelope registarFactura incompleto; falta(m): " + ", ".join(em_falta)`
- L217: `"registarFactura exige uma lista não vazia no campo documents."`
- L246: `"""Envia um pedido. Captura registarFactura uma única vez antes do HTTP."""`
- L258: `if servico == "registarFactura":`
- L265: `"registarFactura exige um envelope com uma lista documents não vazia."`
- L276: `"Falha ao capturar envelope registarFactura. Pedido bloqueado antes do HTTP."`
- L285: `self._validar_envelope_registar_factura(payload)`
- L648: `return self._chamar("registarFactura", payload)`
- L650: `def registar_factura(`
- L660: `Não há retry automático para registarFactura.`
- L663: `raise FiscalServiceError("registarFactura exige uma lista de documentos não vazia.")`
- L682: `"registarFactura", config, assinatura_campos, extra`
- L684: `data = self._chamar("registarFactura", payload)`
- L695: `servico="registarFactura",`

**apps\fiscal\services\agt_payload_builder.py**
- L2: `"""Construção explícita do envelope ``registarFactura`` para AGT v2.0.`
- L629: `"""Monta um envelope ``registarFactura`` v2.0 para DocumentoFiscal emitido."""`
- L653: `"pelo serviço AGT registarFactura v2.0."`
- L655: `raise AGTPayloadBuildError(f"Tipo de documento {tipo!r} não suportado por registarFactura v2.0.")`

**apps\fiscal\services\assinatura_service.py**
- L285: `registarFactura; taxRegistrationNumber+requestID em obterEstado).`

**apps\fiscal\services\numero_documento_agt.py**
- L6: `Para FP/DT, que não integram a lista documentType do endpoint AGT registarFactura,`

**apps\fiscal\services\payload_inspector.py**
- L48: `raise ValueError("O envelope registarFactura tem de conter 'documents' como lista.")`

**apps\fiscal\services\submissao_documento_agt.py**
- L22: `meta = servicos.get("registarFactura", {})`

**apps\fiscal\services\submissao_fatura_service.py**
- L3: `Serviço de submissão de facturas à API AGT — endpoint /registarFactura.`
- L44: `Submete documentos fiscais à API AGT (/registarFactura).`

**apps\fiscal\tasks.py**
- L41: `Submete um DocumentoFiscal à API AGT (/registarFactura).`

**apps\vendas\models.py**
- L422: `help_text="Obrigatório no payload registarFactura. Use TB para produtos, SE para serviços."`
- L2063: `"Obrigatório no payload registarFactura (referenceInfo.reference)."`

### A3_agtclient - AGTClient e o seu ponto central _chamar

**apps\fiscal\services\agt_client.py**
- L62: `class AGTClient:`
- L245: `def _chamar(self, servico: str, payload: Dict[str, Any]) -> Dict[str, Any]:`
- L590: `data = self._chamar("listarSeries", payload)`
- L632: `data = self._chamar("solicitarSerie", payload)`
- L648: `return self._chamar("registarFactura", payload)`
- L684: `data = self._chamar("registarFactura", payload)`
- L715: `data = self._chamar("obterEstado", payload)`

**apps\fiscal\services\polling_service.py**
- L5: `A comunicação HTTP está no AGTClient. Este serviço só interpreta a resposta e`
- L28: `from apps.fiscal.services.agt_client import AGTClient, AGTError`
- L37: `def __init__(self, client: AGTClient = None):`
- L38: `self.client = client or AGTClient()`

**apps\fiscal\services\serie_fiscal_service.py**
- L13: `está no AGTClient; este serviço só persiste o resultado em SerieFiscalAGT /`
- L41: `from apps.fiscal.services.agt_client import AGTClient`
- L52: `def __init__(self, client: Optional[AGTClient] = None):`
- L54: `self.client = client or AGTClient()`

**apps\fiscal\services\submissao_documento_agt.py**
- L3: `A captura do JSON ocorre no ponto único de transporte AGTClient._chamar(), não`
- L33: ```cliente_agt`` é a instância AGTClient configurada no projecto. O serviço`

**apps\fiscal\services\submissao_fatura_service.py**
- L6: `jwsSignature, timeouts) está no AGTClient. Este serviço:`
- L29: `from apps.fiscal.services.agt_client import AGTClient, AGTError`
- L48: `def __init__(self, client: AGTClient = None):`
- L49: `self.client = client or AGTClient()`

### A4_inspector_actual - Uso actual do Inspector (PayloadInspectorService / PayloadAGT)

**apps\fiscal\models.py**
- L1991: `def marcar_enviado(self, usuario):`
- L2014: `from .models_payload_agt import PayloadAGT`

**apps\fiscal\models_payload_agt.py**
- L4: `Importar PayloadAGT no final de apps/fiscal/models.py para o Django registar`
- L13: `class PayloadAGT(TimeStampedModel):`

**apps\fiscal\payload_views.py**
- L15: `from apps.fiscal.models_payload_agt import PayloadAGT`
- L53: `model = PayloadAGT`
- L60: `qs = PayloadAGT.objects.all().order_by("-created_at", "-pk")`
- L71: `if status and status in dict(PayloadAGT.STATUS_CHOICES):`
- L73: `if ambiente and ambiente in dict(PayloadAGT.AMBIENTE_CHOICES):`
- L81: `context["status_choices"] = PayloadAGT.STATUS_CHOICES`
- L82: `context["ambiente_choices"] = PayloadAGT.AMBIENTE_CHOICES`
- L83: `context["total_payloads"] = PayloadAGT.objects.count()`
- L95: `model = PayloadAGT`
- L101: `return PayloadAGT.objects.all()`
- L116: `registo = PayloadAGT.objects.filter(pk=pk).first()`

**apps\fiscal\services\agt_client.py**
- L34: `from apps.fiscal.services.payload_inspector import PayloadInspectorService`
- L269: `captura_payload = PayloadInspectorService.registar_payload(`
- L288: `PayloadInspectorService.marcar_falha(`
- L304: `PayloadInspectorService.marcar_falha(`
- L322: `PayloadInspectorService.marcar_enviado(captura_payload)`
- L328: `PayloadInspectorService.marcar_falha(`
- L355: `PayloadInspectorService.marcar_falha(`
- L397: `PayloadInspectorService.registar_resposta(`

**apps\fiscal\services\payload_inspector.py**
- L21: `from apps.fiscal.models_payload_agt import PayloadAGT`
- L98: `class PayloadInspectorService:`
- L107: `def registar_payload(payload: dict, endpoint: str = "", ambiente: str | None = None) -> PayloadAGT:`
- L117: `existente = PayloadAGT.objects.filter(submission_uuid=submission_uuid).order_by("pk").first()`
- L125: `registo = PayloadAGT.objects.create(`
- L136: `status=PayloadAGT.STATUS_PREPARADO,`
- L166: `def marcar_enviado(registo: PayloadAGT) -> PayloadAGT:`
- L167: `registo.status = PayloadAGT.STATUS_ENVIADO`
- L175: `def registar_resposta(registo: PayloadAGT, response) -> PayloadAGT:`
- L191: `PayloadAGT.STATUS_RESPOSTA if 200 <= status_code < 400 else PayloadAGT.STATUS_FALHOU`
- L204: `def marcar_falha(registo: PayloadAGT, erro: object, *, pedido_enviado: bool = False) -> PayloadAGT:`
- L206: `registo.status = PayloadAGT.STATUS_FALHOU if pedido_enviado else PayloadAGT.STATUS_NAO_ENVIADO`
- L216: `registo = PayloadAGT.objects.create(`
- L223: `status=PayloadAGT.STATUS_ERRO_PREPARACAO,`

**apps\fiscal\services\submissao_documento_agt.py**
- L14: `from apps.fiscal.services.payload_inspector import PayloadInspectorService`
- L43: `PayloadInspectorService.registar_erro_preparacao(`

**apps\fiscal\services\submissao_fatura_service.py**
- L60: `from apps.fiscal.services.payload_inspector import PayloadInspectorService`
- L98: `captura = PayloadInspectorService.registar_payload(`
- L114: `PayloadInspectorService.marcar_enviado(captura)`
- L129: `PayloadInspectorService.registar_resposta(captura, response)`
- L138: `PayloadInspectorService.marcar_falha(captura, exc, pedido_enviado=tentativa_http)`
- L144: `PayloadInspectorService.registar_erro_preparacao(`
- L162: `PayloadInspectorService.marcar_falha(captura, exc, pedido_enviado=tentativa_http)`
- L167: `PayloadInspectorService.registar_erro_preparacao(`

### B1_emissao_documento - Criacao/emissao de DocumentoFiscal

**apps\fiscal\services\documento_fiscal_service.py**
- L364: `def criar_documento(`

**apps\vendas\fiscal_bridge.py**
- L370: `documento = DocumentoFiscalService.criar_documento(`

**apps\vendas\models.py**
- L323: `documento = service.criar_documento(`
- L1260: `documento = service.criar_documento(`
- L1406: `documento = service.criar_documento(`
- L1787: `documento = service.criar_documento(`
- L1944: `documento = service.criar_documento(`
- L2170: `documento = service.criar_documento(`
- L2437: `documento = service.criar_documento(`

### B2_transicoes_estado - Transicoes de estado (draft/confirmed/posted/paid)

**apps\fiscal\api_viewsets.py**
- L291: `serializer.save(empresa=empresa, usuario_criacao=self.request.user, status="draft")`

**apps\fiscal\models.py**
- L1236: `status='confirmed',`
- L1407: `self.status = 'confirmed'`
- L1416: `status='confirmed'`
- L1439: `self.status = 'posted'`
- L1456: `self.status = 'paid'`
- L1554: `status='draft',`

**apps\fiscal\services\assinatura_service.py**
- L345: `docs = DocumentoFiscal.objects.filter(status='confirmed').order_by(`

**apps\fiscal\services\documento_fiscal_service.py**
- L433: `status="confirmed",`

**apps\fiscal\services\polling_service.py**
- L85: `doc.status = "posted"`

**apps\fiscal\services\saft_xml_generator_service.py**
- L438: `tipo_documento__in={"NC", "ND"}, status="confirmed"`
- L441: `status="confirmed"`

**apps\fiscal\views.py**
- L2601: `status='draft',`

**apps\licenca\admin.py**
- L53: `rows_updated = queryset.update(status='pago', pago_em=timezone.now())`

**apps\parceiros\admin.py**
- L133: `queryset.update(status='suspensa')`
- L138: `queryset.update(status='expirada')`

**apps\servicos\tasks.py**
- L155: `).update(status="pendente")`

**apps\site\admin.py**
- L120: `queryset.filter(status='pendente').update(status='confirmado', processado_por=request.user)`
- L125: `queryset.update(status='entregue')`

**apps\vendas\v_views.py**
- L2360: `status='emitido'`

**apps\vendas\views.py**
- L2376: `forma_pagamento=forma, valor_pago=valor_pendente, status='emitido',`

### B3_signals - Signals (pre_save/post_save/receiver)

**apps\analytics\signals.py**
- L2: `from django.db.models.signals import post_save, post_delete`
- L22: `@receiver(user_logged_in)`
- L36: `@receiver(post_save)`
- L76: `@receiver(post_delete)`

**apps\auditoria_publica\signals.py**
- L2: `from django.db.models.signals import post_save`
- L13: `@receiver(post_save, sender=Empresa)`
- L35: `@receiver(post_save, sender=Licenca)`

**apps\core\signals.py**
- L12: `@receiver(user_logged_in)`

**apps\core\views.py**
- L317: `@receiver(user_logged_in)`

**apps\core_tenants\signals.py**
- L15: `@receiver(user_logged_in)`

**apps\empresas\signals.py**
- L5: `from django.db.models.signals import post_save`
- L25: `@receiver(post_save, sender=Empresa)`
- L32: `@receiver(post_schema_sync)`

**apps\fiscal\signals.py**
- L18: `from django.db.models.signals import post_save, pre_save, post_delete, pre_delete`
- L121: `@receiver(post_save, sender='vendas.Venda')`
- L122: `@receiver(post_save, sender='vendas.FaturaCredito')`
- L123: `@receiver(post_save, sender='vendas.NotaCredito')`
- L124: `@receiver(post_save, sender='vendas.NotaDebito')`
- L125: `@receiver(post_save, sender='vendas.Recibo')`
- L136: `@receiver(post_save, sender=AssinaturaDigital)`
- L148: `@receiver(pre_save, sender=RetencaoFonte)`
- L160: `@receiver(post_save, sender=RetencaoFonte)`
- L180: `@receiver(post_save, sender=TaxaIVAAGT)`
- L191: `@receiver(post_save, sender=TaxaIVAAGT)`
- L205: `@receiver(pre_delete, sender=TaxaIVAAGT)`
- L234: `@receiver(post_save)`
- L247: `@receiver(pre_delete)`
- L268: `@receiver(evento_fiscal)`

**apps\funcionarios\signals.py**
- L5: `from django.db.models.signals import post_save`
- L17: `@receiver(post_save, sender="funcionarios.Funcionario",`
- L40: `@receiver(post_schema_sync, sender=TenantMixin,`

**apps\produtos\signals.py**
- L3: `from django.db.models.signals import post_save, post_delete`
- L8: `@receiver(post_save, sender=Lote)`
- L9: `@receiver(post_delete, sender=Lote)`

**apps\servicos\signals.py**
- L2: `from django.db.models.signals import post_save`
- L8: `@receiver(post_save, sender=AgendamentoServico)`

**apps\vendas\models.py**
- L8: `from django.db.models.signals import post_save`
- L1038: `@receiver(post_save, sender=MetaVenda)`

**apps\vendas\signals.py**
- L2: `from django.db.models.signals import post_save`
- L13: `@receiver(post_save, sender=Venda)`
- L27: `@receiver(post_save, sender=Venda)`

### B4_bypass_do_save - Escritas que nao disparam signals (.update / bulk_update / bulk_create)

**apps\analytics\views.py**
- L272: `DashboardPersonalizado.objects.filter(usuario=self.request.user, padrao=True).update(padrao=False)`
- L279: `if form.cleaned_data.get("padrao"): DashboardPersonalizado.objects.filter(usuario=self.request.user,padrao=True).exclude(pk=self.object.pk).`

**apps\core\provisionamento.py**
- L49: `Funcionario.objects.filter(pk=funcionario.pk).update(`

**apps\estoque\models.py**
- L537: `cls.objects.bulk_create(novos)`
- L539: `cls.objects.filter(pk__in=obsoletos).update(`

**apps\financeiro\management\commands\setup_formas_pagamento.py**
- L24: `FormaPagamento.objects.filter(tipo__in=tipos).update(ativa=True)`

**apps\financeiro\views.py**
- L319: `FormaPagamento.objects.filter(tipo=tipo).update(ativa=(acao == 'ativar'))`

**apps\fiscal\models.py**
- L1872: `DocumentoFiscal.objects.filter(pk=documento.pk).update(`

**apps\fiscal\services\serie_service.py**
- L31: `ContadorDocumento.objects.filter(id=contador.id).update(sequencia=F('sequencia') + 1)`

**apps\funcionarios\motor_salarial.py**
- L437: `LinhaRecibo.objects.bulk_create([`

**apps\funcionarios\views_recibo.py**
- L506: `Rubrica.objects.filter(pk=pk).update(ordem_calculo=pos * 10)`

**apps\produtos\management\commands\setup_produtos_lotes.py**
- L189: `Produto.objects.bulk_create([p for p, _ in specs], batch_size=500)`
- L192: `Lote.objects.bulk_create(lotes_objs, batch_size=1000)`
- L196: `MovimentacaoEstoque.objects.bulk_create([`

**apps\produtos\views.py**
- L518: `updated = Produto.objects.filter(ativo=True).update(ativo=False)`
- L1428: `modelo.objects.bulk_create(list(novos.values()))`
- L1454: `TaxaIVAAGT.objects.bulk_create(novas)`

**apps\servicos\management\commands\setup_servicos.py**
- L98: `Servico.objects.bulk_create(novos, batch_size=500)`

**apps\servicos\tasks.py**
- L183: `NotificacaoAgendamento.objects.filter(pk=pk, status="processando").update(`

**apps\site\views.py**
- L2165: `Secao.objects.filter(pk=pk, pagina=pagina).update(ordem=ordem)`

**apps\vendas\fiscal_bridge.py**
- L331: `model.objects.filter(pk=origem.pk).update(**updates)`

**apps\vendas\v_views.py**
- L361: `Produto.objects.filter(pk=l['produto'].pk).update(estoque_atual=F('estoque_atual') - qtd)`
- L582: `Produto.objects.filter(pk=p.pk).update(estoque_atual=F('estoque_atual') - qtd)`
- L621: `Produto.objects.filter(pk=p.pk).update(estoque_atual=F('estoque_atual') - qtd)`
- L2071: `Produto.objects.filter(id=item['produto_id']).update(estoque_atual=F('estoque_atual') - item['quantidade'])`

**apps\vendas\views.py**
- L513: `Produto.objects.filter(pk=l['produto'].pk).update(estoque_atual=F('estoque_atual') - qtd)`
- L521: `Produto.objects.filter(pk=p.pk).update(estoque_atual=F('estoque_atual') - quantidade)`
- L525: `Produto.objects.filter(pk=produto_id).update(estoque_atual=F('estoque_atual') + quantidade)`

### C1_celery - Tarefas Celery e disparos

**apps\auditoria_publica\signals.py**
- L32: `transaction.on_commit(gravar_log)`
- L57: `transaction.on_commit(gravar_log)`

**apps\clientes\chat_views.py**
- L206: `transaction.on_commit(lambda: _enfileirar_alerta_chat(schema_name, msg.pk))`
- L213: `notificar_mensagem_chat.delay(schema_name, mensagem_id)`

**apps\clientes\tasks.py**
- L24: `@shared_task(bind=True, name="clientes.notificar_mensagem_chat", max_retries=3, default_retry_delay=60, ignore_result=True)`
- L115: `@shared_task(name="clientes.reenfileirar_notificacoes_chat_global", ignore_result=True)`
- L135: `notificar_mensagem_chat.delay(schema_name, mensagem_id)`

**apps\comunicacao\tasks.py**
- L12: `@shared_task(name="comunicacao.notificar_mensagem_chat", ignore_result=True)`

**apps\comunicacao\views.py**
- L170: `transaction.on_commit(lambda: _enfileirar_alerta_chat(schema_name, msg.pk))`
- L177: `notificar_mensagem_chat.delay(schema_name, mensagem_id)`

**apps\configuracoes\tasks.py**
- L10: `@shared_task(bind=True, name="configuracoes.backup_automatico_diario", autoretry_for=(), max_retries=0)`

**apps\empresas\signals.py**
- L29: `transaction.on_commit(lambda: _sincronizar(instance))`

**apps\estoque\tasks.py**
- L15: `@shared_task(name="estoque.gerar_alertas_global", ignore_result=True)`
- L20: `gerar_alertas.delay(schema_name)`
- L24: `@shared_task(name="estoque.gerar_alertas")`

**apps\fiscal\services\documento_fiscal_service.py**
- L148: `transaction.on_commit(lambda: logger.info(mensagem, *args))`

**apps\fiscal\signals.py**
- L107: `processar_assinatura_documento.delay(`
- L118: `transaction.on_commit(_agendar)`

**apps\fiscal\tasks.py**
- L33: `@shared_task(`
- L128: `@shared_task(`
- L230: `@shared_task(`
- L280: `submeter_fatura_agt.apply_async(`
- L285: `polling_estado_agt.apply_async(`
- L299: `@shared_task(`

**apps\integracoes\tasks.py**
- L9: `@shared_task(`

**apps\parceiros\commercial_services.py**
- L80: `notificar_evento_comercial_staff.delay(evento_pk)`
- L83: `db_transaction.on_commit(_enviar_alerta_staff)`

**apps\parceiros\tasks.py**
- L45: `@shared_task(name="parceiros.verificar_inatividade_e_licencas_global", ignore_result=True)`
- L175: `@shared_task(bind=True, name="parceiros.notificar_mensagem_parceiro", max_retries=3, default_retry_delay=60, ignore_result=True)`
- L216: `@shared_task(bind=True, name="parceiros.notificar_evento_comercial_staff", max_retries=3, default_retry_delay=60, ignore_result=True)`
- L257: `notificar_evento_comercial_staff.delay(evento_id)`

**apps\parceiros\views_comercial.py**
- L254: `transaction.on_commit(lambda: _enfileirar_notificacao_parceiro(msg.pk))`
- L262: `notificar_mensagem_parceiro.delay(mensagem_id)`
- L449: `transaction.on_commit(lambda: _enfileirar_notificacao_evento(evento.pk))`
- L457: `notificar_evento_comercial_staff.delay(evento_id)`

**apps\relatorios\tasks.py**
- L132: `@shared_task(bind=True, max_retries=3, default_retry_delay=60)`
- L149: `@shared_task`
- L189: `@shared_task`
- L206: `@shared_task`
- L221: `@shared_task`
- L240: `@shared_task`
- L250: `@shared_task(bind=True, max_retries=3, default_retry_delay=60)`
- L277: `@shared_task(bind=True, max_retries=3, default_retry_delay=60)`

**apps\relatorios\views.py**
- L1233: `executar_agendamento_individual_task.delay(agendamento.pk, connection.schema_name)`
- L1444: `task = processar_relatorio_task.delay(report.pk, connection.schema_name)`
- L1514: `task = processar_relatorio_task.delay(report.pk, connection.schema_name); task_id = task.id`

**apps\servicos\tasks.py**
- L179: `enviar_notificacao_agendamento.apply_async(args=[schema_name, pk], expires=300)`
- L191: `@shared_task(name="servicos.processar_notificacoes_global", ignore_result=True)`
- L211: `@shared_task(name="servicos.processar_notificacoes_tenant", ignore_result=True)`
- L217: `@shared_task(name="servicos.enviar_notificacao_agendamento", acks_late=True)`
- L274: `@shared_task(name="servicos.notificar_evento_agendamento", ignore_result=True)`

**apps\servicos\tracking_services.py**
- L41: `notificar_evento_agendamento.delay(schema, evento.pk)`
- L46: `transaction.on_commit(enfileirar)`

**apps\vendas\tasks.py**
- L24: `@shared_task(name="vendas.verificar_margem_critica_global", ignore_result=True)`
- L29: `verificar_margem_critica.delay(schema_name)`
- L33: `@shared_task(name="vendas.verificar_margem_critica")`

**apps\vendas\v_views.py**
- L3544: `verificar_margem_critica.delay()`

**apps\vendas\views.py**
- L729: `transaction.on_commit(_invalidar_cache_bi)`
- L731: `transaction.on_commit(lambda: _notificar_documento_comercial('proforma', proforma_id, email_avulso, whats_avulso))`
- L785: `transaction.on_commit(_invalidar_cache_bi)`
- L787: `transaction.on_commit(lambda: _notificar_documento_comercial('fatura_credito', fatura_id, email_avulso, whats_avulso))`
- L2131: `transaction.on_commit(_invalidar_cache_bi)`
- L2133: `transaction.on_commit(lambda: _notificar_venda(venda_id, email_avulso, whats_avulso))`
- L2186: `transaction.on_commit(_invalidar_cache_bi)`
- L3257: `transaction.on_commit(_invalidar_cache_bi)`
- L3278: `transaction.on_commit(verificar_margem_critica.delay)`
- L3279: `transaction.on_commit(_invalidar_cache_bi)`

### C2_polling - Polling / obterEstado

**apps\fiscal\services\agt_client.py**
- L69: `"obterEstado": {"schema": "1.0", "timeout": (5, 30), "retry": True},`
- L701: `def obter_estado(self, request_id: str) -> Dict[str, Any]:`
- L703: `raise FiscalServiceError("obterEstado exige requestID.")`
- L710: `"obterEstado",`
- L715: `data = self._chamar("obterEstado", payload)`
- L719: `f"obterEstado falhou (HTTP {data.get('_http_status')}): "`
- L721: `servico="obterEstado",`

**apps\fiscal\services\assinatura_service.py**
- L285: `registarFactura; taxRegistrationNumber+requestID em obterEstado).`

**apps\fiscal\services\polling_service.py**
- L3: `Consulta do estado assíncrono na AGT (obterEstado) no schema do tenant activo.`
- L40: `def consultar_estado_documento(self, request_id):`
- L42: `logger.error("Tentativa de polling sem RequestID.")`
- L45: `data = self.client.obter_estado(request_id)`
- L53: `logger.exception("Falha inesperada no polling AGT (requestID=%s).", request_id)`

**apps\fiscal\services\submissao_fatura_service.py**
- L14: `obterEstado (FiscalPollingService).`

**apps\fiscal\tasks.py**
- L7: `- polling_estado_agt: consulta o estado de documentos pendentes.`
- L13: `3. O polling verifica o resultado diferido a cada 15 minutos.`
- L132: `name='fiscal.polling_estado_agt',`
- L134: `def polling_estado_agt(self, schema_name: str, documento_fiscal_id: int):`
- L137: `(/obterEstado) e actualiza o status local.`
- L149: `from apps.fiscal.services.polling_service import FiscalPollingService`
- L156: `"[%s] polling_estado_agt: DocumentoFiscal #%d não encontrado.",`
- L164: `"[%s] DocumentoFiscal #%d sem requestID — polling impossível.",`
- L179: `resultado = service.consultar_estado_documento(request_id)`
- L183: `"[%s] DocumentoFiscal #%d ainda em processamento. Reagendar polling.",`
- L197: `"[%s] DocumentoFiscal #%d — resultado inesperado do polling: %s",`
- L203: `"[%s] DocumentoFiscal #%d — máximo de retentativas de polling atingido.",`
- L208: `doc.metadados['polling_max_retries'] = True`
- L213: `"[%s] Erro de rede no polling de #%d: %s",`
- L220: `"[%s] Erro inesperado no polling de #%d: %s",`
- L285: `polling_estado_agt.apply_async(`

### C3_comandos - Management commands relacionados

**apps\configuracoes\management\commands\executar_backup_automatico.py**
- L2: `from django.core.management.base import BaseCommand`
- L7: `class Command(BaseCommand):`

**apps\configuracoes\management\commands\executar_backups.py**
- L6: `from django.core.management.base import BaseCommand`
- L14: `class Command(BaseCommand):`

**apps\configuracoes\management\commands\verificar_tenants.py**
- L2: `from django.core.management.base import BaseCommand, CommandError`
- L13: `class Command(BaseCommand):`

**apps\core\management\commands\test_mail_prod.py**
- L1: `from django.core.management.base import BaseCommand`
- L5: `class Command(BaseCommand):`

**apps\core\management\commands\test_whatsapp_config.py**
- L1: `from django.core.management.base import BaseCommand`
- L6: `class Command(BaseCommand):`

**apps\core_tenants\management\commands\auditar_empresa.py**
- L24: `from django.core.management.base import BaseCommand`
- L39: `class Command(BaseCommand):`

**apps\core_tenants\tenant_commands.py**
- L5: `from django.core.management.base import BaseCommand, CommandError`
- L9: `class TenantCommand(BaseCommand):`

**apps\empresas\management\commands\exportacao.py**
- L2: `from django.core.management.base import BaseCommand`
- L6: `class Command(BaseCommand):`

**apps\empresas\management\commands\secretKEY.py**
- L7: `from django.core.management.base import BaseCommand`
- L15: `class Command(BaseCommand):`

**apps\empresas\management\commands\setup_public_tenant.py**
- L1: `from django.core.management.base import BaseCommand`
- L5: `class Command(BaseCommand):`

**apps\financeiro\management\commands\iniciar_ambiente_fin_tenant.py**
- L14: `from django.core.management.base import BaseCommand, CommandError`
- L32: `class Command(BaseCommand):`

**apps\fiscal\management\commands\audit_fiscal.py**
- L3: `from django.core.management.base import BaseCommand`
- L11: `class Command(BaseCommand):`

**apps\fiscal\management\commands\export_saft.py**
- L3: `from django.core.management.base import BaseCommand, CommandError`
- L9: `class Command(BaseCommand):`

**apps\fiscal\management\commands\iniciar_ambiente_fiscal_tenant.py**
- L13: `from django.core.management.base import BaseCommand, CommandError`
- L20: `class Command(BaseCommand):`

**apps\funcionarios\management\commands\criar_cargos_padrao.py**
- L1: `from django.core.management.base import BaseCommand, CommandError`
- L7: `class Command(BaseCommand):`

**apps\funcionarios\management\commands\setup_departamento.py**
- L11: `from django.core.management.base import BaseCommand, CommandError`
- L17: `class Command(BaseCommand):`

**apps\integracoes\management\commands\seed_integracoes.py**
- L1: `from django.core.management.base import BaseCommand`
- L6: `class Command(BaseCommand):`

**apps\licenca\management\commands\setup_modulos.py**
- L1: `from django.core.management.base import BaseCommand`
- L30: `class Command(BaseCommand):`

**apps\licenca\management\commands\setup_planos.py**
- L3: `from django.core.management.base import BaseCommand, CommandError`
- L191: `class Command(BaseCommand):`

**apps\licenca\management\commands\verificar_licencas.py**
- L2: `from django.core.management.base import BaseCommand`
- L8: `class Command(BaseCommand):`

**apps\parceiros\management\commands\listar_parceiros.py**
- L7: `from django.core.management.base import BaseCommand`
- L15: `class Command(BaseCommand):`

**apps\servicos\management\commands\processar_notificacoes.py**
- L3: `from django.core.management.base import BaseCommand, CommandError`
- L7: `class Command(BaseCommand):`

### D1_credenciais_risco - Locais onde cabecalhos/credenciais podem ser persistidos (rever manualmente)

**apps\core\utils.py**
- L49: `self.headers = {`
- L50: `"Authorization": f"Bearer {self.token}",`
- L75: `headers={"Authorization": f"Bearer {self.token}"},`
- L97: `response_send = requests.post(self.url_base, headers=self.headers, json=payload, timeout=30)`

**apps\core\views.py**
- L539: `headers={'Cache-Control': 'public, max-age=3600'},`

**apps\core_tenants\utils.py**
- L49: `self.headers = {`
- L50: `"Authorization": f"Bearer {self.token}",`
- L75: `headers={"Authorization": f"Bearer {self.token}"},`
- L97: `response_send = requests.post(self.url_base, headers=self.headers, json=payload, timeout=30)`

**apps\fiscal\services\agt_client.py**
- L300: `auth = self._credenciais()`
- L347: `auth=auth,`
- L349: `headers={"Accept": "application/json"},`

**apps\fiscal\services\submissao_fatura_service.py**
- L123: `auth=(credenciais["username"], credenciais["password"]),`

**apps\fiscal\services\whatsapp_service.py**
- L42: `headers = {`
- L43: `"Authorization": f"Bearer {self.token}",`
- L55: `response = requests.post(self.url, json=payload, headers=headers, timeout=20)`

**apps\integracoes\models.py**
- L202: `headers = models.JSONField(default=dict, blank=True)   # já mascarados`
- L235: `headers = models.JSONField(default=dict, blank=True)`

**apps\integracoes\services\catalogo.py**
- L81: `dict(chave='cabecalho_auth', label='Cabeçalho de autenticação', tipo='text', padrao='Authorization'),`
- L87: `'Indique o cabeçalho e o prefixo exigidos (ex.: X-API-Key e prefixo vazio, ou Authorization e "Bearer ").',`
- L101: `dict(chave='cabecalho_auth', label='Cabeçalho de autenticação', tipo='text', padrao='Authorization'),`

**apps\integracoes\services\cliente.py**
- L76: `headers=_mascarar(dict(headers or {})), payload=payload, status_code=status_code,`
- L86: `def chamar(config, metodo, url, *, headers=None, json_body=None, data=None, params=None, auth=None,`
- L104: `resp = requests.request(metodo, url, headers=headers, json=json_body, data=data, params=params,`
- L105: `auth=auth, timeout=config.timeout_segundos, allow_redirects=False)`

**apps\integracoes\services\providers.py**
- L90: `return {'Authorization': f"Bearer {self.cred['access_token']}"}`
- L93: `r = chamar(self.config, 'GET', f"{self._base()}/{self.cred['phone_number_id']}", headers=self._h(),`
- L103: `headers=self._h(),`
- L149: `r = chamar(self.config, 'GET', self._base() + '.json', auth=self._auth(), exigir_ativa=False)`
- L158: `r = chamar(self.config, 'POST', self._base() + '/Messages.json', auth=self._auth(),`
- L173: `return {'Authorization': f"Bearer {self.cred['api_key']}"}`
- L176: `r = chamar(self.config, 'GET', 'https://api.sendgrid.com/v3/scopes', headers=self._h(), exigir_ativa=False)`
- L187: `r = chamar(self.config, 'POST', 'https://api.sendgrid.com/v3/mail/send', headers=self._h(), json_body=corpo)`
- L201: `headers = {'Content-Type': 'application/json', 'X-Webhook-Event': evento,`
- L203: `r = chamar(self.config, 'POST', self.cred['url_destino'], headers=headers, data=corpo,`
- L219: `nome = self.cfg.get('cabecalho_auth') or 'Authorization'`
- L224: `return chamar(self.config, metodo, self._url(caminho), headers=self._h(), json_body=json_body,`

**apps\integracoes\services\webhooks.py**
- L52: `headers={k: v for k, v in request.headers.items() if k.lower() not in HEADERS_EXCLUIDOS},`

**apps\produtos\views.py**
- L1150: `headers = list(ExportarProdutosExcelView.HEADERS) + self.HEADERS_EXTRA`

**apps\relatorios\utils.py**
- L196: `headers = list(rows[0].keys()); table_data = [headers] + [[str(row.get(key, "")) for key in headers] for row in rows]`
- L209: `headers = list(rows[0].keys()) if rows else ["Informação"]`
- L218: `headers = list(rows[0].keys()) if rows else ["Informação"]`
- L272: `rows = data.get("linhas", []); headers = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []`

**apps\relatorios\views.py**
- L1350: `headers = list(rows[0].keys()); data = [headers] + [[row.get(h, "") for h in headers] for row in rows]`
- L1365: `headers = list(rows[0].keys()) if rows else ["Informação"]`
- L1375: `rows = self.get_dados(kwargs["pk"]); output = StringIO(); headers = list(rows[0].keys()) if rows else ["Informação"]`

**apps\vendas\v_views.py**
- L3520: `headers = self.get_success_headers(serializer.data)`
- L3524: `}, status=status.HTTP_201_CREATED, headers=headers)`
- L3547: `headers = self.get_success_headers(serializer.data)`
- L3548: `return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)`

**apps\vendas\views.py**
- L3259: `headers = self.get_success_headers(serializer.data)`
- L3263: `}, status=status.HTTP_201_CREATED, headers=headers)`
- L3281: `headers = self.get_success_headers(serializer.data)`
- L3282: `return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)`

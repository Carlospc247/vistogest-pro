# conversa_recente.md — VistoGest Pro: handoff de contexto

> Documento de continuidade. Se estás a ler isto, é porque a sessão anterior
> de IA ficou sem tokens a meio do trabalho. Este ficheiro explica **o que**
> estamos a fazer, **porquê**, **o que já foi decidido** (não voltar a
> perguntar), **o que já foi entregue**, e **exactamente onde parámos**.
> O dono do sistema chama-se Carlos, está em Angola, e o projecto é o
> VistoGest Pro — ver `CLAUDE.md` na raiz do repositório para o contexto
> técnico permanente do projecto (stack, convenções, estrutura de pastas).
> Este ficheiro é sobre o trabalho **em curso**, não sobre o projecto em geral.

Há duas frentes de trabalho em paralelo nesta sessão. São independentes uma
da outra — podes continuar qualquer uma sem depender da outra estar concluída.

---

## FRENTE A — Módulo Fiscal AGT (facturação electrónica, SAF-T)

### Porquê
O VistoGest Pro precisa de cumprir o **Decreto Executivo n.º 683/25** (Diário
da República, I Série, N.º 159, 22/08/2025), que define a estrutura de dados
e o modelo de facturação electrónica da AGT (Administração Geral Tributária
de Angola), mais o **SAF-T AO 1.01_01 XSD** (ficheiro de auditoria fiscal
periódico) e a documentação do **Portal do Parceiro AGT**. São três fontes
oficiais, e por vezes discordam entre si em detalhes — cada discordância
encontrada foi resolvida e está registada abaixo.

### Documentos de referência já produzidos (entregues ao utilizador)
- **`CLAUDE.md`** — reescrito nesta sessão, separa FACTO / DECISÃO-REGRA /
  NÃO VERIFICADO sobre toda a arquitectura do projecto (não só fiscal).
- **`PLANO_IMPLEMENTACAO.md`** — plano faseado (Fase 1 a Fase 9) de tudo o
  que falta corrigir no módulo fiscal, com checkboxes de estado.

**Lê esses dois ficheiros primeiro** se estiverem no repositório — são mais
detalhados do que este resumo. O que se segue é o essencial para não
repetires perguntas já respondidas.

### Decisões já tomadas (NÃO voltar a perguntar)

1. **Duas chaves RSA distintas, origens opostas**:
   - **Chave do Software** (`jwsSoftwareSignature`) — gerada **localmente**
     pela SOTARQ (o produtor do software), uma só para todos os tenants,
     homologada uma vez no Portal do Parceiro AGT. Vive em variável de
     ambiente (`AGT_SOFTWARE_PRIVATE_KEY_PEM`), nunca em base de dados.
     `SOTARQ_PRIVATE_KEY` é nome antigo/código morto — não usar.
   - **Chave do Contribuinte** (`jwsDocumentSignature`, `jwsSignature`) —
     **emitida pela AGT**, uma por NIF, obtida no Portal do Contribuinte por
     cada cliente e colada manualmente no sistema. É por tenant, guardada
     (cifrada com AES via `AESService`) no modelo singleton `AssinaturaDigital`
     (`apps/fiscal/models.py`, sem FK para `Empresa` — isolamento físico).
     **Nunca é gerada pelo sistema** — só recebida e guardada.

2. **JWS = RS256 = RSASSA-PKCS1-v1_5 + SHA-256** (RFC 7518). **Não é
   RSA-PSS** — a implementação antiga usava PSS por engano; uma assinatura
   PSS seria rejeitada por qualquer validador RS256 padrão, incluindo o da
   AGT. Corrigido em `gerar_jws_rs256()`/`verificar_jws_rs256()`
   (`apps/fiscal/services/assinatura_service.py`).

3. **Assinar é síncrono; falar com a AGT é assíncrono.** RSA local corre
   inline, na mesma transacção que confirma o documento. Só a chamada HTTP
   a `registarFactura` (que devolve `requestID` na hora, mas a validação
   fiscal completa é diferida) vai para Celery, via `FiscalPollingService`
   + `obterEstado`.

4. **Unificação das cadeias de hash/ATCUD — "opção A modificada" (decisão
   confirmada)**: existia uma falha de arquitectura em que `Venda`,
   `FaturaCredito`, `Recibo`, `NotaCredito`, `NotaDebito`,
   `DocumentoTransporte` (em `apps.vendas`) tinham cada um o seu próprio
   `hash_documento`/`atcud`, **completamente desligado** do `DocumentoFiscal`
   (em `apps.fiscal`), que tinha outro hash/ATCUD independente. Uma mesma
   fatura podia ter dois hashes diferentes. Decisão: `DocumentoFiscal` passa
   a ser a **única fonte de verdade**; os 6 modelos de `apps.vendas` passam
   a ter `documento_fiscal = OneToOneField('fiscal.DocumentoFiscal', ...)`,
   e os seus campos `hash_documento`/`atcud` locais tornam-se apenas cache
   de leitura, sincronizado a partir do `DocumentoFiscal` ligado — nunca
   gerados localmente outra vez. **Esta migração (adicionar o OneToOneField
   e reescrever `gerar_documento_fiscal()`) ainda não foi aplicada em
   código** — só a decisão está tomada e documentada no `PLANO_IMPLEMENTACAO.md`.

5. **Códigos de retenção na fonte — dois schemas AGT diferentes, não um
   "desactualizado"**:
   - Decreto 683/25, Anexo I (`withholdingTaxList`, usado na API de
     facturação electrónica): 9 códigos — `IRT, II, IS, IVA, IP, IAC, OU,
     IRPC, IRPS` (`IRPC`/`IRPS` marcados no Decreto como "impostos futuros").
   - SAF-T AO 1.01_01 XSD (`WithholdingTaxType`, usado no ficheiro SAF-T
     periódico): 7 códigos — `IRT, II, IS, IVA, IPU, IAC, OU` (nota: `IPU`,
     não `IP`; sem `IRPC`/`IRPS`).
   - Decisão: o modelo interno (`TIPO_RETENCAO_CHOICES` em
     `apps/core/choices.py`) guarda os **9 códigos do Decreto** (fonte
     única, à prova de futuro). A exportação SAF-T traduz para os 7 do XSD
     no momento de gerar o XML, nunca ao contrário — ver
     `apps/fiscal/services/saft_mapping.py` (`mapear_withholding_tax_saft()`).
   - **Actualização posterior do utilizador**: o bloqueio de data de vigor
     para `IRPS` (que impedia seleccionar o código antes de Jan/2027) foi
     **removido** — por altura da certificação do sistema junto da AGT, esse
     prazo já terá passado, e o utilizador não quer risco de problemas de
     certificação por causa de um bloqueio que deixou de fazer sentido. Ver
     `apps/core/choices.py` tal como partilhado pelo utilizador — já reflecte
     isto (comentário explícito no ficheiro: "O bloqueio foi removido").

6. **URL do QR Code** — discrepância entre o Decreto Executivo 683/25 (Anexo
   III: `https://portaldocontribuinte.minfin.gov.ao/consultar-fe?documentNo`)
   e o Portal do Parceiro (`https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor=nifEmissor&document=documentNo`).
   Decisão do utilizador: usar a URL do **Portal do Parceiro** (considera o
   texto do Decreto desactualizado/erro de contexto nesse ponto específico).
   Já está em `settings.AGT_QR_CODE_BASE_URL`.

7. **`TaxaIVAAGT.TAX_EXEMPTION_REASON_CHOICES`** — lista antiga (`M99, M01,
   M02`) não existia na lista oficial. Substituída pela lista completa das
   Tabelas 4 (IVA, `M10`-`M24`, `M80`-`M86`, `M30`-`M38`, `M90`-`M93`, `M00`,
   `M02`, `M04`), 5 (Imposto de Selo, `S01`-`S03`) e 6 (IEC, `I01`-`I16`) do
   Decreto. Já entregue como bloco de código completo numa resposta anterior
   — ver histórico da conversa ou `PLANO_IMPLEMENTACAO.md`, Fase 4.

### Ficheiros já entregues/reescritos nesta sessão
- `apps/fiscal/models.py` — `AssinaturaDigital` reescrito (singleton,
  sem FK empresa, separa chave do contribuinte).
- `apps/fiscal/services/assinatura_service.py` — `AssinaturaSoftwareService`,
  `AssinaturaDigitalService`, `VerificadorIntegridadeService`, helpers JWS.
- `apps/fiscal/services/saft_mapping.py` — tradução de códigos de retenção
  para o SAF-T XSD.
- `apps/core/choices.py` — `TIPO_RETENCAO_CHOICES`, `OPERATION_TYPE_CHOICES`
  (já incorporados pelo utilizador no ficheiro real).
- `config/settings/base.py` — variáveis `AGT_SOFTWARE_*`, `AGT_ENVIRONMENT`,
  `AGT_BASE_URL_*`, `AGT_QR_CODE_BASE_URL`.
- Comando `gerar_chave_teste --tipo=software|contribuinte`.

### Estado actual / onde parámos nesta frente
A **Fase 1.2** do `PLANO_IMPLEMENTACAO.md` (limpeza de views/serializers que
ainda referenciam o `AssinaturaDigital` antigo — `AssinaturaDigitalViewSet`,
`AssinaturaGerarChavesView` [apagar], `debug_testar_assinatura`,
`ajax_status_assinatura`, `DownloadChavePublicaView` e afins,
`FiscalPollingService.consultar_estado_documento()`) foi **descrita em
detalhe com código pronto numa resposta anterior**, mas ainda não temos
confirmação do utilizador de que foi aplicada ao repositório real.

**Próximo passo nesta frente**: confirmar com o utilizador se a Fase 1.2 já
foi aplicada; se sim, avançar para a Fase 2 (migração `documento_fiscal`
OneToOneField nos 6 modelos de `apps.vendas` — ainda preciso de ver o corpo
actual de `gerar_documento_fiscal()`/equivalentes nesses 6 modelos antes de
escrever a migração, para não reescrever algo que já funciona de forma
diferente do que foi descrito). Se a Fase 1.2 ainda não foi aplicada, é o
próximo passo lógico antes de tudo o resto.

---

## FRENTE B — Migração `apps/core` → `apps/core` + `apps/core_tenants`

### Porquê
Bug original: `{% safe_url 'vendas:pdv' %}` nos templates devolvia `'#'`
(link morto) quando renderizado dentro de um schema de tenant. Causa raiz:
`apps/core` estava em `SHARED_APPS`, mas continha views e URLs que só fazem
sentido no contexto de um tenant (dashboard, notificações, 2FA por IP,
licença). O Django ficava com o namespace `core` ambíguo entre os dois
urlconfs (`urls_public.py` e `urls_tenants.py`), e isso impedia a resolução
correcta de outros namespaces de tenant como `vendas:pdv`.

### Solução
Separar em duas apps:
- **`apps/core`** (continua `SHARED_APPS`, schema `public`) — só login,
  logout, reset de password, rate limiting de login, PWA, e
  `PlanoBypassView` (painel de comissões SOTARQ que itera todas as
  empresas via `schema_context`, por isso corre no schema public).
- **`apps/core_tenants`** (nova, `TENANT_APPS`) — dashboard, notificações,
  segurança/2FA por IP, licença, permissões de negócio (`EmpresaPermission`,
  `FiscalPermission`, `ContabilidadePermission`, `EmpresaAdminPermission`).

### Decisão de namespace (importante — já mudou uma vez)
O plano original do utilizador (`PLANO_CORE_TENANT.md`) considerava manter
`app_name = 'core'` em `core_tenants/urls.py` para não ter de mudar
referências em templates. **Decisão final, confirmada explicitamente pelo
utilizador**: usar `core_tenants` como namespace real e distinto. Ou seja,
nos templates e no código, `core:login`/`core:logout` continuam `core:`,
mas `dashboard`, `notifications`, `verify_ip`, etc. passam a
`core_tenants:dashboard`, `core_tenants:notifications`,
`core_tenants:verify_ip`.

### Regra de dependência a respeitar sempre
**`apps.core` nunca deve importar de `apps.core_tenants`.** O inverso é
permitido (`core_tenants` pode importar modelos/serviços de `apps.core`).
Isto causou um bug real nesta sessão (ver abaixo) — qualquer classe que
fique em `apps/core/views.py` não pode herdar de nada que tenha ido para
`core_tenants`.

### Ficheiros já entregues nesta sessão (prontos, aplicados pelo utilizador)
- `apps/core_tenants/models.py` — vazio por design.
- `apps/core_tenants/views.py` — `BaseMPAView`, `DashboardView` (placeholder,
  ver nota abaixo), `DashboardStatsAPI`, `SecurityHistoryView`,
  `TerminarOutrasSessoesView`, `VerifyIPView`, `NotificationListView` +
  3 views AJAX de notificação, helpers `_icon_for_alerta`/`_color_for_prioridade`.
- `apps/core_tenants/urls.py` — namespace `core_tenants`, todas as rotas acima.
- `apps/core_tenants/middleware.py` — `DocumentLogMiddleware`,
  `ModuloAcessMiddleware`, `LicencaVencidaMiddleware`, `TwoFactorIPMiddleware`
  (com o `reverse('core:verify_ip', ...)` corrigido para
  `reverse('core_tenants:verify_ip', ...)` — bug real encontrado e corrigido).
- `apps/core_tenants/context_processors.py` — `dashboard_data`,
  `notifications_context`, `modules_context`, cada uma com guard
  `if connection.schema_name == 'public': return {}`.
- `apps/core_tenants/permissions.py` — `EmpresaPermission`,
  `EmpresaAdminPermission`, `FiscalPermission`, `ContabilidadePermission`,
  `empresa_required`, `fiscal_required`.
- `config/settings/base.py` — `apps.core_tenants` adicionado a
  `TENANT_APPS` (faltava!), `MIDDLEWARE` a apontar para
  `apps.core_tenants.middleware.*`, `TEMPLATES.context_processors` a
  apontar para `apps.core_tenants.context_processors.*` (e `modules_context`
  foi **adicionado** à lista — nunca tinha sido registado antes, possível
  esquecimento anterior do utilizador, sinalizado mas não confirmado).
- `config/urls_tenants.py` — corrigido: faltava
  `path('', include(('apps.core.urls_login', 'core'), namespace='core'))`.
  Sem isto, **nenhum utilizador autenticado conseguia navegar num tenant**
  (o próprio `RedirectView` da raiz e o `TwoFactorIPMiddleware` dependem de
  `core:login`/`core:logout` resolverem dentro do `TENANT_URLCONF`, e
  namespaces são por árvore de urlconf, não globais — incluir
  `urls_login.py` só em `urls_public.py` não bastava).
- `config/urls_public.py` — confirmado que **não precisa de alterações**
  (já incluía `apps.core.urls_login` com `namespace='core'` correctamente).

### Bugs encontrados e corrigidos nesta frente (histórico, para não repetir)
1. `TwoFactorIPMiddleware` fazia `reverse('core:verify_ip', ...)` — corrigido
   para `core_tenants:verify_ip` (view mudou de app).
2. `urls_tenants.py` sem o include de `apps.core.urls_login` — corrigido
   (ver acima).
3. **`PlanoBypassView` (em `apps/core/views.py`) ainda herdava de
   `BaseMPAView`**, que mudou para `apps/core_tenants/views.py`. Isto causou
   um `NameError: name 'BaseMPAView' is not defined` real, visto no log do
   utilizador, que impedia o servidor de arrancar. **Corrigido**: `PlanoBypassView`
   deixou de herdar de `BaseMPAView` — passa a herdar directamente de
   `TemplateView`, com a lógica de `get_empresa()`/`empresa_atual` removida
   (não fazia sentido ali, já que esta view corre sempre no schema `public`).
   Isto respeita a regra "core nunca importa de core_tenants".
4. `DashboardStatsAPI` ficou **duplicada** — existe tanto em
   `apps/core/views.py` (versão antiga, ainda lá) como em
   `apps/core_tenants/views.py` (versão nova, correcta). **Por fazer**:
   apagar a cópia de `apps/core/views.py`.
5. `apps/core/urls_login.py` tinha (em ambas as versões que o utilizador
   mandou nesta sessão, incluindo uma com `app_name` errado como
   `'core_tenants'`) 4 rotas a apontar para `NotificationListView` e as 3
   views AJAX de notificação, que **já não existem** em `apps/core/views.py`
   (foram correctamente removidas de lá). Isto ia causar `AttributeError`
   no arranque. **Corrigido**: versão final de `urls_login.py` entregue,
   com `app_name = 'core'` (não `'core_tenants'` — essa era uma versão
   incorrecta que o utilizador também tinha mandado) e sem essas 4 rotas.
6. `DashboardView` nunca teve o corpo real partilhado nesta sessão — só era
   referenciada (`reverse_lazy('core_tenants:dashboard')`,
   `redirect('core_tenants:dashboard')`). Criado um **placeholder** em
   `core_tenants/views.py` com `# TODO` explícito — não inventei lógica de
   negócio sem base.
7. **Ainda por confirmar/aplicar**: qualquer ficheiro em `apps/fiscal` ou
   `apps/vendas` que faça `from apps.core.permissions import
   EmpresaPermission, FiscalPermission, ContabilidadePermission,
   EmpresaAdminPermission` (ou os decoradores `empresa_required`/
   `fiscal_required`) tem de passar a importar de
   `apps.core_tenants.permissions`. Já confirmei que `apps/fiscal/views.py`
   e `apps/vendas/views.py` fazem isto — vão rebentar assim que as classes
   saírem de `apps/core/permissions.py` por completo. `MultiplePermissions`,
   `SuperUserPermission`, `ReadOnlyPermission` continuam em
   `apps.core.permissions` sem alteração.
8. `apps/core/urls.py` (o ficheiro antigo, misturado — tem `app_name = 'core'`
   mas inclui `path('', views.DashboardView.as_view(), ...)` comentado, e
   outras rotas de tenant) **pode já ser código morto**, substituído por
   `urls_login.py` + `core_tenants/urls.py`. Ainda não confirmado se algum
   urlconf (`urls_public.py` ou `urls_tenants.py`) ainda o inclui — se não
   incluir, pode ser apagado com segurança.

### Estado actual / onde parámos nesta frente
O traceback mais recente do utilizador (`NameError: name 'BaseMPAView' is
not defined` em `apps/core/views.py` linha 85) foi **diagnosticado e
corrigido** (ponto 3 acima) nesta última resposta, junto com a limpeza final
de `urls_login.py` (ponto 5). **Ainda não há confirmação do utilizador de
que aplicou estas duas correcções e que o servidor arranca sem erros.**

**Próximo passo nesta frente, por ordem**:
1. Confirmar que `PlanoBypassView` foi corrigida e `urls_login.py` final foi
   aplicado — pedir ao utilizador para correr `python manage.py check` (ou
   tentar arrancar o `runserver`) e colar qualquer erro novo.
2. Apagar a cópia duplicada de `DashboardStatsAPI` em `apps/core/views.py`
   (ponto 4 acima).
3. Procurar e corrigir os imports de `EmpresaPermission`/`FiscalPermission`/
   etc. em `apps/fiscal` e `apps/vendas` (ponto 7 acima) — provavelmente o
   próximo erro a aparecer depois dos dois primeiros estarem resolvidos.
4. Confirmar se `apps/core/urls.py` (antigo, misturado) ainda é referenciado
   nalgum lado; se não for, pode ser apagado.
5. Preencher o corpo real de `DashboardView` quando o utilizador tiver essa
   lógica disponível (ponto 6 acima).

---

## Como retomar esta conversa com outra IA

1. Lê primeiro `CLAUDE.md` e `PLANO_IMPLEMENTACAO.md` se existirem no
   repositório — têm mais detalhe técnico do que este ficheiro.
2. Este ficheiro (`conversa_recente.md`) diz-te **o que já foi decidido** —
   não voltes a perguntar "qual chave é gerada localmente" ou "qual
   namespace usar", já está respondido acima.
3. Pede ao utilizador o estado actual dos ficheiros de `apps/core`,
   `apps/core_tenants`, `apps/fiscal` e `apps/vendas` antes de continuares
   — esta conversa evoluiu rapidamente e os ficheiros reais podem já ter
   mudado desde a última versão que vês aqui.
4. Se o utilizador colar um traceback novo, cruza-o sempre com a secção
   "Bugs encontrados e corrigidos" de cada frente acima — é provável que
   seja uma consequência directa de uma das migrações já em curso, não um
   problema novo.
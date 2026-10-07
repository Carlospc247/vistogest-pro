# PLANO DE IMPLEMENTAÇÃO — VistoGest Pro / SOTARQ Software
## Versão 9.0 — Plano Consolidado

> **Última actualização:** 01/Out/2026
> **Estado geral:** S1–S12 implementados · S13 (segurança) em curso

---

## Legenda

| Símbolo | Significado |
|---|---|
| `[x]` | Concluído e confirmado |
| `[~]` | Parcialmente feito / com bugs |
| `[ ]` | Por fazer |
| `[!]` | Depende de acção externa |

---

# ══════════════════════════════════════════════════════
# S1–S12 ✅ IMPLEMENTADOS
# ══════════════════════════════════════════════════════

| Secção | Descrição | Estado |
|---|---|---|
| S1 | Infra (scripts, Procfile, check_settings, auditar_integridade, gerenciar_sotarq) | ✅ |
| S2 | Migrações criadas (fiscal 0001–0006, vendas 0001–0004, empresas, funcionarios, parceiros, site) | ✅ |
| S3 | Imutabilidade documentos fiscais (DocumentoFiscalService, máquina de estados) | ✅ |
| S4 | PDF redesign (operation_type, regime_fiscal, comentarios, ANULADO, WhatsApp QR) | ✅ |
| S5 | SAF-T AO 1.01_01 (SaftValidacaoService, SerieFiscalService, proxies GF/AF) | ✅ |
| S6 | Portal de Parceiros (10 modelos, services, views, admin, urls, management commands) | ✅ |
| S7 | App site — Site institucional + Loja online | ✅ |
| S8 | Notificações (AJAX polling, marcar lida, NotificacaoCountAjaxView) | ✅ |
| S9 | PWA (manifest.json dinâmico, SW na raiz, install banner, offline page) | ✅ |
| S10 | Chave AGT do Contribuinte (formulário, teste JWS, credenciais API) | ✅ |
| S11 | 17 Documentos de Homologação AGT + dashboard + management command | ✅ |
| S12 | Site Builder drag-and-drop (SortableJS, 18 blocos, design global, modal tema) | ✅ |

---

# ══════════════════════════════════════════════════════
# S13 — SEGURANÇA: .ENV CANÓNICO + SCAN DE VULNERABILIDADES
# ══════════════════════════════════════════════════════

## 13.1 — .env Canónico e base.py sem fallbacks ✅

**Regra adoptada:** `base.py` usa **exclusivamente** `os.environ['VAR']` (falha imediatamente
se ausente) ou `os.getenv('VAR')` que retorna `None` — sem defaults inline.
Todos os defaults operacionais ficam no `.env` ou nos ficheiros de settings específicos.

**Ficheiros alterados:**
- `.env` — reescrito com todas as variáveis, documentado e organizado
- `config/settings/base.py` — eliminados todos os defaults inline
- `config/settings/development.py` — mantém overrides legítimos (email console, SECRET_KEY dev)
- `config/settings/production.py` — mantém `os.environ['VAR']` obrigatórios

## 13.2 — Vulnerabilidades encontradas e corrigidas ✅

### 🔴 ALTA — ENCRYPTION_KEY ausente das settings
- **Ficheiro:** `apps/integracoes/models.py` + `base.py`
- **Problema:** `ConfiguracaoIntegracao.set_credenciais()` usa `settings.ENCRYPTION_KEY`
  mas a variável não existia em nenhum settings file. A encriptação falhava silenciosamente.
- **Correcção:** Adicionado `ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')` ao `base.py`
  e `ENCRYPTION_KEY=<fernet_key>` ao `.env`.

### 🟠 MÉDIA — Webhooks sem verificação HMAC
- **Ficheiros:** `apps/fiscal/views_integracoes.py` (webhooks AGT e Banco Central)
- **Problema:** Qualquer pessoa que conhecesse o URL podia fazer POST com dados arbitrários.
- **Correcção:** Adicionada verificação HMAC com `GATEWAY_WEBHOOK_SECRET` do `.env`.

### 🟠 MÉDIA — Endpoints de integração sem autenticação
- **Ficheiro:** `apps/fiscal/views_integracoes.py`
- **Problema:** `integracao_agt_validar` e `integracao_saft_submit` sem `@login_required`.
- **Correcção:** Adicionado `@login_required` a ambos.

### 🟠 MÉDIA — `webhook_agt_notification` duplicado
- **Ficheiros:** `apps/fiscal/views.py` e `apps/fiscal/views_integracoes.py`
- **Problema:** Mesma função definida em dois lugares — o segundo silencia o primeiro.
- **Correcção:** Removida a cópia de `views.py`, mantida só em `views_integracoes.py`.

### 🟡 BAIXA — `@csrf_exempt` redundante em endpoints autenticados
- **Ficheiro:** `apps/vendas/views.py`
- **Problema:** `remover_item_nota_debito_api`, `remover_item_documento_transporte_api`,
  `nota_debito_pdf_view` têm `@csrf_exempt` + `@login_required` — o CSRF devia estar activo.
- **Correcção:** Removido `@csrf_exempt` dos três (o JS já envia `X-CSRFToken`).

### 🟡 BAIXA — `LoginUnblockView` usa auth manual em vez de mixin
- **Ficheiro:** `apps/core/views.py`
- **Correcção:** Adicionado `LoginRequiredMixin`.

### 🟡 BAIXA — `SECURE_HSTS_*` no base.py (aplica-se a dev)
- **Correcção:** Movido para `production.py` exclusivamente.

### 🔵 INFO — `WhatsAppService` sem timeout HTTP
- **Ficheiro:** `apps/core/utils.py`
- **Correcção:** `timeout=30` adicionado em ambas as chamadas `requests.post()`.

### 🔵 INFO — hCaptcha silenciosamente não-funcional sem chaves reais
- **Situação:** Chaves de teste oficiais hCaptcha funcionam correctamente em DEV.
  Em PROD, `HCAPTCHA_SITE_KEY` e `HCAPTCHA_SECRET_KEY` já estão no `.env`.
- **Estado:** ✅ Documentado e resolvido via `.env`.

## 13.3 — Inventário completo do .env [ ]

Todas as variáveis lidas pelo sistema, com secção, descrição e exemplo.
Ver ficheiro `.env` para o estado actual.

---

# NOTAS PERMANENTES DE ARQUITECTURA

1. **Chave do Software AGT** — só em `AGT_SOFTWARE_PRIVATE_KEY_PEM` no `.env`. Nunca na BD.
2. **Chave do Contribuinte AGT** — emitida pela AGT, cifrada AES na BD (`AssinaturaDigital`).
3. **Isolamento físico** — nenhum filtro `empresa=` em TENANT_APPs. Schema PostgreSQL isola.
4. **Documentos fiscais imutáveis** — nunca sobrescrever após `confirmed`. Usar rectificativos.
5. **`Empresa.regime`** = tipo de actividade. **`Empresa.regime_fiscal`** = regime tributário AGT.
6. **Portal de Parceiros** — parceiro selecciona planos da `apps.licenca`; nunca os cria.
7. **App site** — TENANT_APP. Nunca passar `empresa=` a modelos tenant.
8. **PWA** — SW registado em `/service-worker.js` (raiz). Scope `/`.
9. **Site Builder** — secções guardadas como JSON em `Secao.dados`.
10. **Homologação AGT** — documentos `HOM-*` são de teste. Não submeter sem chaves reais.
11. **Variáveis de ambiente** — `base.py` não tem defaults inline. Todos os valores vêm do `.env`.

---

# ESTADO ACTUAL

| Módulo | Estado |
|---|---|
| Migrações (public + mundoemaquinas) | ✅ Todas aplicadas |
| S1–S12 | ✅ Implementados |
| .env canónico + base.py sem fallbacks | ✅ |
| Scan de segurança + correcções | ✅ |
| Chaves AGT configuradas em mundoemaquinas | [!] Requer acção manual |
| Submissão à AGT (homologação) | [!] Requer chaves configuradas |
| HCAPTCHA_SITE_KEY / SECRET_KEY (produção) | [!] Requer conta hcaptcha.com |

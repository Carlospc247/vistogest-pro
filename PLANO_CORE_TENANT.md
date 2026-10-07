# PLANO_CORE_TENANT.md
## Separação apps/core → apps/core + apps/core_tenants

> **Versão:** 1.0 — Para análise e aprovação antes de qualquer implementação.  
> **Objectivo:** resolver o problema em que `{% safe_url 'vendas:pdv' %}` retorna `'#'`  
> porque o `apps/core/urls.py` está em SHARED_APPS e os namespaces de tenant  
> não ficam disponíveis quando o template é renderizado via `apps.core.views`.

---

## 1. RAIZ DO PROBLEMA

O `apps/core` está em **SHARED_APPS** (schema public).  
Quando o Django carrega o `urls_tenants.py` e inclui `apps.core.urls`,  
o namespace `core` fica registado com o resolver do schema tenant.  
MAS: as views como `DashboardView`, `NotificationListView`, etc.  
estão no mesmo `apps.core.views` — o Python não sabe se estão  
a ser chamadas do public ou do tenant.  

Resultado: o `{% url %}` (e o `{% safe_url %}`) usam o resolver activo  
do context do request, e quando esse resolver é ambíguo (por `core`  
estar em dois urlconfs ao mesmo tempo), os namespaces de tenant  
como `vendas` nem chegam a ser resolvidos — retornam `'#'`.

**Solução permanente:** as views e URLs de tenant saem de `apps/core`  
e passam para `apps/core_tenants` (já em TENANT_APPS).  
O Django sabe então exactamente que `apps/core` = public e  
`apps/core_tenants` = tenant.

---

## 2. ESTADO ACTUAL DOS FICHEIROS

### `apps/core` (SHARED_APPS — schema public)
| Ficheiro | Estado actual |
|---|---|
| `models.py` | ✅ Correcto — `Usuario`, `AuditoriaAcesso`, `IPConhecido`, `VerificacaoSeguranca`, `LoginAttempt` — ficam aqui |
| `views.py` | ⚠️ Misturado — tem views public E tenant na mesma |
| `urls.py` | ⚠️ Misturado — tem URLs public E tenant na mesma |
| `urls_login.py` | ✅ Já é o ficheiro correcto para o schema public |
| `middleware.py` | ⚠️ Misturado — `RateLimitLoginMiddleware` é public; os outros são tenant |
| `context_processors.py` | ⚠️ Misturado — `regime_context` serve ambos; os outros são tenant |
| `permissions.py` | ⚠️ Misturado — algumas são tenant-only |
| `services/` | ✅ Correcto — `rate_limit_service` e `captcha_service` são public |
| `templatetags/pharma_tags.py` | ✅ Fica em `apps/core` (pode ser carregado em ambos os schemas) |

### `apps/core_tenants` (TENANT_APPS — schemas tenant)
| Ficheiro | Estado actual |
|---|---|
| `apps.py` | ✅ Configurado — `name='apps.core_tenants'` |
| `models.py` | ❌ Cópia exacta de `apps/core/models.py` — precisa de ser limpo |
| `views.py` | ❌ Existente mas vazio/stub — precisa de receber as views de tenant |
| `urls.py` | ❌ Cópia exacta de `apps/core/urls.py` — precisa de apontar para `core_tenants.views` |
| `middleware.py` | ❌ Existente — precisa de receber os middlewares de tenant |
| `context_processors.py` | ❌ Existente — precisa de receber os context processors de tenant |
| `permissions.py` | ❌ Existente — precisa de receber as permissões de tenant |

---

## 3. O QUE SAIR DE `apps/core` E IR PARA `apps/core_tenants`

### 3.1 — `apps/core_tenants/views.py`

**Mover de `apps/core/views.py`:**

| View/Função | Razão |
|---|---|
| `BaseMPAView` | Base view que injected `empresa_atual` — depende do tenant |
| `DashboardView` | Consulta `Venda`, `Produto`, `Categoria` — modelos de tenant |
| `SecurityHistoryView` | Mostra `AuditoriaAcesso` do utilizador — contexto de tenant |
| `TerminarOutrasSessoesView` | Gestão de sessões — funcionalidade ERP |
| `VerifyIPView` | Verificação 2FA por IP — redireccionada pela `TwoFactorIPMiddleware` (tenant) |
| `DashboardStatsAPI` | AJAX de estatísticas do dashboard — tenant |
| `NotificationListView` | Lista `NotificacaoAlerta` — modelo de tenant (analytics) |
| `NotificacaoMarcarLidaView` | AJAX marca notificação lida — tenant |
| `NotificacaoMarcarTodasLidasView` | AJAX marca todas lidas — tenant |
| `NotificacaoCountAjaxView` | AJAX polling do badge — tenant (mas com guard public) |
| `_icon_for_alerta` | Helper das notificações — vai junto |
| `_color_for_prioridade` | Helper das notificações — vai junto |

**Ficam em `apps/core/views.py` (public):**

| View/Função | Razão |
|---|---|
| `CustomLoginView` | Login — schema public |
| `LoginStatusView` | AJAX de lockout status — usada na página de login |
| `LoginUnblockView` | Admin desbloqueia IP/user — schema public |
| `logout_view` | Logout — schema public |
| `PlanoBypassView` | Painel de comissões SOTARQ — precisa de estar em ambos os schemas |
| `error_report` | Log de erros JS — ambos |
| `PWAManifestView` | manifest.json — ambos |
| `PWAOfflineView` | Página offline — ambos |
| `PWASyncOfflineView` | Background sync — ambos |
| `PWAServiceWorkerView` | Service worker — ambos |
| `verificar_seguranca_ip` (signal handler) | Regista login no `AuditoriaAcesso` — public |
| `enviar_alerta_ip_novo` | Envia email de alerta de IP — public |

---

### 3.2 — `apps/core_tenants/urls.py`

**Criar o urlconf de tenant com `app_name = 'core_tenants'` ← NOVO NAMESPACE**

```python
# apps/core_tenants/urls.py
app_name = 'core_tenants'

urlpatterns = [
    path('dashboard/',          views.DashboardView,             name='dashboard'),
    path('bypass-control/',     views.PlanoBypassView,           name='plano_bypass'),
    path('security/history/',   views.SecurityHistoryView,       name='security_history'),
    path('security/terminate/', views.TerminarOutrasSessoesView, name='terminate_sessions'),
    path('verify-device/',      views.VerifyIPView,              name='verify_ip'),
    path('notifications/',      views.NotificationListView,      name='notifications'),
    path('ajax/notifications/count/', ...,                       name='notifications_count_ajax'),
    path('ajax/notifications/<int:pk>/read/', ...,               name='notification_mark_read'),
    path('ajax/notifications/read-all/', ...,                    name='notifications_read_all'),
    path('ajax/dashboard/stats/', views.DashboardStatsAPI,       name='dashboard_stats_api'),
    # ... (todas as URLs de tenant que actualmente estão em core:urls.py)
]
```

**⚠️ ATENÇÃO — impacto:**  
Mudar o namespace de `core:dashboard` para `core_tenants:dashboard` requer  
actualizar TODAS as referências em templates, views e código que usam  
`reverse('core:dashboard')` ou `{% url 'core:dashboard' %}`.  
Isso inclui o `base.html`, `CustomLoginView.get_success_url()`, e outros. Mas isso já foi feito manualmente.


---

### 3.3 — `apps/core_tenants/middleware.py`

**Mover de `apps/core/middleware.py`:**

| Classe | Razão |
|---|---|
| `DocumentLogMiddleware` | Loga documentos de tenant |
| `ModuloAcessMiddleware` | Verifica licença do tenant |
| `LicencaVencidaMiddleware` | Bloqueia acesso por licença expirada |
| `TwoFactorIPMiddleware` | Verifica IPs conhecidos — salta schema public |

**Ficam em `apps/core/middleware.py` (public):**

| Classe | Razão |
|---|---|
| `AccountsProfileRedirectMiddleware` | Redireciona `/accounts/profile` |
| `ThreadLocalUserMiddleware` + `get_current_authenticated_user()` | Thread-local user para signals |
| `RateLimitLoginMiddleware` | Protecção da página de login |

---

### 3.4 — `apps/core_tenants/context_processors.py`

**Mover de `apps/core/context_processors.py`:**

| Função | Razão |
|---|---|
| `dashboard_data(request)` | Consulta `Lote` e `Venda` — modelos de tenant |
| `notifications_context(request)` | Consulta `NotificacaoAgendamento` e `AlertaProdutoExpiracao` |
| `modules_context(request)` | Consulta `licenca.plano.modulos` do tenant |

**Fica em `apps/core/context_processors.py` (public):**

| Função | Razão |
|---|---|
| `regime_context(request)` | Usa `request.tenant.regime` — seguro em ambos (retorna `IS_PUBLIC: True`) |

**Actualizar em `settings/base.py` — TEMPLATES context_processors:**
```python
# context_processors que consultam modelos de tenant
# devem ser movidos para a lista do TENANT_URLCONF
# ou ter guards `if IS_PUBLIC: return {}`
```

---

### 3.5 — `apps/core_tenants/permissions.py`

**Mover de `apps/core/permissions.py`:**

| Classe/Função | Razão |
|---|---|
| `EmpresaPermission` | Exige schema ≠ public |
| `EmpresaAdminPermission` | Exige `funcionario` (tenant-only) |
| `FiscalPermission` | Exige cargo fiscal (tenant) |
| `ContabilidadePermission` | Exige cargo contabilidade (tenant) |
| `empresa_required` (decorator) | Aplica `EmpresaPermission` |
| `fiscal_required` (decorator) | Aplica `FiscalPermission` |

**Ficam em `apps/core/permissions.py` (public):**

| Classe | Razão |
|---|---|
| `SuperUserPermission` | Usada em ambos |
| `ReadOnlyPermission` | Usada em ambos |
| `MultiplePermissions` | Usada em ambos |

---

### 3.6 — `apps/core_tenants/models.py`

**LIMPAR COMPLETAMENTE — não pode conter cópias dos modelos public.**

O ficheiro actual é uma cópia exacta de `apps/core/models.py` — isso é errado.  
`apps/core_tenants/models.py` deve ficar **vazio** ou conter apenas  
modelos genuinamente de tenant (se existirem no futuro).

Os modelos `Usuario`, `AuditoriaAcesso`, `IPConhecido`, `VerificacaoSeguranca`,  
`LoginAttempt` e `TimeStampedModel` ficam em `apps/core/models.py`.

---

## 4. ALTERAÇÕES AOS URLCONFS

### `config/urls_public.py` — sem alterações
Continua a incluir `apps.core.urls_login` com `namespace='core'`.

### `config/urls_tenants.py` — alterar o include do core

**Antes:**
```python
path('', include('apps.core.urls')),
```

**Depois:**
```python
# URLs de autenticação e base (do apps/core — shared)
path('', include(('apps.core.urls_login', 'core'), namespace='core')),
# URLs de tenant ERP (do apps/core_tenants)
path('', include('apps/core_tenants/urls.py')),   # app_name='core' para manter namespace
```

**Razão:** separar explicitamente o que é public do que é tenant.  
O `urls_login.py` do core (com login/logout/PWA/reset) cobre o que  
o schema tenant também precisa da app core. As views de ERP  
(dashboard, notificações, etc.) vêm do `core_tenants`.

---

## 5. ALTERAÇÕES AOS SETTINGS

### `settings/base.py` — MIDDLEWARE

Remover de `MIDDLEWARE`:
```python
'apps.core.middleware.ModuloAcessMiddleware',
'apps.core.middleware.TwoFactorIPMiddleware',
```

Adicionar (apontar para `core_tenants`):
```python
'apps.core_tenants.middleware.ModuloAcessMiddleware',
'apps.core_tenants.middleware.TwoFactorIPMiddleware',
```

**Nota:** `DocumentLogMiddleware` e `LicencaVencidaMiddleware` devem  
ser avaliados — se estiverem a ser usados, migram para `core_tenants`.

### `settings/base.py` — TEMPLATES context_processors

Mover os 3 context_processors de tenant para `core_tenants`:
```python
# Antes:
'apps.core.context_processors.dashboard_data',
'apps.core.context_processors.notifications_context',
'apps.core.context_processors.modules_context',

# Depois:
'apps.core_tenants.context_processors.dashboard_data',
'apps.core_tenants.context_processors.notifications_context',
'apps.core_tenants.context_processors.modules_context',
```

---

## 6. REFERÊNCIAS A ACTUALIZAR APÓS A MIGRAÇÃO

Qualquer ficheiro que importe de `apps.core.views` para views de tenant  
precisa de passar a importar de `apps.core_tenants.views`.

Ficheiros afectados (amostra):
- `templates/base.html` — se usar `{% url 'core:dashboard' %}` e o namespace mudar
- `apps/core/views.py` — `CustomLoginView.get_success_url()` usa `reverse_lazy('core:dashboard')`
- `config/urls_tenants.py` — include do `apps.core`
- Todos os templates que usem `{% url 'core:verify_ip' %}`, `{% url 'core:security_history' %}`, etc.

**Se mantivermos `app_name = 'core'` em `core_tenants/urls.py`:**  
Nenhuma referência de template ou view precisa de mudar — os nomes  
`core:dashboard`, `core:notifications`, etc. continuam iguais.  
Só os imports Python nas views mudam.

---

## 7. SEQUÊNCIA DE IMPLEMENTAÇÃO RECOMENDADA

```
Passo 1: Limpar apps/core_tenants/models.py (remover cópia)
Passo 2: Criar apps/core_tenants/views.py com as views de tenant
Passo 3: Criar apps/core_tenants/urls.py com app_name='core'
Passo 4: Criar apps/core_tenants/context_processors.py com as 3 funções de tenant
Passo 5: Criar apps/core_tenants/middleware.py com os 4 middlewares de tenant
Passo 6: Criar apps/core_tenants/permissions.py com as permissões de tenant
Passo 7: Actualizar config/urls_tenants.py
Passo 8: Actualizar settings/base.py (MIDDLEWARE + context_processors)
Passo 9: Actualizar apps/core/views.py (remover o que foi para core_tenants)
Passo 10: Actualizar apps/core/middleware.py (remover middlewares de tenant)
Passo 11: Actualizar apps/core/context_processors.py (remover funções de tenant)
Passo 12: Verificar todos os imports em apps que referenciam apps.core.views para views de tenant
Passo 13: Executar manage.py check + migrate_schemas
```

---

## 8. FICHEIROS DE TENANT NÃO AFECTADOS (ficam onde estão)

- `apps/core/templatetags/pharma_tags.py` — fica em core (SHARED_APPS pode servir templatetags)
- `apps/core/services/rate_limit_service.py` — fica em core (rate limit é público)
- `apps/core/services/captcha_service.py` — fica em core (captcha é público)
- `apps/core/models.py` — fica em core (todos os modelos são shared/public)
- `apps/core/signals.py` — fica em core (o sinal `user_logged_in` é público)
- `apps/core/static/js/service-worker.js` — fica em core

---

## 9. RISCOS E CONSIDERAÇÕES

| Risco | Mitigação |
|---|---|
| Namespace `core` duplicado se `core_tenants/urls.py` usar `app_name='core'` | Testar com `python manage.py check` após cada passo |
| Imports circulares entre `core` e `core_tenants` | `core_tenants` importa de `core` (modelos, serviços); `core` NUNCA importa de `core_tenants` |
| Templates que usem `{% url 'core:verify_ip' %}` e a view mude de app | Se namespace se mantiver `core`, não há impacto |
| `AuditoriaAcesso` necessário em views de `core_tenants` | Import directo de `apps.core.models` — sem problema |
| `context_processors` de tenant sendo executados no schema public | Adicionar guard `if connection.schema_name == 'public': return {}` em cada um |

---

## 10. RESULTADO ESPERADO

Após aplicar este plano:
- `http://mundoemaquinas.localhost/dashboard/` → usa `core_tenants.views.DashboardView`  
  → resolver activo conhece `vendas`, `produtos`, etc.  
  → `{% safe_url 'vendas:pdv' %}` resolve correctamente → link funcional
- `http://localhost/login/` → usa `core.views.CustomLoginView`  
  → resolver activo só conhece namespace `core`  
  → `{% safe_url 'vendas:pdv' %}` não resolve → retorna `'#'` correctamente (menu não visível no login)
- Todos os botões e links do `base.html` funcionam no schema tenant

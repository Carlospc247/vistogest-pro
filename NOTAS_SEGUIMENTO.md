# Notas de seguimento — migração apps/core → apps/core_tenants

## 1. Remover de `apps/core/views.py`

Apagar por completo as seguintes classes/funções (foram para `core_tenants/views.py`):
`BaseMPAView`, `SecurityHistoryView`, `TerminarOutrasSessoesView`, `VerifyIPView`,
`DashboardStatsAPI`, `NotificationListView`, `NotificacaoMarcarLidaView`,
`NotificacaoMarcarTodasLidasView`, `NotificacaoCountAjaxView`, `_icon_for_alerta`,
`_color_for_prioridade`.

Ficam em `apps/core/views.py`: `PlanoBypassView`, `CustomLoginView`, `logout_view`,
`verificar_seguranca_ip` (+ `enviar_alerta_ip_novo`), `LoginStatusView`,
`LoginUnblockView`, `error_report`, `PWAManifestView`, `PWAOfflineView`,
`PWASyncOfflineView`, `PWAServiceWorkerView`.

Depois de remover, os imports no topo de `apps/core/views.py` que só serviam as
views removidas também podem ser limpos (ex.: `NotificacaoAgendamento`,
`NotificacaoAlerta`, `EventoAnalytics`, `AuditoriaInvestimento`, `Lote`, `Session`,
`VerificacaoSeguranca`, `IPConhecido` deixam de ser necessários em `core/views.py`
se nada mais ali os usar).

## 2. Remover de `apps/core/middleware.py`

Apagar: `DocumentLogMiddleware`, `ModuloAcessMiddleware`, `LicencaVencidaMiddleware`,
`TwoFactorIPMiddleware`. Também remover o import `from .models import IPConhecido,
VerificacaoSeguranca` se nada mais os usar ali.

Ficam: `AccountsProfileRedirectMiddleware`, `ThreadLocalUserMiddleware` +
`get_current_authenticated_user()`, `RateLimitLoginMiddleware`.

**Bug à parte, independente desta migração**: `get_current_authenticated_user()`
está definida **duas vezes seguidas** em `apps/core/middleware.py` (idêntica).
Apagar a segunda definição — é código morto inofensivo, mas confunde leitura.

## 3. Remover de `apps/core/context_processors.py`

Apagar: `dashboard_data`, `notifications_context`, `modules_context`.
Fica: `regime_context`.

Depois de remover, os imports `NotificacaoAgendamento`, `Venda`, `Lote`,
`AlertaProdutoExpiracao` deixam de ser necessários em `core/context_processors.py`.

## 4. Remover de `apps/core/permissions.py`

Apagar: `EmpresaPermission`, `EmpresaAdminPermission`, `FiscalPermission`,
`ContabilidadePermission`, `empresa_required`, `fiscal_required`.
Ficam: `SuperUserPermission`, `ReadOnlyPermission`, `MultiplePermissions`.

## 5. ⚠️ `apps/core/urls_login.py` tem um conflito que o plano original não previu

O ficheiro que já tens (`urls_login.py`) inclui estas rotas que apontam para
views que **saem** de `apps.core.views`:

```python
path('bypass-control/', views.PlanoBypassView.as_view(), name='plano_bypass'),  # fica — OK
path('notifications/', views.NotificationListView.as_view(), name='notifications'),  # MOVE — quebra
path('ajax/notifications/count/', views.NotificacaoCountAjaxView.as_view(), ...),  # MOVE — quebra
path('ajax/notifications/<int:pk>/read/', views.NotificacaoMarcarLidaView.as_view(), ...),  # MOVE — quebra
path('ajax/notifications/read-all/', views.NotificacaoMarcarTodasLidasView.as_view(), ...),  # MOVE — quebra
```

Como `NotificationListView` e as 3 views de notificações AJAX deixam de existir
em `apps.core.views`, estas 4 linhas vão causar `AttributeError` no arranque do
Django assim que remover as classes de `core/views.py`. **Apagar estas 4 linhas
de `urls_login.py`** — faz sentido de qualquer forma, pois o schema `public`
(login) não tem os modelos de tenant que essas views consultam. `bypass-control/`
fica, porque `PlanoBypassView` continua em `apps.core.views`.

## 6. `settings/base.py`

```python
# MIDDLEWARE — trocar:
'apps.core.middleware.ModuloAcessMiddleware',
'apps.core.middleware.TwoFactorIPMiddleware',
# por:
'apps.core_tenants.middleware.ModuloAcessMiddleware',
'apps.core_tenants.middleware.TwoFactorIPMiddleware',

# Se LicencaVencidaMiddleware e DocumentLogMiddleware estiverem de facto
# activos no MIDDLEWARE (não estavam na lista partilhada até agora — ver
# "NÃO VERIFICADO" no CLAUDE.md), apontar também para apps.core_tenants.*

# TEMPLATES → OPTIONS → context_processors — trocar:
'apps.core.context_processors.dashboard_data',
'apps.core.context_processors.notifications_context',
'apps.core.context_processors.modules_context',
# por:
'apps.core_tenants.context_processors.dashboard_data',
'apps.core_tenants.context_processors.notifications_context',
'apps.core_tenants.context_processors.modules_context',

# INSTALLED_APPS / TENANT_APPS — confirmar que 'apps.core_tenants' já lá está
# (a tua mensagem diz que sim, "já em TENANT_APPS")
```

## 7. `config/urls_tenants.py`

```python
# Antes:
path('', include('apps.core.urls')),

# Depois:
path('', include(('apps.core.urls_login', 'core'), namespace='core')),
path('', include('apps.core_tenants.urls')),
```

(Nota: a sintaxe `include('apps/core_tenants/urls.py')` que aparecia no teu
plano original tem erro de sintaxe — o segundo argumento de `include()` é um
caminho de módulo Python com pontos, `'apps.core_tenants.urls'`, não um
caminho de ficheiro. `core_tenants/urls.py` já define `app_name = 'core_tenants'`
no próprio ficheiro, por isso basta `include('apps.core_tenants.urls')` sem
precisar de passar namespace explícito — o Django usa o `app_name` do módulo.)

## 8. ⚠️ Maior impacto fora de `apps/core` — imports de permissões em todo o resto do sistema

Isto não estava coberto no `PLANO_CORE_TENANT.md`, mas é uma consequência directa
dele: qualquer ficheiro em `apps/vendas`, `apps/fiscal`, etc. que hoje faça

```python
from apps.core.permissions import EmpresaPermission, FiscalPermission, ContabilidadePermission, EmpresaAdminPermission
from apps.core.permissions import empresa_required, fiscal_required
```

tem de passar a importar de `apps.core_tenants.permissions` para essas 6
funções/classes especificamente. `MultiplePermissions`, `SuperUserPermission` e
`ReadOnlyPermission` continuam em `apps.core.permissions` sem alteração — só
estas 6 mudam de módulo.

Já confirmei nos ficheiros `apps/fiscal/views.py` e `apps/vendas/views.py` que
já vi nesta conversa que ambos fazem `from apps.core.permissions import
MultiplePermissions, EmpresaPermission, FiscalPermission` em várias linhas —
**estes dois ficheiros, no mínimo, vão rebentar** assim que `EmpresaPermission`/
`FiscalPermission` saírem de `apps.core.permissions`, até esses imports serem
actualizados para `apps.core_tenants.permissions`.

**Acção recomendada**: antes de apagar as classes de `apps/core/permissions.py`
(passo 4), fazer uma busca global por `from apps.core.permissions import` em
todo o projecto e corrigir cada ocorrência que use alguma das 6 classes/funções
movidas. Só depois apagar as classes de `apps/core/permissions.py` — para não
teres uma janela de tempo em que o projecto não arranca.

## 9. `DashboardView` — corpo em falta

`core_tenants/views.py` tem um placeholder para `DashboardView` porque o corpo
real desta view não estava em nenhum ficheiro partilhado nesta sessão (só era
referenciada via `reverse_lazy`/`redirect`, nunca definida). Se já existir
noutro lado do projecto, substitui o placeholder por essa versão real; se não
existir ainda, o placeholder pelo menos evita `AttributeError` no arranque
enquanto a constróis.
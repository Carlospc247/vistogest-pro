# Esclarecimentos — Resultados dos Comandos
## VistoGest Pro / SOTARQ Software

---

## 1. O que aconteceu quando correste os comandos

Correste três comandos. Cada um teve um resultado diferente. Explico cada um abaixo.

---

## 2. `.\iniciar_infra.ps1` — CORREU BEM ✅

```
✅ Celery Worker e Beat iniciados em janelas separadas.
```

**O que significa:**
O script abriu dois terminais PowerShell separados — um para o **Celery Worker** e outro para o **Celery Beat**. Ambos arrancaram correctamente do ponto de vista do sistema operativo.

**O que é o Celery Worker:**
É o processo que fica à escuta de tarefas assíncronas — por exemplo, quando o sistema precisa de enviar uma fatura para a AGT sem bloquear o utilizador. Ele recebe a tarefa da fila Redis e executa-a em background.

**O que é o Celery Beat:**
É o agendador interno. Funciona como um "cron" — dispara automaticamente tarefas agendadas nas horas certas (ex.: polling de estado AGT a cada 15 min, backup às 02h00, expiração de licenças de parceiros às 03h30).

**Por que é que aparece o erro de Redis nos terminais:**
O Worker e o Beat arrancaram, mas **o Redis não está a correr**. O Celery tenta ligar ao Redis (que é a "fila" onde as mensagens ficam guardadas) e não consegue porque o servidor Redis não está activo. Por isso repete:
```
Cannot connect to redis://localhost:6379/0: Error 10061 ...
Trying again in X seconds... (N/100)
```
Isso **não é um crash** — o Celery está a tentar ligar de 2 em 2 segundos, depois de 4 em 4, depois de 6 em 6... até 100 tentativas. Assim que o Redis arrancar, vai ligar automaticamente.

**Como resolver o Redis no Windows:**
Tens duas opções:

```powershell
# Opção A — Docker (recomendado, mais simples)
docker run -d -p 6379:6379 --name redis-vistogest redis:7-alpine

# Opção B — Redis for Windows (se tiveres instalado)
# Procurar "Redis" no menu iniciar e arrancar o serviço
```

**Confirmação de que o Redis arrancou:**
```powershell
# Testar se o Redis responde
docker exec redis-vistogest redis-cli ping
# Deve responder: PONG
```

---

## 3. `python manage.py migrate_schemas --schema=public` — ERRO ❌

```
SystemCheckError: System check identified some issues:

ERRORS:
<class 'apps.parceiros.admin.PartnerClientInline'>: (admin.E202)
'parceiros.PartnerClient' has more than one ForeignKey to 'parceiros.Partner'.
You must specify a 'fk_name' attribute.
```

**O que significa:**
Antes de aplicar qualquer migração, o Django verifica o código todo para garantir que está consistente. Encontrou um erro no ficheiro `apps/parceiros/admin.py`.

**Qual era o problema:**
O modelo `PartnerClient` tem **dois campos** que apontam para `Partner`:
- `partner` — o parceiro actual responsável pelo cliente
- `parceiro_anterior` — histórico: quem era o parceiro antes de uma transferência

Quando o Django Admin tenta criar o `PartnerClientInline` (a tabela de clientes que aparece dentro da ficha do parceiro), ele não sabe qual dos dois campos usar para mostrar os clientes. Por isso dá erro.

**O que foi corrigido agora:**
Adicionei `fk_name = 'partner'` ao `PartnerClientInline`, dizendo explicitamente ao Django para usar o campo `partner` (o actual) e não o `parceiro_anterior`.

```python
# Antes (com erro):
class PartnerClientInline(admin.TabularInline):
    model = PartnerClient
    ...

# Depois (corrigido):
class PartnerClientInline(admin.TabularInline):
    model   = PartnerClient
    fk_name = 'partner'   # ← diz qual FK usar
    ...
```

**Este erro foi corrigido nesta sessão.** Podes re-executar o comando.

---

## 4. `python manage.py migrate` — MESMO ERRO ❌

Este comando falhou pelo mesmo motivo que o anterior. O Django faz o system check antes de qualquer operação. Com o `admin.py` corrigido, este comando também vai funcionar.

---

## 5. Terminal do Celery Worker — O que vês

```
-------------- celery@Carlos-Pc v5.5.3 (immunity)
--- ***** -----
-- ******* ---- Windows-11-10.0.22000-SP0 2026-10-01 01:05:11
```

**O que é:**
O Celery identifica-se com o nome da máquina (`Carlos-Pc`) e a versão (`5.5.3`). O nome de código da versão é "immunity" — é só um nome criativo que os criadores do Celery dão a cada versão, como o Linux nomeia as versões com animais.

```
.> transport:   redis://localhost:6379/0
.> results:     redis://localhost:6379/0
.> concurrency: 4 (solo)
```

**O que significa:**
- `transport` — onde o Worker vai buscar as tarefas (Redis, porta 6379, base de dados 0)
- `results` — onde guarda os resultados das tarefas (também no Redis)
- `concurrency: 4 (solo)` — está a usar 4 processos paralelos no modo "solo" (específico para Windows, porque o multiprocessing normal do Python não funciona bem no Windows)

```
[tasks]
  . apps.configuracoes.tasks.backup_automatico_diario
  . fiscal.polling_estado_agt
  . fiscal.submeter_fatura_agt
  . parceiros.expirar_licencas_global
  ...
```

**O que é:**
Lista de todas as tarefas registadas que este Worker sabe executar. Inclui as tarefas do módulo fiscal (submeter facturas à AGT, polling), do módulo de parceiros (expirar licenças) e outras tarefas da aplicação. Isto confirma que o teu código foi carregado correctamente.

```
ERROR/MainProcess] consumer: Cannot connect to redis://localhost:6379/0
Trying again in 2.00 seconds... (1/100)
```

**O que é:**
O Worker está activo mas não consegue ligar ao Redis. Está a tentar de 2 em 2 segundos com backoff exponencial (2s, 4s, 6s, 8s...). Assim que o Redis arrancar, liga automaticamente sem precisar de reiniciar o Worker.

---

## 6. Terminal do Celery Beat — O que vês

```
celery beat v5.5.3 (immunity) is starting.
LocalTime -> 2026-10-01 01:05:08
.> broker -> redis://localhost:6379/0
.> scheduler -> celery.beat.PersistentScheduler
.> db -> celerybeat-schedule
beat: Starting...
```

**O que é:**
O Beat arrancar com sucesso. Está configurado para:
- Ligar ao Redis para enviar as tarefas agendadas
- Usar o `PersistentScheduler` — guarda o estado num ficheiro `celerybeat-schedule` no disco, para saber quando foi a última vez que cada tarefa correu (evita disparar a mesma tarefa duas vezes após um restart)
- `LocalTime` — o horário é Africa/Luanda conforme configurado no `CELERY_TIMEZONE`

O Beat não dá erro de ligação porque ele apenas **agenda** as tarefas — envia-as para a fila Redis quando está na hora. O Worker é que precisa de estar ligado para as executar. Quando o Redis arrancar, o Beat vai começar a enviar as tarefas agendadas.

---

## 7. Resumo — O que fazer agora

### Passo 1 — Iniciar o Redis

```powershell
# Com Docker (mais simples):
docker run -d -p 6379:6379 --name redis-vistogest redis:7-alpine

# Confirmar que está activo:
docker ps | Select-String redis
```

### Passo 2 — Aplicar as migrações (com o Redis a correr ou sem ele — não é necessário para migrações)

```powershell
# O Redis NÃO é necessário para as migrações — só para o Celery.
# Podes correr as migrações sem Redis activo:

python manage.py migrate_schemas --schema=public --settings=config.settings.development
python manage.py migrate --settings=config.settings.development
```

### Passo 3 — Iniciar o servidor Django

```powershell
python manage.py runserver --settings=config.settings.development
```

### Passo 4 — Aceder ao sistema

```
http://localhost:8000           → área pública
http://mundoemaquinas.localhost:8000  → tenant mundoemaquinas
```

---

## 8. Diagrama do que está a correr e do que falta

```
Estado actual:
                                    
  [Celery Worker]  ──────────────────────╮
       ✅ Iniciado                       │  Tentando ligar...
       ❌ Sem Redis                      │
                                         ▼
  [Celery Beat]    ──────────────────►  [Redis]
       ✅ Iniciado                        ❌ NÃO ESTÁ A CORRER
       ❌ Sem Redis
  
  [Django Server]  ──── ❌ Não foi iniciado ainda
  
  [Migrações]      ──── ❌ Bloqueadas pelo erro do admin (já corrigido)

Estado depois de iniciar o Redis e re-executar:

  [Redis]          ──── ✅ Activo na porta 6379
       ↑
  [Celery Worker]  ──── ✅ Liga automaticamente ao Redis
  [Celery Beat]    ──── ✅ Começa a disparar tarefas agendadas
  
  [Migrações]      ──── ✅ Correm sem erro (admin.E202 corrigido)
  [Django Server]  ──── ✅ Arranca e serve pedidos
```

---

## 9. O erro `admin.E202` — Porquê aconteceu

Este erro existia no código mas só é detectado quando o Django faz um `system check` — que acontece antes de qualquer `manage.py migrate`, `manage.py runserver`, etc.

**Causa:** `PartnerClient` tem dois campos FK para `Partner` (`partner` e `parceiro_anterior`) porque o modelo foi desenhado para preservar o histórico de transferências de clientes entre parceiros. O Django Admin não consegue escolher automaticamente qual usar para o inline.

**Correcção aplicada:** `fk_name = 'partner'` no `PartnerClientInline` do `apps/parceiros/admin.py`.

**Lição:** Sempre que um modelo tem mais de uma FK para o mesmo modelo pai e é usado num Inline do Admin, é obrigatório especificar o `fk_name`.

---

## 10. Verificação final após correcções

Depois de iniciar o Redis e re-executar as migrações, verifica com:

```powershell
# Auditoria de integridade
python auditar_integridade.py

# Verificar settings
python check_settings.py

# Verificar sistema Django
python manage.py check --settings=config.settings.development
```

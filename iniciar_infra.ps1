# ==============================================================================
# iniciar_infra.ps1 — VistoGest Pro / SOTARQ Software
# Ambiente: Windows PowerShell (desenvolvimento local)
# Objectivo: Iniciar os processos de segundo plano necessários para o sistema.
#
# O servidor Django (manage.py runserver) responde apenas a pedidos HTTP
# do browser. Operações pesadas ou agendadas — assinaturas fiscais RSA para
# a AGT, envio de emails, polling de estado de facturas, backups automáticos
# — precisam correr em background para não bloquear o utilizador.
# Esses processos são geridos pelo Celery:
#   • Celery Worker: executa as tarefas assíncronas à medida que chegam.
#   • Celery Beat:  actua como um "cron" interno, disparando tarefas agendadas
#                  (ex.: polling AGT a cada 15 min, backup diário às 02h00).
#
# Pré-condições:
#   1. Redis em execução (Docker: `docker run -p 6379:6379 redis` ou serviço Windows).
#   2. Ambiente virtual criado em .\venv\.
#   3. Dependências instaladas: pip install -r requirements.txt
#
# Uso:
#   .\iniciar_infra.ps1
#   (Se falhar por política de execução: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
# ==============================================================================

Write-Host "--- INICIANDO INFRAESTRUTURA SOTARQ (MODO DEV) ---" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# Caminhos e configurações
# ------------------------------------------------------------------------------

# Caminho para o executável Python dentro do ambiente virtual
$PYTHON_EXE = ".\venv\Scripts\python.exe"

# Módulo de settings a usar (desenvolvimento local)
$SETTINGS_MODULE = "config.settings.development"

# ------------------------------------------------------------------------------
# Validação do ambiente virtual
# ------------------------------------------------------------------------------

# Verificar se o ambiente virtual existe antes de tentar usar
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Error "❌ ERRO: Ambiente virtual não encontrado em '.\venv'."
    Write-Error "   Crie o venv primeiro: python -m venv venv && .\venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# Exportar o módulo de settings para os processos filhos que vão ser criados
$env:DJANGO_SETTINGS_MODULE = $SETTINGS_MODULE

# ------------------------------------------------------------------------------
# 1. Celery Worker — processa tarefas assíncronas
# ------------------------------------------------------------------------------
# -A config.tasks_celery  : aplicação Celery definida em config/tasks_celery.py
# worker                   : modo worker (consome tarefas da fila Redis)
# --loglevel=info          : nível de log (info mostra tarefas recebidas/concluídas)
# -P solo                  : pool "solo" (single-thread) — necessário no Windows
#                            porque o multiprocessing padrão do Celery não funciona
#                            correctamente em Windows sem este flag.
# O processo é aberto numa nova janela PowerShell para não bloquear este terminal.
Write-Host "[1/2] A lançar Celery Worker (tarefas assíncronas — JWS, emails, AGT)..." -ForegroundColor Yellow
$workerCmd = "chcp 65001; `$env:DJANGO_SETTINGS_MODULE='$SETTINGS_MODULE'; & '$PYTHON_EXE' -m celery -A config.tasks_celery worker --loglevel=info -P solo"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $workerCmd

# ------------------------------------------------------------------------------
# 2. Celery Beat — agendador de tarefas periódicas
# ------------------------------------------------------------------------------
# beat                     : modo beat (dispara tarefas segundo o CELERY_BEAT_SCHEDULE)
# --loglevel=info          : nível de log
# Tarefas agendadas activas (ver config/settings/base.py CELERY_BEAT_SCHEDULE):
#   • polling-estado-agt-15-minutos    — consulta estado de facturas na AGT
#   • sincronizar-series-agt-diario    — sincroniza séries com a AGT às 03h00
#   • backup_diario                    — backup automático às 02h00
#   • verificar_margem_critica_diaria  — alertas de margem crítica
#   • verificar_stock_critico_horario  — alertas de stock a cada hora
Write-Host "[2/2] A lançar Celery Beat (tarefas agendadas — polling AGT, backups)..." -ForegroundColor Yellow
$beatCmd = "chcp 65001; `$env:DJANGO_SETTINGS_MODULE='$SETTINGS_MODULE'; & '$PYTHON_EXE' -m celery -A config.tasks_celery beat --loglevel=info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $beatCmd

# ------------------------------------------------------------------------------
# Mensagem final
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "---------------------------------------------------" -ForegroundColor Gray
Write-Host "✅ Celery Worker e Beat iniciados em janelas separadas." -ForegroundColor Green
Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor White
Write-Host "  • Certifique-se de que o Redis está activo." -ForegroundColor Gray
Write-Host "    Docker: docker run -d -p 6379:6379 redis" -ForegroundColor Gray
Write-Host "  • Inicie o servidor Django:" -ForegroundColor Gray
Write-Host "    python manage.py runserver 8080 --settings=config.settings.development" -ForegroundColor Gray
Write-Host "  • Aceda ao sistema em: http://localhost:8080" -ForegroundColor Gray
Write-Host "---------------------------------------------------" -ForegroundColor Gray

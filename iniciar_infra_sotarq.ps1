# SOTARQ VENDOR - Script de Inicialização de Infraestrutura
Write-Host "--- INICIANDO INFRAESTRUTURA SOTARQ (MODO DEV) ---" -ForegroundColor Cyan

# 1. Ativar Ambiente Virtual
$VENV_PATH = ".\venv\Scripts\Activate.ps1"
if (Test-Path $VENV_PATH) {
    & $VENV_PATH
} else {
    Write-Error "Ambiente virtual (venv) não encontrado!"
    exit
}

# 2. Iniciar Worker do Celery (Para Assinaturas RSA)
Write-Host "[1/2] Lançando Celery Worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "chcp 65001; & '$VENV_PATH'; celery -A pharmassys.tasks_celery worker --loglevel=info -P solo"

# 3. Iniciar Celery Beat (Para Polling AGT e Backups)
Write-Host "[2/2] Lançando Celery Beat..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "chcp 65001; & '$VENV_PATH'; celery -A pharmassys.tasks_celery beat --loglevel=info"

Write-Host "---------------------------------------------------"
Write-Host "🚀 SUCESSO: Worker e Beat rodando em janelas separadas." -ForegroundColor Green
Write-Host "Dica: Mantenha o Redis rodando no Docker ou Windows." -ForegroundColor White
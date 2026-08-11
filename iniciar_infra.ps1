
# Esse script serve para ligar os motores de segundo plano do SOTARQ VENDOR no seu ambiente de desenvolvimento.
"""
Quando o servidor web do Django está a rodar, ele cuida apenas de responder às requisições do navegador.
No entanto, operações pesadas ou agendadas — como gerar assinaturas fiscais RSA para a AGT, enviar e-mails ou 
rodar rotinas automáticas — precisam acontecer em segundo plano para não travar a navegação do utilizador.

"""
# ==============================================================================
# SOTARQ VENDOR - Script de Inicialização de Infraestrutura (Modo Desenvolvimento)
# ==============================================================================

Write-Host "--- INICIANDO INFRAESTRUTURA SOTARQ (MODO DEV) ---" -ForegroundColor Cyan

# 1. Definir caminhos do ambiente virtual e configurações
$PYTHON_EXE = ".\venv\Scripts\python.exe"
$SETTINGS_MODULE = "config.settings.development"

# Validar se o ambiente virtual existe
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Error "❌ ERRO: Ambiente virtual não encontrado em '.\venv'. Certifique-se de ter criado o venv!"
    exit
}

# Configurar variável no processo principal
$env:DJANGO_SETTINGS_MODULE = $SETTINGS_MODULE

# 2. Iniciar Worker do Celery (Assinaturas RSA, Faturação e Tarefas Assíncronas)
Write-Host "[1/2] Lançando Celery Worker..." -ForegroundColor Yellow
$workerCommand = "chcp 65001; `$env:DJANGO_SETTINGS_MODULE='$SETTINGS_MODULE'; & '$PYTHON_EXE' -m celery -A config.tasks_celery worker --loglevel=info -P solo"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $workerCommand

# 3. Iniciar Celery Beat (Polling AGT, Tarefas Agendadas e Backups)
Write-Host "[2/2] Lançando Celery Beat..." -ForegroundColor Yellow
$beatCommand = "chcp 65001; `$env:DJANGO_SETTINGS_MODULE='$SETTINGS_MODULE'; & '$PYTHON_EXE' -m celery -A config.tasks_celery beat --loglevel=info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $beatCommand

Write-Host "---------------------------------------------------" -ForegroundColor Gray
Write-Host "🚀 SUCESSO: Celery Worker e Beat disparados em janelas dedicadas." -ForegroundColor Green
Write-Host "ℹ️ Nota: Certifique-se de que o serviço Redis está ativo (Docker ou Windows Service)." -ForegroundColor White

# .\iniciar_infra.ps1
# (Se o PowerShell bloquear por política de execução, utilize: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass antes de rodar
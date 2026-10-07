#!/usr/bin/env bash
# ==============================================================================
# iniciar_infra.sh — VistoGest Pro / SOTARQ Software
# Ambiente: Linux / produção (Render, VPS, Docker, etc.)
# Objectivo: Iniciar Celery Worker e Beat em background.
#
# Este script destina-se a ambientes Linux onde o iniciar_infra.ps1
# (Windows PowerShell) não está disponível.
# Em produção com Render/Heroku, prefira o Procfile.
# Use este script em VPS/Docker onde gere os processos manualmente.
#
# Pré-condições:
#   1. Redis acessível (variável CELERY_BROKER_URL ou REDIS_URL definida).
#   2. Virtualenv activado OU dependências instaladas no Python do sistema.
#   3. DJANGO_SETTINGS_MODULE definido (ou passado como argumento).
#
# Uso:
#   bash iniciar_infra.sh                           # usa production por defeito
#   DJANGO_SETTINGS_MODULE=config.settings.development bash iniciar_infra.sh
#
# Para parar os processos:
#   kill $(cat /tmp/celery_worker.pid)
#   kill $(cat /tmp/celery_beat.pid)
# ==============================================================================

set -e  # Parar imediatamente se qualquer comando falhar

# ------------------------------------------------------------------------------
# Configuração
# ------------------------------------------------------------------------------

# Usar settings de produção por defeito; pode ser sobreposto pela variável de ambiente
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

# Directório de logs — criar se não existir
LOG_DIR="${LOG_DIR:-/var/log/vistogest}"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="/tmp"

# Ficheiros PID para identificar os processos e poder pará-los depois
WORKER_PID="/tmp/celery_worker.pid"
BEAT_PID="/tmp/celery_beat.pid"

echo "================================================================"
echo " VistoGest Pro — Iniciando infraestrutura de background"
echo " Settings: $DJANGO_SETTINGS_MODULE"
echo " Logs:     $LOG_DIR"
echo "================================================================"

# ------------------------------------------------------------------------------
# Parar processos anteriores (se existirem)
# ------------------------------------------------------------------------------
# Evita múltiplas instâncias a correr em simultâneo após um restart

if [ -f "$WORKER_PID" ]; then
    OLD_PID=$(cat "$WORKER_PID")
    # kill -0 verifica se o processo existe sem o matar
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[INFO] A parar worker anterior (PID $OLD_PID)..."
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "$WORKER_PID"
fi

if [ -f "$BEAT_PID" ]; then
    OLD_PID=$(cat "$BEAT_PID")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[INFO] A parar beat anterior (PID $OLD_PID)..."
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "$BEAT_PID"
fi

# ------------------------------------------------------------------------------
# 1. Celery Worker
# ------------------------------------------------------------------------------
# -A config.tasks_celery  : módulo Celery (config/tasks_celery.py)
# worker                   : modo worker
# --loglevel=info          : nível de log
# --concurrency=2          : 2 processos worker (ajustar conforme RAM disponível)
# --pidfile                : ficheiro PID para controlo do processo
# --logfile                : ficheiro de log (rotacionado pelo logrotate em produção)
# &                        : executar em background

echo "[1/2] A iniciar Celery Worker..."
python -m celery \
    -A config.tasks_celery worker \
    --loglevel=info \
    --concurrency=2 \
    --pidfile="$WORKER_PID" \
    --logfile="$LOG_DIR/celery_worker.log" \
    &
WORKER_LAUNCHED_PID=$!
echo "  PID: $WORKER_LAUNCHED_PID | Log: $LOG_DIR/celery_worker.log"

# ------------------------------------------------------------------------------
# 2. Celery Beat
# ------------------------------------------------------------------------------
# beat                     : modo agendador (dispara tarefas via CELERY_BEAT_SCHEDULE)
# --loglevel=info          : nível de log
# --pidfile                : ficheiro PID
# --logfile                : ficheiro de log
# --schedule               : ficheiro de estado do beat (evita re-disparar tarefas
#                            após restart dentro da mesma janela de agendamento)
# &                        : background

echo "[2/2] A iniciar Celery Beat..."
python -m celery \
    -A config.tasks_celery beat \
    --loglevel=info \
    --pidfile="$BEAT_PID" \
    --logfile="$LOG_DIR/celery_beat.log" \
    --schedule=/tmp/celerybeat-schedule \
    &
echo "  PID: $! | Log: $LOG_DIR/celery_beat.log"

# ------------------------------------------------------------------------------
# Confirmação
# ------------------------------------------------------------------------------
sleep 1  # Dar 1 segundo para os processos arrancarem

echo ""
echo "================================================================"
echo "✅ Celery Worker e Beat iniciados com sucesso."
echo ""
echo "Para verificar:"
echo "  ps aux | grep celery"
echo ""
echo "Para ver logs em tempo real:"
echo "  tail -f $LOG_DIR/celery_worker.log"
echo "  tail -f $LOG_DIR/celery_beat.log"
echo ""
echo "Para parar:"
echo "  kill \$(cat $WORKER_PID) && kill \$(cat $BEAT_PID)"
echo "================================================================"

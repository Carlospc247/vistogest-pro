#!/usr/bin/env python
"""
check_settings.py — VistoGest Pro / SOTARQ Software
Diagnóstico completo das configurações e dependências do sistema.

Uso:
    python check_settings.py                         # auto-detecta ambiente
    DJANGO_SETTINGS_MODULE=config.settings.production python check_settings.py

O ambiente é detectado automaticamente:
    • Variável RENDER definida    → config.settings.production
    • Variável ENV_MODE=production → config.settings.production
    • Caso contrário              → config.settings.development
"""
import os
import sys
import re

# ──────────────────────────────────────────────────────────────────────────────
# Cores ANSI (sem dependências externas)
# ──────────────────────────────────────────────────────────────────────────────
GREEN  = '\033[32m'
RED    = '\033[31m'
YELLOW = '\033[33m'
CYAN   = '\033[36m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

def ok(msg):   print(f"  {GREEN}✔{RESET} {msg}")
def err(msg):  print(f"  {RED}✘{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg): print(f"  {CYAN}ℹ{RESET} {msg}")

def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

# ──────────────────────────────────────────────────────────────────────────────
# 1. Detectar ambiente antes de carregar o Django
# ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if os.environ.get('RENDER') or os.environ.get('ENV_MODE', '').lower() == 'production':
    settings_module = 'config.settings.production'
else:
    settings_module = 'config.settings.development'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings_module)

print(f"\n{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
print(f"{BOLD}║       VistoGest Pro — Diagnóstico de Configurações       ║{RESET}")
print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")
info(f"Módulo de settings: {os.environ['DJANGO_SETTINGS_MODULE']}")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Variáveis de ambiente críticas (antes de carregar o Django)
# ──────────────────────────────────────────────────────────────────────────────
section("Variáveis de Ambiente")

env_checks = [
    ('SECRET_KEY',                   'Django Secret Key',           50, True),
    ('AES_KEY',                      'Chave AES (cifrar contribuinte)', 32, True),
    ('AGT_SOFTWARE_PRIVATE_KEY_PEM', 'Chave Privada Software AGT',  50, True),
    ('AGT_SOFTWARE_VALIDATION_NUMBER','Número Validação AGT',         3, False),
    ('AGT_PRODUCT_COMPANY_TAX_ID',   'NIF SOTARQ Software',          9, False),
    ('AGT_PRODUCT_ID',               'ProductID SAF-T',              3, False),
    ('AGT_ENVIRONMENT',              'Ambiente AGT (HOMOLOGACAO/PRODUCTION)', 1, False),
    ('DATABASE_URL',                 'URL de ligação à BD',          5, False),
]

for var, label, min_len, required in env_checks:
    val = os.environ.get(var, '')
    if not val:
        if required:
            err(f"{label} ({var}) — NÃO DEFINIDA ⚡ obrigatória")
        else:
            warn(f"{label} ({var}) — não definida")
    elif len(val) < min_len:
        warn(f"{label} ({var}) — definida mas parece curta ({len(val)} chars < {min_len} esperado)")
    else:
        ok(f"{label} ({var}) — definida ({len(val)} chars)")

# Validação específica da chave PEM
pem = os.environ.get('AGT_SOFTWARE_PRIVATE_KEY_PEM', '')
if pem:
    pem_decoded = pem.replace('\\n', '\n')
    if '-----BEGIN' in pem_decoded and 'PRIVATE KEY' in pem_decoded:
        ok("AGT_SOFTWARE_PRIVATE_KEY_PEM — formato PEM aparentemente válido")
    else:
        err("AGT_SOFTWARE_PRIVATE_KEY_PEM — não parece ser um PEM válido (falta '-----BEGIN ... PRIVATE KEY-----')")

# Validação do número de validação AGT (padrão: NNN/AGT/AAAA ou '0')
val_num = os.environ.get('AGT_SOFTWARE_VALIDATION_NUMBER', '')
if val_num and val_num != '0':
    if re.match(r'^\d+/AGT/\d{4}$', val_num) or re.match(r'^\d+$', val_num):
        ok(f"AGT_SOFTWARE_VALIDATION_NUMBER — formato válido: {val_num}")
    else:
        warn(f"AGT_SOFTWARE_VALIDATION_NUMBER — formato inesperado: '{val_num}' (esperado: NNN/AGT/AAAA ou inteiro)")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Carregar Django e verificar settings
# ──────────────────────────────────────────────────────────────────────────────
section("Configurações Django")

try:
    import django
    django.setup()
    from django.conf import settings
    ok("Django inicializado com sucesso")
except Exception as e:
    err(f"Falha ao inicializar o Django: {e}")
    print(f"\n{RED}Diagnóstico interrompido — Django não carregou.{RESET}\n")
    sys.exit(1)

# DEBUG
if settings.DEBUG:
    warn(f"DEBUG = True (modo desenvolvimento)")
else:
    ok("DEBUG = False (modo produção)")
    if not settings.ALLOWED_HOSTS:
        err("ALLOWED_HOSTS está vazio — servidor não responderá em produção")
    else:
        ok(f"ALLOWED_HOSTS = {settings.ALLOWED_HOSTS}")

# SECRET_KEY
if len(settings.SECRET_KEY) < 50:
    err(f"SECRET_KEY parece curta ({len(settings.SECRET_KEY)} chars)")
elif 'django-insecure' in settings.SECRET_KEY or 'changeme' in settings.SECRET_KEY.lower():
    err("SECRET_KEY contém valor inseguro/padrão — não usar em produção")
else:
    ok(f"SECRET_KEY — comprimento {len(settings.SECRET_KEY)} chars")

# DATABASES
try:
    db = settings.DATABASES.get('default', {})
    engine = db.get('ENGINE', '')
    name = db.get('NAME', db.get('URL', ''))
    if 'postgresql' in engine or 'postgis' in engine:
        ok(f"Base de dados: PostgreSQL ({str(name)[:40]})")
    elif engine:
        warn(f"Base de dados: {engine} (esperado PostgreSQL para produção)")
    else:
        err("DATABASES não configurado")
except Exception as e:
    err(f"Erro ao ler DATABASES: {e}")

# CELERY / REDIS
section("Celery e Redis")
broker = getattr(settings, 'CELERY_BROKER_URL', '') or os.environ.get('REDIS_URL', '')
if not broker:
    err("CELERY_BROKER_URL / REDIS_URL não definida — Celery não vai funcionar")
else:
    ok(f"Broker Celery: {broker[:50]}{'...' if len(broker) > 50 else ''}")
    # Tentar ping ao Redis
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(broker, socket_connect_timeout=3)
        r.ping()
        ok("Redis — acessível (ping OK)")
    except ImportError:
        warn("Biblioteca 'redis' não instalada — impossível testar conexão")
    except Exception as e:
        err(f"Redis — não acessível: {e}")

beat_schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
if beat_schedule:
    ok(f"CELERY_BEAT_SCHEDULE — {len(beat_schedule)} tarefa(s) agendada(s)")
    for name in beat_schedule:
        info(f"  • {name}")
else:
    warn("CELERY_BEAT_SCHEDULE — vazio (nenhuma tarefa agendada)")

# ──────────────────────────────────────────────────────────────────────────────
# 4. Verificações específicas do VistoGest / AGT
# ──────────────────────────────────────────────────────────────────────────────
section("VistoGest / AGT")

agt_settings = [
    ('AGT_ENVIRONMENT',             'Ambiente AGT'),
    ('AGT_BASE_URL_HOMOLOGACAO',    'URL Homologação AGT'),
    ('AGT_BASE_URL_PRODUCAO',       'URL Produção AGT'),
    ('AGT_QR_CODE_BASE_URL',        'URL QR Code AGT'),
    ('AGT_SOFTWARE_PRODUCT_ID',     'ProductID Software'),
    ('AGT_SOFTWARE_PRODUCT_VERSION','Versão Software'),
    ('AGT_PRODUCT_COMPANY_TAX_ID',  'NIF SOTARQ'),
]

for attr, label in agt_settings:
    val = getattr(settings, attr, None)
    if val:
        ok(f"{label}: {val}")
    else:
        warn(f"{label} ({attr}) — não definido em settings")

# Ambiente AGT
env_agt = getattr(settings, 'AGT_ENVIRONMENT', '')
if env_agt == 'PRODUCTION':
    warn("AGT_ENVIRONMENT = PRODUCTION — a usar endpoints reais da AGT")
elif env_agt == 'HOMOLOGACAO':
    ok("AGT_ENVIRONMENT = HOMOLOGACAO — a usar endpoints de teste")
else:
    err(f"AGT_ENVIRONMENT = '{env_agt}' — valor inesperado (esperado: HOMOLOGACAO ou PRODUCTION)")

# ──────────────────────────────────────────────────────────────────────────────
# 5. Resumo
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}")
print(f"{BOLD}{CYAN}  Diagnóstico concluído.{RESET}")
print(f"{BOLD}{CYAN}{'═'*60}{RESET}\n")

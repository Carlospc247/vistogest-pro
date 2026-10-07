"""
Script de verificação do sistema VistoGest Pro.
Executar: .\\venv\\Scripts\\python.exe _check_system.py
"""
import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.development'

import django
django.setup()

from django.conf import settings
from django.urls import reverse, NoReverseMatch

SEP = "=" * 62
print(SEP)
print("  VERIFICAÇÃO DO SISTEMA — VistoGest Pro")
print(SEP)

errors = []

# ── Settings críticas ──────────────────────────────────────────
db = settings.DATABASES['default']
print("\n[SETTINGS]")
items = [
    ("DEBUG",           settings.DEBUG),
    ("DB_NAME",         db['NAME']),
    ("DB_USER",         db['USER']),
    ("DB_HOST",         db['HOST']),
    ("EMAIL_BACKEND",   settings.EMAIL_BACKEND),
    ("REDIS_URL",       settings.REDIS_URL or "AUSENTE"),
    ("AES_KEY",         "OK" if settings.AES_KEY else "AUSENTE"),
    ("ENCRYPTION_KEY",  "OK (substituir em PROD)" if settings.ENCRYPTION_KEY else "AUSENTE"),
    ("GATEWAY_SECRET",  "OK" if settings.GATEWAY_WEBHOOK_SECRET else "AUSENTE"),
    ("PWD_RESET_TTL",   f"{settings.PASSWORD_RESET_TIMEOUT}s"),
]
for label, val in items:
    flag = "AUSENTE" in str(val)
    icon = "ERR" if flag else " OK"
    print(f"  {icon}  {label:<20} {val}")
    if flag:
        errors.append(f"Setting ausente: {label}")

# ── URLs schema PUBLIC (urls_login.py) ─────────────────────────
# Estas URLs existem em AMBOS os schemas (public e tenant).
print("\n[URLs — PUBLIC + TENANT (devem existir em ambos)]")
public_urls = [
    ("core:login",                    {}),
    ("core:logout",                   {}),
    ("core:login_status",             {}),
    ("core:login_unblock",            {}),
    ("core:password_reset",           {}),
    ("core:password_reset_done",      {}),
    ("core:password_reset_confirm",   {"uidb64": "MQ", "token": "abc-123"}),
    ("core:password_reset_complete",  {}),
]
for name, kw in public_urls:
    try:
        url = reverse(name, kwargs=kw)
        print(f"   OK  {name:<48} {url}")
    except NoReverseMatch as e:
        print(f"  ERR  {name:<48} {e}")
        errors.append(f"URL ausente (public): {name}")

# ── URLs schema TENANT (urls.py) ───────────────────────────────
# Estas URLs SÓ existem no contexto de tenant — não no schema public.
# Por isso são verificadas com o urlconf de tenants directamente.
print("\n[URLs — APENAS TENANT (urls.py)]")
from django.urls import reverse as _rev

tenant_urlconf = settings.TENANT_URLCONF  # 'config.urls_tenants'
tenant_urls = [
    ("core:dashboard",          {}),
    ("core:notifications",      {}),
    ("core:verify_ip",          {}),
    ("core:security_history",   {}),
    ("core:login_status",       {}),
    ("core:pwa_manifest",       {}),
    ("core:pwa_offline",        {}),
    ("core:pwa_service_worker", {}),
]
for name, kw in tenant_urls:
    try:
        url = _rev(name, kwargs=kw, urlconf=tenant_urlconf)
        print(f"   OK  {name:<48} {url}")
    except NoReverseMatch as e:
        print(f"  ERR  {name:<48} {e}")
        errors.append(f"URL ausente (tenant): {name}")

# ── Resultado ──────────────────────────────────────────────────
print()
print(SEP)
if errors:
    print(f"  RESULTADO: {len(errors)} ERRO(S)")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)
else:
    print("  RESULTADO: TUDO OK")
    print()
    print("  Passos seguintes:")
    print("    .\\venv\\Scripts\\python.exe manage.py migrate_schemas \\")
    print("        --settings=config.settings.development")
    print("    .\\venv\\Scripts\\python.exe manage.py runserver 8080 \\")
    print("        --settings=config.settings.development")
print(SEP)

#!/usr/bin/env python
"""Script de diagnóstico para verificar as configurações do Django"""
import os
import sys

# Adicionar o diretório do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configurar o Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings')

print("=" * 60)
print("DIAGNÓSTICO DE CONFIGURAÇÕES")
print("=" * 60)

# Verificar variáveis de ambiente ANTES de importar settings
print("\n1. VARIÁVEIS DE AMBIENTE (antes de carregar settings):")
print(f"   ENV_MODE: {os.getenv('ENV_MODE', 'NOT SET')}")
print(f"   DEBUG: {os.getenv('DEBUG', 'NOT SET')}")
print(f"   SECRET_KEY: {'SET' if os.getenv('SECRET_KEY') else 'NOT SET'}")

# Importar Django e settings
import django
django.setup()

from django.conf import settings

print("\n2. CONFIGURAÇÕES DO DJANGO (após carregar settings):")
print(f"   ENV_MODE: {getattr(settings, 'ENV_MODE', 'NOT FOUND')}")
print(f"   DEBUG: {settings.DEBUG}")
print(f"   ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
print(f"   SECRET_KEY: {'SET' if settings.SECRET_KEY else 'NOT SET'}")

print("\n3. ANÁLISE:")
if settings.DEBUG:
    print("   ✓ DEBUG está ativado (modo desenvolvimento)")
else:
    print("   ✗ DEBUG está desativado (modo produção)")
    if not settings.ALLOWED_HOSTS:
        print("   ✗ ERRO: ALLOWED_HOSTS está vazio!")
    elif settings.ALLOWED_HOSTS:
        print(f"   ✓ ALLOWED_HOSTS configurado: {settings.ALLOWED_HOSTS}")

print("\n" + "=" * 60)

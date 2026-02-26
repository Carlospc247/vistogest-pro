#!/usr/bin/env python3
import argparse
import os
import re
import secrets
from pathlib import Path
from django.core.management.base import BaseCommand

from pharmassys.settings import SECRET_KEY

# Alfabeto compatível com o gerador oficial do Django
ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"
DEFAULT_LEN = 50

class Command(BaseCommand):
    help = 'Exporta categorias para Excel'

    def handle(self, *args, **options):
        
        self.stdout.write(self.style.SUCCESS(F"CHAVE SECRETA com sucesso! {SECRET_KEY}"))


def generate_secret_key(length: int = DEFAULT_LEN, alphabet: str = ALPHABET) -> str:
    if length < 32:
        raise ValueError("Use length >= 32 por segurança.")
    return "".join(secrets.choice(alphabet) for _ in range(length))

def update_env_file(env_path: Path, key: str, var_name: str = "SECRET_KEY") -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(var_name)}=.*$", flags=re.MULTILINE)

    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        if pattern.search(content):
            content = pattern.sub(f"{var_name}={key}", content)
        else:
            if content and not content.endswith("\n"):
                content += "\n"
            content += f"{var_name}={key}\n"
    else:
        content = f"{var_name}={key}\n"

    env_path.write_text(content, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(
        description="Gera uma Django SECRET_KEY segura e opcionalmente grava no .env"
    )
    parser.add_argument("-l", "--length", type=int, default=DEFAULT_LEN,
                        help=f"Tamanho da chave (padrão: {DEFAULT_LEN}, mínimo: 32)")
    parser.add_argument("-o", "--outfile", type=str, default=None,
                        help="Caminho do .env para escrever/atualizar (ex: ./.env)")
    parser.add_argument("-n", "--name", type=str, default="SECRET_KEY",
                        help="Nome da variável no .env (padrão: SECRET_KEY)")
    parser.add_argument("--print-only", action="store_true",
                        help="Apenas imprimir no stdout (não escreve no arquivo)")
    args = parser.parse_args()

    key = generate_secret_key(args.length)

    if args.print_only or not args.outfile:
        print(key)
    else:
        env_path = Path(args.outfile).expanduser().resolve()
        update_env_file(env_path, key, var_name=args.name)
        print(f"{args.name} atualizada em: {env_path}")

if __name__ == "__main__":
    main()

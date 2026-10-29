# apps/configuracoes/management/commands/verificar_tenants.py
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import get_public_schema_name, schema_context

from apps.configuracoes.models import ConfiguracaoFiscal
from apps.configuracoes.services.identidade import divergencias, sincronizar_identidade
from apps.empresas.models import Empresa
from apps.fiscal.models import AssinaturaDigital
from apps.fiscal.utility import chaves


class Command(BaseCommand):
    help = "Verifica Empresa ↔ ConfiguracaoFiscal ↔ chaves AGT em todos os tenants."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true",
                            help="Re-sincroniza a identidade (Empresa -> ConfiguracaoFiscal).")
        parser.add_argument("--carimbar", action="store_true",
                            help="Carimba chaves antigas (se o par validar e o NIF bater com a Empresa).")

    def handle(self, *args, fix, carimbar, **options):
        falhas = 0
        for empresa in Empresa.objects.exclude(schema_name=get_public_schema_name()).order_by("schema_name"):
            try:
                estado, detalhe = self.verificar(empresa, fix, carimbar)
            except Exception as exc:
                estado, detalhe = "ERRO", str(exc)
            if estado in ("PROBLEMAS", "ERRO"):
                falhas += 1
            self.stdout.write(f"[{empresa.schema_name}] {estado} {detalhe}".rstrip())
        if falhas:
            raise CommandError(f"{falhas} tenant(s) com problemas.")

    def verificar(self, empresa, fix, carimbar):
        if fix:
            sincronizar_identidade(empresa)
        with schema_context(empresa.schema_name):
            config = ConfiguracaoFiscal.objects.order_by("pk").first()
            problemas = [f"{campo}: esperado {esperado!r}, actual {actual!r}"
                         for campo, (esperado, actual) in divergencias(config, empresa).items()]
            ass = AssinaturaDigital.objects.filter(pk=1).first()
            if ass is None or not ass.esta_configurada:
                return ("PROBLEMAS", "; ".join(problemas)) if problemas else ("SEM_CHAVES", "")
            if carimbar and not ass.schema_vinculado:
                problemas += self.carimbar(ass, empresa)
            problemas += ass.verificar_integridade()
        return ("PROBLEMAS", "; ".join(problemas)) if problemas else ("OK", "")

    @staticmethod
    def carimbar(ass, empresa):
        """Migração única: carimba chaves gravadas antes de existir o carimbo."""
        if ass.nif_contribuinte != empresa.nif:
            return [f"NIF das chaves ({ass.nif_contribuinte}) difere do da empresa ({empresa.nif})."]
        try:
            _, pub = ass.ler_par()
        except Exception as exc:
            return [f"Não foi possível carimbar: {exc}"]
        ass.chave_publica_fingerprint = chaves.fingerprint(pub)
        ass.schema_vinculado = connection.schema_name
        ass.save()
        return []
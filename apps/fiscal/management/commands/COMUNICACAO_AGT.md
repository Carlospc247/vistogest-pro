exec("""
from django_tenants.utils import schema_context
from apps.fiscal.services.agt_client import AGTClient, AGTError

with schema_context("sotarqsoftware"):
    cliente = AGTClient()

    try:
        resultado = cliente.listar_series()

        print("\\n--- RESPOSTA DA AGT ---")
        print("HTTP:", resultado.get("_http_status"))
        print("Código:", resultado.get("resultCode"))
        print("Descrição:", resultado.get("resultDesc"))
        print("Quantidade de séries:", resultado.get("seriesResultCount"))

    except AGTError as exc:
        print("\\n--- ERRO DA AGT ---")
        print("Mensagem:", str(exc))
        print("Serviço:", getattr(exc, "servico", None))
        print("HTTP:", getattr(exc, "http_status", None))
        print("Código:", getattr(exc, "result_code", None))
        print("Detalhes:", getattr(exc, "errors", None))

    except Exception as exc:
        print("\\n--- ERRO INESPERADO ---")
        print(type(exc).__name__, str(exc))
""")
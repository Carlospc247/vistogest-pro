from apps.empresas.models import Empresa, Domain

# TENANT PUBLICO
empresa = Empresa(
    schema_name="public",
    nome="VISTOGEST SOFTWARE - Administração Global",
    nome_fantasia="VistoGest",
    nif="000000000",
    regime="MISTO",
    endereco="Sede VistoGest",
    numero="0",
    bairro="Centro",
    cidade="Luanda",
    provincia="LUA",
    postal="0000-000",
    telefone="+244000000000",
    email="admin@vistogest.pro",
    ativa=True
)

empresa.save()

# DOMINIO PUBLICO
dominio = Domain()
dominio.domain = "vistogest.pro"
dominio.tenant = empresa
dominio.is_primary = True
dominio.save()

print("PUBLIC TENANT CRIADO")
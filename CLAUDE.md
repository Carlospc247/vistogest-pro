# CLAUDE.md

Este documento define regras de contexto e execução para o Claude trabalhar no VistoGest Pro.
Cada afirmação está rotulada:

- **FATO** — confirmado por leitura direta do código real partilhado nesta conversa.
- **DECISÃO/REGRA** — arquitetura exigida, decidida explicitamente pelo dono do sistema.
- **NÃO VERIFICADO** — mencionado em algum momento, mas nunca confirmado num ficheiro real. Não deve ser tratado como certo até ser lido.

Esta reescrita corrige a versão anterior gerada pelo Claude Code, que continha três erros factuais confirmados (detalhados no fim deste documento, secção "Erros corrigidos").

---

## Visão Geral
**FATO**: O VistoGest Pro é um ERP de gestão e faturação multi-tenant para o mercado angolano, com exigência de conformidade fiscal junto da AGT (Administração Geral Tributária), incluindo faturação eletrónica conforme o Decreto Executivo n.º 683/25.

## Stack
**FATO**:
- Linguagem: Python. Framework: Django.
- Banco de Dados: PostgreSQL (`psycopg2-binary`).
- Multi-tenancy: `django-tenants` (isolamento físico por schema PostgreSQL).
- Assíncrono: Celery + Redis.
- Armazenamento: WhiteNoise (estáticos) + Cloudinary (media, via `django-cloudinary-storage`).
- Criptografia: `cryptography` (RSA para assinatura JWS, AES para chaves em repouso).

## Estrutura do Projeto
**FATO**:
- `/config/`: settings divididos (`base.py`, `development.py`, `production.py`), `urls_public.py` (schema `public`), `urls_tenants.py` (rotas por tenant), tarefas Celery.
- `/apps/`:
  - *Shared Apps* (schema `public`): `core`, `empresas`, `licenca`, `auditoria_publica`.
  - *Tenant Apps*: `vendas`, `fiscal`, `saft`, `configuracoes`, `analytics`, `produtos`, `clientes`, `fornecedores`, `estoque`, `funcionarios`, `servicos`, `financeiro`, `relatorios`, `compras`, `site` (lista confirmada em `TENANT_APPS` de `config/settings/base.py`).
- `apps/vendas`: **já reescrito** — `models.py` e `views.py` sem FK para `empresas.Empresa`, sem modelo `Loja`. Empresa é implícita pelo schema activo (`connection.tenant` em services/models; `request.user.empresa` em views, pois `Usuario` é modelo SHARED e carrega essa FK legitimamente).
- `apps/fiscal`: **ainda não migrado** para isolamento físico — `TaxaIVAAGT`, `RetencaoFonte`, `SAFTExport` ainda têm FK `empresa` nos modelos, e a maioria de `views.py`/`views_debug.py`/`views_integracoes.py` ainda filtra por `empresa=request.user.empresa` ou `.filter(empresa=empresa)`. `AssinaturaDigital` já foi migrado nesta sessão (ver secção seguinte).

## Arquitetura Multi-Tenant
**DECISÃO/REGRA**:
- `public` nunca partilha dados com tenants.
- Código fora do ciclo de request (management commands, tasks Celery) deve forçar o schema explicitamente com `schema_context(schema_name)`.
- `DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)` — isolamento é **físico** (schema PostgreSQL separado por tenant), não uma restrição lógica por FK/filtro.

## Arquitetura Fiscal (AGT) — chaves de assinatura
**DECISÃO/REGRA**, corrigida e implementada nesta sessão:

Existem **duas chaves RSA com origens opostas**:

1. **Chave do Software** (`jwsSoftwareSignature`) — gerada **localmente pela SOTARQ**, uma só para todo o sistema, igual para todos os tenants. Homologada uma única vez no Portal do Parceiro AGT. Vive **apenas** em variável de ambiente:
   - `AGT_SOFTWARE_PRIVATE_KEY_PEM` (PEM inline, com `\n` escapado) — variável real e activa.
   - `AGT_SOFTWARE_PRIVATE_KEY_PATH` (alternativa: caminho para ficheiro `.pem`).
   - `SOTARQ_PRIVATE_KEY` é **código morto** — ainda existe em `config/settings/base.py` (`SOTARQ_PRIVATE_KEY_BYTES`) mas nenhum serviço activo a lê. Não usar como referência.
   - Gerida por `AssinaturaSoftwareService` (`apps/fiscal/services/assinatura_service.py`), método `montar_software_info()`.

2. **Chave do Contribuinte** (`jwsDocumentSignature`, `jwsSignature`) — **emitida pela AGT**, uma por NIF, obtida pelo admin de cada empresa no Portal do Contribuinte e colada manualmente no sistema. É **por tenant**, mas nunca gerada por este sistema.
   - Persistida no modelo singleton `AssinaturaDigital` (`apps/fiscal/models.py`), campo `chave_contribuinte_privada`, cifrado em repouso com `AESService.encrypt()` (cifragem **única**, AES-256-CFB via chave derivada por PBKDF2-HMAC-SHA256 de `AES_KEY` — não é "dupla encriptação").
   - Gerida por `AssinaturaDigitalService.configurar_chave_contribuinte()` — este método **nunca gera** um par de chaves; apenas valida e guarda o que foi colado.
   - `AssinaturaDigital` é singleton **por schema de tenant** (reforçado em `save()`), sem FK para `empresas.Empresa` (isolamento físico).

3. **Padrão JWS**: RS256 = `RSASSA-PKCS1-v1_5` + SHA-256 (RFC 7518). **Não é RSA-PSS** — a implementação anterior usava `padding.PSS(...)`, o que geraria assinaturas rejeitadas por um validador RS256 padrão como o da AGT. Corrigido em `gerar_jws_rs256()`.

4. **Assinar é síncrono, comunicar com a AGT é assíncrono**: RSA local (assinar um documento ou uma requisição) é uma operação de microssegundos e corre inline, dentro da mesma transação que confirma o documento. O que é genuinamente assíncrono é a chamada HTTP a `registarFactura` (devolve `requestID` na hora, mas a validação fiscal completa só fica pronta depois) — só esta parte deve ir para Celery (`FiscalPollingService` + Celery beat chamando `obterEstado`).

## ⚠️ Falha de arquitetura identificada — cadeias de hash/ATCUD duplicadas (NÃO RESOLVIDA)
**NÃO VERIFICADO → agora confirmado por leitura de código, decisão ainda pendente**:

Os modelos de `apps.vendas` (`Venda`, `FaturaCredito`, `Recibo`, `NotaCredito`, `NotaDebito`, `DocumentoTransporte`) **não herdam de `DocumentoFiscal`** (app `fiscal`) e **não têm relação alguma** com ele — nem FK. São modelos completamente separados, cada um com os seus próprios campos `hash_documento`/`atcud`, gerados pela sua própria lógica em `apps/vendas/models.py`.

Em paralelo, `DocumentoFiscal` (`apps/fiscal/models.py`) tem **a sua própria** numeração (`ContadorDocumento`), o seu próprio `_gerar_hash_documento()` e o seu próprio `atcud`, através de `DocumentoFiscalService.criar_documento()` chamado a partir de `venda.gerar_documento_fiscal()`.

**Resultado prático hoje**: uma única fatura pode ter **dois hashes e dois ATCUDs diferentes** — um gerado em `apps.vendas` (o que aparece no PDF ao cliente) e outro gerado em `apps.fiscal.DocumentoFiscal` (o que alimentaria, em teoria, o SAF-T e a submissão à AGT) — sem nenhuma relação formal entre os dois.

Isto **precisa de decisão explícita antes da Fase 3** do `PLANO_IMPLEMENTACAO.md`, porque determina onde os novos campos obrigatórios do Anexo I (`operationType`, `settlementAmount`, `referenceInfo` por linha, `currency`) devem realmente viver: no modelo de vendas, no `DocumentoFiscal`, ou eliminando a duplicação e fazendo um apontar para o outro.

## Regras críticas
**DECISÃO/REGRA**:
1. **Delete de `Usuario`**: cuidado com cascade cruzando schemas (`public` → tenant). Evitar FKs explícitas de tabelas tenant apontando para tabelas `public`.
2. **Nunca processar chamadas de rede lentas de forma síncrona numa view** — envio à AGT (`registarFactura`) e geração de SAF-T grande devem ir para Celery. (Assinar localmente com RSA **não** entra nesta regra — ver secção "Arquitetura Fiscal", ponto 4.)
3. `TwoFactorIPMiddleware` é o único mecanismo de 2FA por IP — não inventar lógica de acesso paralela.
4. **Nenhuma nova query em `apps/fiscal` deve introduzir filtro por `empresa=`** a partir de agora — isso seria andar para trás em relação à migração de isolamento físico já feita em `apps/vendas`. Novo código em `apps/fiscal` deve assumir isolamento por schema, mesmo que o modelo antigo ainda tenha o campo (até a migração completa do app).

## Convenções
**FATO**:
- Nomes de variáveis, classes e métodos em Português (`calcular_totais()`), com termos técnicos em inglês pontualmente (`get_client_ip()`).
- Uso extensivo de class-based views e mixins (`PermissaoAcaoMixin`, `AccessMixin`).
- Nomes de rotas (`name=`) em minúsculas com hífen.

## Banco de Dados
**FATO**:
- `Empresa` (schema `public`) é o `TENANT_MODEL`; `Domain` é o `TENANT_DOMAIN_MODEL`.
- `AUTH_USER_MODEL = 'core.Usuario'` (schema `public`, SHARED_APPS).

## APIs e Integrações AGT
**FATO** (URLs confirmadas em `.env`/`base.py` nesta sessão):
- `AGT_ENVIRONMENT` alterna entre `'HOMOLOGACAO'` e `'PRODUCTION'`.
- `AGT_BASE_URL_HOMOLOGACAO = https://sifphml.minfin.gov.ao/sigt/fe/v1`
- `AGT_BASE_URL_PRODUCAO = https://sifp.minfin.gov.ao/sigt/fe/v1`
- Autenticação da API AGT: Basic Auth (usuário/senha emitidos por email pela AGT — `produtores.dfe.dcrr.agt@minfin.gov.ao`), camada **distinta** da assinatura JWS. Campos `api_username`/`api_password` já existem em `AssinaturaDigital`.
- URL do QR Code — **decisão do dono do sistema**: usar `https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor=nifEmissor&document=documentNo` (Portal do Parceiro), **não** a URL do Anexo III do Decreto Executivo 683/25 (`portaldocontribuinte.minfin.gov.ao/consultar-fe?documentNo`), que se considera desatualizada/erro de contexto no texto legal.
- 7 serviços REST do Anexo I (todos POST, síncronos por chamada; modelo de negócio "validação a posteriori"): `registarFactura`, `obterEstado`, `listarFacturas`, `consultarFactura`, `solicitarSerie`, `listarSeries`, `validarDocumento`.

**NÃO VERIFICADO**: nenhum destes 7 serviços tem cliente HTTP implementado ainda — apenas `FiscalPollingService.consultar_estado_documento()` para `obterEstado`, e mesmo esse chama `AssinaturaDigitalService.gerar_jws(self.empresa, ...)`, uma assinatura de método que **não existe** na versão actual de `AssinaturaDigitalService` (o método real chama-se `assinar_requisicao(campos_requisicao)` e não recebe `empresa`). Este ficheiro está quebrado e precisa de correcção.

## Segurança
**DECISÃO/REGRA**:
- Segredos sempre via `os.getenv`/`os.environ`, nunca hardcoded.
- Chave do contribuinte nunca é lida em texto plano da base de dados — sempre via `AESService.decrypt()`.
- Chave do Software nunca é gerada em runtime nem guardada em base de dados — só variável de ambiente.

## Desenvolvimento
**FATO**:
- Venv (Windows): `.\venv\Scripts\Activate.ps1`
- Infra (Celery/DB): `.\iniciar_infra.ps1`
- Migrations: `.\reset_migrations.ps1`
- Server dev: `python manage.py runserver --settings=config.settings.development`
- Migrate schema public: `python manage.py migrate_schemas --schema=public --settings=config.settings.development`

## Testes
**FATO**: Sem cobertura real — `tests.py` dos apps só têm moldes `django.test.TestCase` vazios.

## Regras para alterações
**DECISÃO/REGRA**:
1. Antes de mexer em campos de documentos fiscais (Nota, Recibo, Fatura), reveja como interagem com `TaxaIVAAGT` e com a cadeia de hash. Um documento já confirmado/assinado **não pode** ser modificado.
2. Todo app novo precisa estar explicitamente em `SHARED_APPS` ou `TENANT_APPS` (`config/settings/base.py`), senão não é instanciado nos schemas de tenant.
3. Ao adicionar campo em modelo de `apps/fiscal`, nunca adicionar FK para `empresa` — isolamento físico é a direção do projeto, não o contrário.

## Não fazer
**DECISÃO/REGRA**:
- **NÃO** misturar dados de tenant em `urls_public.py`.
- **NÃO** usar a chave privada do contribuinte sem passar por `AESService.decrypt()`.
- **NÃO** apagar migrations manualmente — usar `reset_migrations.ps1`.
- **NÃO** inventar regras de ATCUD/numeração fora do que os Anexos I/II/III do Decreto Executivo 683/25 e o Portal do Parceiro exigem.
- **NÃO** assumir RSA-PSS para assinatura JWS — é PKCS1v15 (RS256 padrão).
- **NÃO** tratar `SOTARQ_PRIVATE_KEY` como a chave activa do Software — é código morto; a activa é `AGT_SOFTWARE_PRIVATE_KEY_PEM`.

---

## Erros corrigidos nesta revisão (vs. versão gerada pelo Claude Code)

1. ~~"chave da fornecedora carregada de `SOTARQ_PRIVATE_KEY` e `AGT_SOFTWARE_PRIVATE_KEY_PEM`"~~ — `SOTARQ_PRIVATE_KEY` é código morto; a variável real e única é `AGT_SOFTWARE_PRIVATE_KEY_PEM`.
2. ~~"chave privada deve ser duplamente encriptada"~~ — é uma única cifragem AES via `AESService`, não dupla.
3. ~~"Documentos de Faturação partilham herança lógica do `DocumentoFiscal`"~~ — **falso**. São modelos paralelos e desconectados (ver secção "Falha de arquitetura identificada" acima).
4. ~~`AGT_BASE_URL_HOMOLOGACAO`/`AGT_BASE_URL_PRODUCAO` como "FATO" consumado~~ — confirmado agora como FATO real (existem no `.env`/`base.py`), mas a integração que as usa (`FiscalPollingService`) está quebrada (ver "NÃO VERIFICADO" acima).
5. ~~"Tenant App usa restrição lógica via `DB_ROUTER`"~~ — corrigido: é isolamento **físico** por schema via `TenantSyncRouter`.
6. `LicencaVencidaMiddleware` — não confirmado em nenhum `MIDDLEWARE` partilhado até agora. Mantido como **NÃO VERIFICADO**, não removido, caso exista num ficheiro ainda não partilhado.
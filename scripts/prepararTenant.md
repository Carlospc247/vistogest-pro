PREPARAÇÃO AUTOMÁTICA DE TENANT — VISTOGEST PRO

Ficheiros necessários dentro da pasta scripts/ do projecto Django:
  - preparar_tenant_producao.py
  - criar_consumidor_final.py

Executar na raiz do projecto, depois de activar o ambiente virtual:
  python scripts/preparar_tenant_producao.py NOME_DO_SCHEMA

Exemplo:
  python scripts/preparar_tenant_producao.py mundoemaquinas

O programa solicita a confirmação do schema. Para um processo não interactivo,
use --yes apenas se o schema já tiver sido validado:
  python scripts/preparar_tenant_producao.py mundoemaquinas --yes

Ordem das etapas:
  1. setup_formas_pagamento --schema=<schema> --forcar
     Não usa --ativar: cria/configura todas as formas de pagamento conforme o
     command do projecto. A activação posterior fica a cargo dos utilizadores
     autorizados na aplicação.
  2. iniciar_ambiente_fin_tenant --schema=<schema>
  3. iniciar_ambiente_fiscal_tenant --schema=<schema>
  4. scripts/criar_consumidor_final.py <schema> --forcar

O módulo settings padrão é config.settings.production (ou o valor de
DJANGO_SETTINGS_MODULE, se estiver definido). Pode escolher outro com:
  --django-settings=config.settings.production
  --finance-settings=config.settings.production

O script interrompe o fluxo ao primeiro erro. As etapas já concluídas não são
revertidas automaticamente; verifique o resultado de cada comando antes de
voltar a executar, especialmente se algum command não for idempotente.

## Para efeitos de testes em desenvolvimento no pc local

executar apenas o concumidor
python scripts\criar_consumidor_final.py sotarqsoftware --settings=config.settings.development

executar o processo completo
python scripts\preparar_tenant_producao.py sotarqsoftware --django-settings=config.settings.development --finance-settings=config.settings.development

verificar existência:
Test-Path .\config\settings\development.py
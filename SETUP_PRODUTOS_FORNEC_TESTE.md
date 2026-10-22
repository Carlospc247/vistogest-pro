python manage.py setup_fornecedores  --schema=mundoemaquinas
python manage.py setup_produtos_lotes --schema=mundoemaquinas --quantidade=1200
python manage.py setup_servicos       --schema=mundoemaquinas --quantidade=500
python manage.py setup_formas_pagamento --schema=mundoemaquinas --ativar=dinheiro,transferencia --forcar
python manage.py iniciar_ambiente_fin_tenant --schema=mundoemaquinas --settings=config.settings.development

python manage.py iniciar_ambiente_fiscal_tenant --schema=mundoemaquinas

Opções úteis do setup_produtos_lotes:
--com-vencidos cria ~3% de lotes vencidos.
--com-movimentacoes --usuario=<username> cria também as entradas em MovimentacaoEstoque
--lotes-max=3, --seed=42



Criar e confirmar as amostras num schema exclusivamente de ensaio, usando o último dia do mês anterior para o ponto 1:

```powershell
python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --confirmar-documentos --usar-dois-meses
```

Executar um ponto específico:

```powershell
python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --ponto=5 --confirmar-documentos
```

Gerar/validar apenas o SAF-T de ensaio (os documentos já devem estar confirmados):

```powershell
python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --apenas-saft
```

Eliminar apenas as amostras deste lote que continuem em `draft` e depois recriá-las (não apaga documentos emitidos):

```powershell
python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --limpar
```

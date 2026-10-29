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



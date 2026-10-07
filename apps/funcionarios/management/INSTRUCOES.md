## Cargos
python manage.py criar_cargos_padrao --dry-run --settings=config.settings.development          # ver o que faria

python manage.py criar_cargos_padrao --settings=config.settings.development                    # todos os tenants

python manage.py criar_cargos_padrao --schema empresa_x --sincronizar --settings=config.settings.development

python manage.py criar_cargos_padrao --schema sotarq --incluir-parceiros --sincronizar --settings=config.settings.development

## Departamentos
# 1. Ver o que faria, sem gravar nada
python manage.py setup_departamento --dry-run

# 2. Criar os que faltam em todos os tenants (preserva os existentes)
python manage.py setup_departamento --settings=config.settings.development

# 3. Só num tenant
python manage.py setup_departamento --schema empresa_x --settings=config.settings.development

# 4. Repor os valores do catálogo nos já existentes (apaga personalizações)
python manage.py setup_departamento --schema empresa_x --sincronizar --settings=config.settings.development

# 5. Só alguns departamentos
python manage.py setup_departamento --only DEP-ADM --only DEP-FIN --settings=config.settings.development

# 6. Combinar: simular a reposição de um departamento num tenant
python manage.py setup_departamento --schema empresa_x --only DEP-TI --sincronizar --dry-run --settings=config.settings.development

#########
python manage.py setup_departamento --settings=config.settings.development
python manage.py criar_cargos_padrao --settings=config.settings.development
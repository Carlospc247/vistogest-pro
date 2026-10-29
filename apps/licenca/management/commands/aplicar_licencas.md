# O comportamento é o do pacote anterior:

# A validação bloqueia a gravação se houver inconsistência entre planos.
# Por omissão só mostra o que mudaria. Só grava com --aplicar.
# Se um plano em uso perder módulos ou limites, exige --forcar-remocao.

# Correr por esta ordem:

python manage.py setup_modulos --settings=config.settings.development
python manage.py setup_planos --settings=config.settings.development
python manage.py setup_planos --aplicar --settings=config.settings.development
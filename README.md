
Esse script serve para ligar os motores de segundo plano do SOTARQ VENDOR no seu ambiente de desenvolvimento.

Quando o servidor web do Django está a rodar, ele cuida apenas de responder às requisições do navegador.
No entanto, operações pesadas ou agendadas — como gerar assinaturas fiscais RSA para a AGT, enviar e-mails ou 
rodar rotinas automáticas — precisam acontecer em segundo plano para não travar a navegação do utilizador.


Exemplo prático usando systemd (Padrão Ubuntu/Debian):
Você cria dois arquivos de serviço no servidor:

## A) Celery Worker (/etc/systemd/system/celery_worker.service):

[Unit]
Description=Celery Worker - SOTARQ Vendor
After=network.target

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/var/www/config
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=/var/www/config/venv/bin/celery -A config.tasks_celery worker --loglevel=info

Restart=always

[Install]
WantedBy=multi-user.target


(Nota: Em Linux, não utilize -P solo no Worker; o modo nativo multiprocessado do Linux é muito mais rápido e eficiente).

## B) Celery Beat (/etc/systemd/system/celery_beat.service):

[Unit]
Description=Celery Beat - SOTARQ Vendor
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/config
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=/var/www/config/venv/bin/celery -A config.tasks_celery beat --loglevel=info

Restart=always

[Install]
WantedBy=multi-user.target


-- Para ativar e iniciar no Linux:--

# Bash:
## sudo systemctl daemon-reload
## sudo systemctl enable --now celery_worker
## sudo systemctl enable --now celery_beat
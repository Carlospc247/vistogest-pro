Impacto prático: use o instalador

Se usar o arquivo (terceiro comando), não terá o atalho "MSYS2 UCRT64" no menu Iniciar, que os meus passos usam. O instalador cria-o sozinho.

O que fazer agora

Ignore o README e siga só isto:

Descarregue o instalador em msys2.org.
Dê duplo clique e deixe a pasta como C:\msys64.
Depois de instalado, abra Menu Iniciar > procure "MSYS2 UCRT64" e execute:
## bash
pacman -Syu
pacman -S mingw-w64-ucrt-x86_64-pango

OPÇÃO B: Sem sair do terminal:
C:\msys64\msys2_shell.cmd -defterm -no-start -ucrt64 -c "pacman -Syu --noconfirm; pacman -S --noconfirm mingw-w64-ucrt-x86_64-pango"


Passo 6: ligar o WeasyPrint às DLLs

Permanente, para todos os terminais novos:

# powershell
setx WEASYPRINT_DLL_DIRECTORIES "C:\msys64\ucrt64\bin"

O setx só vale para terminais novos. Feche o PowerShell, abra outro, entre na pasta do projeto e reative o venv:

# powershell
cd "C:\Users\CARLOS SEBASTIÃO-PC\vistogest-pro"
venv\Scripts\Activate

Não adicione C:\msys64\ucrt64\bin ao PATH do Windows. Pode causar conflitos de DLLs com o Python e outros programas, e é para evitar isso que o WeasyPrint tem esta variável própria.

Passo 7: verificar
# powershell
python -m weasyprint --info
python manage.py check --settings=config.settings.development

O primeiro deve mostrar as versões sem erro. O segundo já não deve imprimir a mensagem do WeasyPrint.

Teste final, gerando um PDF a sério:

# powershell

python -c "from weasyprint import HTML; HTML(string='<h1>Teste</h1>').write_pdf('teste.pdf'); print('ok')"
Remove-Item teste.pdf








##### NNNNNNNNNNNNNNNNNNNNNNNN
O que aconteceu

O Pango nunca chegou a ser instalado, e o diagnóstico confirma: libgobject e libpango dão False. A causa está na saída que colou:

O pacman -Syu atualizou o msys2-runtime, que é um componente central.
Quando isso acontece, o MSYS2 fecha todos os seus processos, incluindo o terminal que estava a correr os seus comandos (SUCCESS: The process with PID ... has been terminated).
O segundo comando, o pacman -S ... pango, estava encadeado no mesmo terminal e morreu junto, antes de correr.

O setx guardou a variável, mas só vale para terminais novos. Por isso a variável aparece vazia na sessão atual.

A atualização do núcleo já está feita. Agora basta correr a instalação do Pango, desta vez separada.

Passo 1: terminar as atualizações
powershell
C:\msys64\msys2_shell.cmd -defterm -no-start -ucrt64 -c "pacman -Syu --noconfirm"

Se acabar com there is nothing to do, siga. Se voltar a fechar o terminal por atualizar outro componente central, repita este mesmo comando até aparecer there is nothing to do.

Passo 2: instalar o Pango
powershell
C:\msys64\msys2_shell.cmd -defterm -no-start -ucrt64 -c "pacman -S --noconfirm mingw-w64-ucrt-x86_64-pango"

Deve aparecer uma lista de pacotes (pango, glib2, harfbuzz, cairo…), a barra de progresso e installing ... até ao fim, sem mensagem de terminal fechado.

Se este comando continuar a dar problemas, use o terminal gráfico: Menu Iniciar > "MSYS2 UCRT64" e execute lá, dentro da janela:

bash
pacman -S --noconfirm mingw-w64-ucrt-x86_64-pango
Passo 3: confirmar que as DLLs existem
powershell
"libgobject: " + (Test-Path C:\msys64\ucrt64\bin\libgobject-2.0-0.dll)
"libpango:   " + (Test-Path C:\msys64\ucrt64\bin\libpango-1.0-0.dll)

Os dois têm de dar True. Se der False, o passo 2 não concluiu: cole aqui o que o terminal mostrou.

Passo 4: ligar o WeasyPrint às DLLs (nesta sessão)
powershell
$env:WEASYPRINT_DLL_DIRECTORIES="C:\msys64\ucrt64\bin"

Este comando vale só para o terminal atual. Em terminais novos já funciona sem repetir, porque o setx que correu antes guardou a variável.

Passo 5: testar
powershell
python -m weasyprint --info

Deve mostrar as versões, sem a mensagem de erro. Depois, o teste real:

powershell
python -c "from weasyprint import HTML; HTML(string='<h1>Teste</h1>').write_pdf('teste.pdf'); print('ok')"
Remove-Item teste.pdf

Se imprimir ok, está resolvido, e o aviso desaparece também dos comandos do manage.py.

O que já está bem
O Python é de 64 bits, que é o necessário.
O PATH não tem nenhuma versão conflituosa de GTK, MSYS ou GLib (a pesquisa que fez não devolveu nada).
O msys2-runtime já está atualizado.

Se falhar algum passo, cole a saída dele e eu digo o que falta.

 
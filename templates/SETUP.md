# Instalação do novo base.html (Windows / PowerShell)

Execute tudo na raiz do projeto (`vistogest-pro`), com o venv ativo.

## 1. Ficheiros a copiar
- templates/base.html
- templates/partials/vendor_chartjs.html, vendor_jquery.html, vendor_select2.html
- static/css/vistogest-base.css
- static/src/input.css
- tailwind.config.js (raiz do projeto)

## 2. Descarregar as bibliotecas para static/vendor (uma só vez)

```powershell
# Criar pastas
foreach ($d in "alpine","chartjs","jquery","select2","fontawesome\css","fontawesome\webfonts") {
    New-Item -ItemType Directory -Force -Path "static\vendor\$d" | Out-Null
}

# Descarregar ficheiros (versões fixas)
$FA = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2"
$files = [ordered]@{
    "static\vendor\alpine\alpine.min.js"                      = "https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js"
    "static\vendor\chartjs\chart.umd.min.js"                  = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.js"
    "static\vendor\jquery\jquery-3.6.0.min.js"                = "https://code.jquery.com/jquery-3.6.0.min.js"
    "static\vendor\select2\select2.min.js"                    = "https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"
    "static\vendor\select2\select2.min.css"                   = "https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css"
    "static\vendor\fontawesome\css\all.min.css"               = "$FA/css/all.min.css"
    "static\vendor\fontawesome\webfonts\fa-solid-900.woff2"   = "$FA/webfonts/fa-solid-900.woff2"
    "static\vendor\fontawesome\webfonts\fa-regular-400.woff2" = "$FA/webfonts/fa-regular-400.woff2"
    "static\vendor\fontawesome\webfonts\fa-brands-400.woff2"  = "$FA/webfonts/fa-brands-400.woff2"
}
foreach ($f in $files.GetEnumerator()) {
    Invoke-WebRequest -Uri $f.Value -OutFile $f.Key
}

# Conferir: nenhum ficheiro deve ter tamanho 0
Get-ChildItem static\vendor -Recurse -File | Select-Object FullName, Length
```

## 3. Compilar o Tailwind (v3, sem CDN)

```powershell
npm i -D tailwindcss@3.4.17

# Produção (uma vez)
npx tailwindcss -i ./static/src/input.css -o ./static/css/tailwind.css --minify

# Desenvolvimento (deixar a correr num segundo terminal; Ctrl+C para parar)
npx tailwindcss -i ./static/src/input.css -o ./static/css/tailwind.css --watch
```

Recompile sempre que criar classes novas nos templates.
Se os templates estiverem noutra pasta, acrescente o caminho em `content` no `tailwind.config.js`.

Em produção: `python manage.py collectstatic`.

## 4. Verificar

1. Existem `static\css\tailwind.css`, `static\css\vistogest-base.css` e `static\vendor\...` sem ficheiros vazios.
2. Abra uma página, carregue em F12 e confirme que não há erros 404 na consola.
3. Teste Claro e Escuro no menu do utilizador:
   - tema claro: título "vistoGEST" índigo, ícones do menu escuros;
   - tema escuro: título branco, ícones claros.

## 5. Páginas que usam Chart.js / jQuery / Select2

O `base.html` já não carrega estas bibliotecas. Em cada template filho que precise:

```django
{% block vendor_libs %}
  {% include 'partials/vendor_chartjs.html' %}
  {% include 'partials/vendor_select2.html' %}   {# já traz o jQuery #}
{% endblock %}
```

Só jQuery: `{% include 'partials/vendor_jquery.html' %}`.

Para encontrar as páginas afetadas:

```powershell
Get-ChildItem -Recurse -Include *.html -Path . -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch "node_modules|venv|staticfiles" } |
  Select-String -Pattern 'new Chart|Chart\(|\$\(|jQuery|select2' -List |
  Select-Object -ExpandProperty Path
```

Sintoma de uma página em falta: `$ is not defined`, `Chart is not defined` ou `select2 is not a function` na consola.

## 6. Consultas (passo 4): context processor com cache curta

Adapte os nomes de modelos e campos aos seus.

```python
# core/context_processors.py
from django.core.cache import cache

def notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    schema = getattr(getattr(request, "tenant", None), "schema_name", "public")
    key = f"notif:{schema}:{user.pk}"
    data = cache.get(key)
    if data is None:
        qs = Notificacao.objects.filter(usuario=user, lida=False).order_by("-created_at")
        data = {
            "notifications": list(qs.values("id", "title", "message", "url", "icon", "type", "created_at")[:5]),
            "notifications_count": qs.count(),
        }
        cache.set(key, data, 30)   # invalidar com signal ao criar / marcar como lida
    return data
```

- Carregue o utilizador com `select_related("funcionario__cargo")` (por exemplo no `get_user` do backend de autenticação) para evitar 2 queries por página.
- Use cache por tenant também para `interface_prefs`.
- Valide `cor_primaria` como hexadecimal no modelo (o valor entra num `<style>`).


##################################
##################################
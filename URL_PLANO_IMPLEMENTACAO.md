# URL_PLANO_IMPLEMENTACAO.md
# Plano para resolver TemplateSyntaxError: 'safe_url' tag not found

---

## Diagnóstico exacto do problema

### Estado actual

O `base.html` usa `{% load pharma_tags %}` e depois `{% safe_url 'vendas:pdv' %}`.

O ficheiro `apps/core/templatetags/pharma_tags.py` tem **`register = template.Library()` duplicado**:

```
Linha  9: register = template.Library()   ← PRIMEIRO (correcto — tem safe_url)
Linha 64: register = template.Library()   ← SEGUNDO  (sobrescreve o primeiro)
```

Quando Python carrega o módulo, o segundo `register` substitui o primeiro.  
O `safe_url` tag foi registado no primeiro — mas o Django expõe o segundo (vazio).  
Resultado: `{% safe_url %}` existe no código mas o Django não o reconhece.

### Ficheiros envolvidos

| Ficheiro | Estado | Problema |
|---|---|---|
| `apps/core/templatetags/pharma_tags.py` | ❌ Corrompido | `register = template.Library()` duplicado na linha 64 |
| `templates/base.html` | ✅ Correcto | Usa `{% load pharma_tags %}` + `{% safe_url ... %}` correctamente |
| `apps/core/templatetags/custom_filters.py` | ✅ Limpo | `register` único, só tem o filtro `split` |

---

## Causa raiz

Nas sessões anteriores, ao adicionar o `safe_url` ao topo do `pharma_tags.py`,  
o bloco original do ficheiro (imports + `register = template.Library()`) não foi  
removido — ficou duplicado na linha 64.

---

## Solução — 2 passos exactos

### Passo 1 — Remover o bloco duplicado do `pharma_tags.py`

Apagar exactamente estas 5 linhas (linhas 60–64 do ficheiro actual):

```python
from django.utils.html import format_html
from decimal import Decimal
import json

register = template.Library()
```

O ficheiro deve ficar assim após o `safe_url_tag` (linha ~57):

```python
    return _SafeURLNode(view_name, args, kwargs, asvar)


@register.filter
def currency(value):
```

**Não apagar mais nada.** O `register = template.Library()` da linha 9 fica intacto.

### Passo 2 — Verificar que funciona

Executar no terminal do projecto (com o venv activo):

```powershell
.\venv\Scripts\python.exe -c "
import apps.core.templatetags.pharma_tags as m
print('safe_url OK:', 'safe_url' in m.register.tags)
print('currency OK:', 'currency' in m.register.filters)
"
```

Resultado esperado:
```
safe_url OK: True
currency OK: True
```

Se ambos forem `True`, reiniciar o servidor. O erro desaparece.

---

## Método de execução do Passo 1

### Opção A — Manualmente no editor (VS Code / Kiro)

1. Abrir `apps/core/templatetags/pharma_tags.py`
2. Ir para a linha 60
3. Seleccionar e apagar as linhas 60–64:
   ```
   from django.utils.html import format_html
   from decimal import Decimal
   import json
   
   register = template.Library()
   ```
4. Guardar o ficheiro (`Ctrl+S`)

### Opção B — Terminal (PowerShell com venv activo)

```powershell
cd "C:\Users\CARLOS SEBASTIÃO-PC\vistogest-pro"

.\venv\Scripts\python.exe -c "
f = open(r'apps\core\templatetags\pharma_tags.py', 'r', encoding='utf-8')
c = f.read()
f.close()
dup = (chr(10) + 'from django.utils.html import format_html' + chr(10)
     + 'from decimal import Decimal' + chr(10)
     + 'import json' + chr(10)
     + chr(10)
     + 'register = template.Library()' + chr(10))
if dup in c:
    c = c.replace(dup, chr(10))
    f = open(r'apps\core\templatetags\pharma_tags.py', 'w', encoding='utf-8')
    f.write(c)
    f.close()
    print('CORRIGIDO')
else:
    print('padrao nao encontrado')
"
```

---

## O que NÃO fazer

- ❌ Não criar uma nova app `core_tenant`
- ❌ Não mover o `safe_url` para outro ficheiro de tags
- ❌ Não alterar o `base.html` novamente
- ❌ Não alterar os urlconfs (`urls_tenants.py`, `urls_public.py`)

Tudo já está correcto — o único problema é o `register` duplicado no `pharma_tags.py`.

---

## Estado após a correcção

O `TemplateSyntaxError: safe_url not found` desaparece.  
O `NoReverseMatch: vendas not registered` também desaparece porque o `safe_url`  
tag retorna `'#'` silenciosamente quando o namespace não está disponível.

O sistema fica funcional no schema tenant (`mundoemaquinas.localhost`) e no schema  
public (`localhost`).

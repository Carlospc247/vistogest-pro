# Correcção da numeração fiscal — VistoGest Pro

## Diagnóstico

A função colada em `apps/core_tenants/services.py` gera `FR A/2` correctamente quando `serie='A'`. Contudo, `DocumentoFiscal._gerar_numero_documento()` importa a função de `apps.fiscal.services.utils`, não a função de `apps/core_tenants/services.py`. Além disso, a implementação antiga trata o campo `serie` como uma etiqueta livre e não consulta a série registada/aprovada pela AGT. Se o valor passado for `FR A`, o formato montado por `f'{tipo_documento} {serie}/{numero}'` torna-se `FR FR A/2`.

A versão incluída em `numero_documento_agt.py` usa `SerieFiscalAGT` para os tipos electrónicos, respeita o intervalo autorizado e reconstrói o número a partir dos campos normalizados — não confia no texto `formatado` de uma função antiga.

## 1. Copiar o módulo central

Copie `numero_documento_agt.py` para:

`apps/fiscal/services/numero_documento_agt.py`

Não substitua todo o ficheiro `apps/fiscal/services/utils.py`, porque nele também pode existir `FiscalServiceError` e outros utilitários. Para evitar duas implementações activas, faça a função antiga `gerar_numero_documento()` em `apps/fiscal/services/utils.py` delegar para a função deste novo módulo, ou actualize todos os seus chamadores para importar o novo módulo.

## 2. Aumentar os campos que guardam a série e a sequência

Em `apps/fiscal/models.py`, actualize estes campos:

```python
# ContadorDocumento
serie = models.CharField(max_length=60, default='A')
ultimo_numero = models.PositiveBigIntegerField(default=0)

# DocumentoFiscal
serie = models.CharField(
    max_length=60,
    default='A',
    help_text='Código da série (seriesCode atribuído pela AGT, quando electrónico).',
)
numero = models.PositiveBigIntegerField(
    verbose_name='Número do Documento',
    help_text='Número sequencial autorizado dentro da série.',
)
numero_documento = models.CharField(
    max_length=60,
    verbose_name='Número Completo',
    help_text='Formato: TIPO CÓDIGO_DA_SÉRIE/SEQUÊNCIA (ex.: FT FT6325S2C/10006).',
    editable=False,
)
```

Isto é importante: os códigos de série AGT podem ser mais longos do que 10 caracteres e a resposta de exemplo da AGT aceita intervalos que excedem o limite de um `IntegerField` de 32 bits. Os campos novos exigem migração de schema tenant.

## 3. Substituir `DocumentoFiscal._gerar_numero_documento()`

No modelo `DocumentoFiscal`, substitua o método inteiro por este:

```python
def _gerar_numero_documento(self):
    """Reserva e valida o número fiscal através do motor central AGT."""
    if not self.empresa_id:
        raise ValidationError({
            'empresa': 'Associe o documento à empresa do tenant antes de numerar.'
        })

    from apps.fiscal.services.numero_documento_agt import gerar_numero_documento

    try:
        dados = gerar_numero_documento(
            empresa=self.empresa,
            tipo_documento=self.tipo_documento,
            serie=self.serie,
            data_emissao=self.data_emissao,
        )
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError({
            'numero_documento': f'O motor de numeração falhou: {exc}'
        }) from exc

    if not isinstance(dados, dict):
        raise ValidationError({
            'numero_documento': 'O motor de numeração devolveu um resultado inválido.'
        })

    sequencial = dados.get('sequencial', dados.get('numero'))
    codigo_serie = str(
        dados.get('series_code') or dados.get('serie') or ''
    ).strip()

    try:
        sequencial = int(sequencial)
    except (TypeError, ValueError) as exc:
        raise ValidationError({
            'numero_documento': 'O motor não devolveu uma sequência numérica válida.'
        }) from exc

    if sequencial < 1 or not codigo_serie:
        raise ValidationError({
            'numero_documento': 'A sequência ou o código da série está vazio/inválido.'
        })
    if any(ch.isspace() for ch in codigo_serie) or '/' in codigo_serie:
        raise ValidationError({
            'numero_documento': 'O código da série contém espaços ou barra inválidos.'
        })

    # Fonte de verdade: tipo + código de série + sequência. Não aceitar um
    # `formatado` vindo de outra função, pois pode conter o tipo duplicado.
    numero_canonico = f'{self.tipo_documento} {codigo_serie}/{sequencial}'
    if len(numero_canonico) > 60:
        raise ValidationError({
            'numero_documento': 'O número completo excede os 60 caracteres permitidos.'
        })

    formatado_antigo = str(dados.get('formatado') or '').strip()
    if formatado_antigo and formatado_antigo != numero_canonico:
        logger.warning(
            'Número formatado divergente ignorado: devolvido=%r; canónico=%r',
            formatado_antigo, numero_canonico,
        )

    self.numero = sequencial
    self.serie = codigo_serie
    self.numero_documento = numero_canonico
```

## 4. Garantir que o número é atribuído pelo servidor

Dentro de `DocumentoFiscal.save()`, na parte `if is_new`, substitua:

```python
if not self.numero or not self.numero_documento:
    self._gerar_numero_documento()
```

por:

```python
self._gerar_numero_documento()
```

Assim, a criação normal não pode injectar manualmente uma sequência ou contornar o contador. Documentos históricos/importados devem usar um fluxo de importação próprio, auditado, e não o fluxo normal de emissão.

Recomendo também colocar `@transaction.atomic` imediatamente acima de `def save(...)` de `DocumentoFiscal`. Dessa forma, se `full_clean()` ou a gravação falhar, a reserva da sequência é revertida na mesma transacção. Já existe `transaction` importado no cabeçalho do modelo.

## 5. Unificar as funções duplicadas

A função em `apps/core_tenants/services.py` deve ficar apenas como compatibilidade, chamando o motor central:

```python
def gerar_numero_documento(empresa, tipo_documento, serie='A', data_emissao=None):
    from apps.fiscal.services.numero_documento_agt import gerar_numero_documento as gerar
    return gerar(
        empresa=empresa,
        tipo_documento=tipo_documento,
        serie=serie,
        data_emissao=data_emissao,
    )
```

Faça o mesmo com qualquer `gerar_numero_documento()` antigo que continue em `apps/fiscal/services/utils.py`, ou altere os chamadores para importar directamente `apps.fiscal.services.numero_documento_agt`. Deve existir apenas um algoritmo de numeração.

## 6. Corrigir o tipo de documento do recibo

Na rotina `Recibo.gerar_documento_fiscal()` do módulo de vendas, a criação actual passa `tipo_documento="REC"`. O modelo `DocumentoFiscal` não tem esse código nas escolhas e a lista oficial da AGT usa `RC` (Recibo Emitido) ou `RG` (Outros Recibos). Para o recibo comum mostrado no código, altere a chamada para:

```python
tipo_documento="RC",
```

Confirme caso o documento represente um recibo de outra natureza, porque então poderá aplicar-se `RG`.

## 7. Migrações e teste

Faça backup da base de dados e reveja a migração gerada antes de aplicar:

```powershell
python manage.py makemigrations fiscal --name corrigir_numero_documento_agt
```

Como `fiscal` é uma app tenant-local na arquitectura descrita, aplique a migração aos schemas tenant com o comando de migração usado pelo projecto, normalmente:

```powershell
python manage.py migrate_schemas --tenant
```

Depois teste num tenant de homologação que tenha uma `SerieFiscalAGT` activa, com `document_type='FR'`, `series_year` igual ao ano de emissão, `series_status='A'` ou `'U'`, e `first_document_no`/`last_document_no` sincronizados com a resposta da AGT. Se houver várias séries válidas para o mesmo tipo/ano, indique o `seriesCode` pretendido em vez de deixar o motor escolher.

**Não renumere documentos já emitidos e assinados directamente na base de dados.** A correcção passa a aplicar-se às novas emissões; qualquer documento emitido com número incorrecto precisa de tratamento fiscal/auditoria próprio.

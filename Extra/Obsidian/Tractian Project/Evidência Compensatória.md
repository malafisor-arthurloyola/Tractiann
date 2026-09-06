---
tags: [architecture, evidence, api, tools]
aliases: [Compensação, Evidência Compensatória, Retry]
---

# Evidência Compensatória

## O problema: retry não funciona nesta API

A tentação natural, diante de um envelope `unavailable`, é tentar de novo. **Não adianta.**

`resolve_mode` (em `api/app/prob.py`) é um hash puro:

```python
key = f"{seed or 'noseed'}|{resource}|{category}"
r = _hash01(key)   # sha256 determinístico
```

Mesma URL, mesmos parâmetros → **mesmo envelope, sempre**. Repetir o GET devolve
byte a byte a mesma resposta.

E há uma camada acima: os `overrides` de `data/seed.json` vencem até o parâmetro `seed`.

```python
ov = overrides.get(resource, {})
if category in ov:
    return Mode(ov[category])   # ignora seed completamente
```

```
asset_G501 → analyses=inconclusive, rms=unavailable, data_quality=partial, baseline=partial
asset_S420 → analyses=conflict
asset_M205 → analyses=conflict
```

Esses são os **cenários desenhados do case**. `asset_G501/rms` é `unavailable` por
design. O gabarito quer que o agente raciocine em volta disso, não que insista.

> [!warning] Por que não passar um `seed` diferente
> Mecanicamente funcionaria — o hash mudaria e o modo poderia vir melhor. Mas isso é
> re-rolar o dado da simulação até gostar do resultado. Foge da premissa do case
> ("a API é probabilística de propósito, o agente precisa lidar bem com isso") e é
> indefensável numa banca.

## A solução: buscar outro caminho para a mesma pergunta

Quando um dado falha, o agente busca um endpoint **diferente** que responda à mesma
questão de fundo. É o que os `expected_path` do gabarito fazem.

| categoria vazia/degradada | compensação | o que destrava |
| :--- | :--- | :--- |
| `baseline` | `model`, `asset_info`, `knowledge` | `coverage[].can_learn_baseline` diz se aquele tipo de máquina sequer aprende baseline |
| `analyses` | `analysis_detail`, `model`, `knowledge` | `processing_state=delayed` explica insight ausente; o detalhe recupera `evidence`/`limitations` omitidos na lista |
| `spectrum` | `asset_info` | frequências características (bpfo/bpfi/bsf/ftf, rotation_rpm, line_frequency) — sem elas o FFT é ininterpretável |
| `data_quality` | `asset_info`, `knowledge` | `sensor_status` explica a falta de dado |

## Tools que faltavam

A versão antiga só sabia chamar 5 categorias e nunca alcançava `GET /assets/{id}`,
`GET /models/{id}` nem `GET /analyses/{id}`. Em **6 dos 13** casos de treino a
trajetória esperada passava por categorias fisicamente inalcançáveis.

`asset_info` foi promovido ao núcleo (`CORE_TOOLS`) porque quase todo raciocínio
depende dele. `model`, `analysis_detail` e `knowledge` entram como compensatórias.

## Busca de conhecimento

`search_knowledge` faz `contains` da **query inteira** contra título e corpo. A versão
antiga buscava `f"manutenção {asset_id}"` — procurar um id de ativo numa base de
documentos nunca dava match. Agora um termo curto é derivado do texto do ticket
(`rolamento`, `rms`, `eletric`, `sintom`), com `baseline` como padrão.

## Relacionado
- [[Quality Check Node]]
- [[Envelope de Resposta]]
- [[Camada MCP - Tools]]
- [[Domínio Industrial Tractian]]

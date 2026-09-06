---
tags: [architecture, quality, node]
aliases: [Quality Check, Nó de Qualidade, Balanço de Evidência]
---

# Quality Check Node

## O que é
Nó dedicado no [[Grafo LangGraph]] que classifica a **força da evidência** coletada.
É o **dono único** da política sobre respostas não-completas.

> [!important] Mudança de papel (v3)
> O nó **anota, não bloqueia**. Antes ele era um porteiro: qualquer modo não-completo
> em `baseline` ou `analyses` virava veredicto `unavailable`, que curto-circuitava o
> `decide` num escalonamento hardcoded. Resultado: **10 de 13 tickets escalavam** e o
> LLM nunca era consultado. Ver [[Auditoria e Bugs Críticos]].

## Classificação dos modos
O erro central da versão antiga foi tratar `conflict` e `partial` como ausência de dado.
Olhando o `_apply_mode` da API, eles não são:

| modo | classificação | o que acontece com o payload |
| :--- | :--- | :--- |
| `complete` | **utilizável** | íntegro |
| `conflict` | **utilizável** | íntegro **+** flag `conflict: true` — mais informativo, não menos |
| `partial` | **utilizável** | só campos secundários omitidos (`_PARTIAL_DROP`); `baseline.state` e `detection_mode` continuam lá |
| `inconclusive` | vazio | reduzido a `{inconclusive, asset_id}` |
| `unavailable` | vazio | `{}` |

## Veredictos
- `ok` — tudo completo
- `partial` — há degradado, mas tudo continua utilizável
- `incomplete` — alguma categoria veio vazia, com compensação disponível
- `unavailable` — **nada** utilizável (único caso de bloqueio real, que na prática não ocorre nos 17 cenários)

## Roteamento
```
quality_check → há compensação pendente e orçamento → investigate
              → caso contrário                       → decide
```
Nenhum veredicto manda para `escalate`. Quem decide escalar é o LLM, olhando a
evidência real — ver [[Ações Reais no Nó Act]] e [[Escalamento]].

## Por que um nó só
Se a regra de "resposta incompleta" estivesse espalhada em vários nós, ficaria
inconsistente. Centralizar permite mudar a política num lugar só — foi o que
permitiu a correção acima ser cirúrgica.

## Relacionado
- [[Envelope de Resposta]]
- [[Evidência Compensatória]]
- [[Grafo LangGraph]]
- [[Auditoria e Bugs Críticos]]

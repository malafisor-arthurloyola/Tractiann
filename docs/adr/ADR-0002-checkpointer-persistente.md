# ADR-0002 — Checkpointer persistente no Postgres para a fila de aprovações

## Status: Aceita
## Data: 2026-09-06

## Contexto

O agente pausa antes de qualquer escrita na plataforma da Tractian. O nó `act` chama
`interrupt()`, o grafo congela, e a execução só continua quando alguém decide — é o
guard-rail que impede uma ação com impacto físico de acontecer sem autorização.

O grafo era compilado com `MemorySaver`, que guarda o estado congelado na RAM do processo.
Isso funciona enquanto quem pausa e quem retoma são a mesma execução do mesmo programa —
que é exatamente o caso de um ticket disparado pelo botão da interface e confirmado na
mesma tela, segundos depois.

Não é o caso de uma plataforma. Uma plataforma recebe tickets continuamente, analisa cada
um, e **notifica** quando precisa de um humano. O humano chega depois, por outro caminho,
possivelmente em outra máquina. Com o estado na memória:

- a ingestão dos tickets (um script) pausava execuções que a interface (outro processo)
  não conseguia enxergar — a caixa de entrada nascia vazia por construção;
- reiniciar o Streamlit descartava, em silêncio, toda ação que esperava aprovação;
- não havia como responder "o que está parado agora?" sem reprocessar tudo.

A primeira tentativa de contornar isso foi um botão na interface que reprocessava, dentro
da sessão, os tickets que a última avaliação apontara como `act`. Funcionava como
demonstração e falhava como arquitetura: a fila continuava sendo um efeito colateral da
sessão do navegador, dependia de um arquivo de resultado anterior para saber o que rodar,
e não sobrevivia a um refresh.

## Decisão

Compilar o grafo com **`PostgresSaver`** (`langgraph-checkpoint-postgres`), com
`MemorySaver` apenas como fallback quando o banco não responde.

Uma execução congelada passa a ser uma linha no banco. Junto, duas tabelas de plataforma:

- **`fila_aprovacoes`** — a caixa de entrada do operador. Uma linha por ação pendente,
  guardando o `thread_id` do checkpoint, a ação pedida, a justificativa do agente e as
  lacunas de dado que ele reconhece ter. É o `thread_id` que permite a qualquer processo
  chamar `Command(resume=True)` no ponto exato onde o grafo parou.
- **`execucoes`** — passou a registrar `thread_id`, `status`, `split` e a avaliação, além
  do trace. Deixou de ser log e virou a tabela de tickets da plataforma.

Um módulo novo, `agent/ingest.py`, é a porta de entrada: roda o grafo sobre os tickets e
**não aprova nada**. É o oposto deliberado de `eval/runner.py`, que aprova todo
`interrupt()` automaticamente porque precisa pontuar a trajetória inteira sem operador.

## Consequências

**Positivas**

- A caixa de entrada mostra o que outro processo congelou, que é o comportamento que uma
  plataforma de notificações precisa ter.
- Nenhuma ação pendente se perde num reinício.
- Autonomia e acerto de decisão saem de contar linhas do banco. Não dependem de arquivo de
  avaliação, e portanto cobrem também tickets sem gabarito.
- A ingestão grava decisão esperada e nota de trajetória quando há gabarito: operar e medir
  produzem as mesmas linhas, em vez de dois mundos que precisam ser reconciliados à mão.

**Negativas e riscos**

- A plataforma passa a depender do Postgres para a funcionalidade central, não só para
  histórico. Sem banco, o sistema cai para memória e **avisa na interface** — mas a fila
  fica vazia, e isso precisa ser legível para quem opera, não silencioso.
- Duas dependências novas: `langgraph-checkpoint-postgres` e `psycopg[binary]`. O `[binary]`
  não é opcional no Windows — sem ele o psycopg 3 não encontra a libpq e o checkpointer
  regride para memória.
- O checkpoint guarda o estado inteiro do grafo, incluindo os envelopes brutos da API. As
  tabelas crescem por ticket processado; não há política de retenção.
- **Não há controle de acesso.** Qualquer pessoa com a interface aberta aprova qualquer
  ação, e `resolvido_por` grava sempre `operador`. Num sistema real, autorizar escrita em
  ativo industrial exigiria identidade, papéis e trilha de auditoria — a coluna existe, o
  mecanismo não.

## Alternativas consideradas

**Manter o `MemorySaver` e reconstruir a fila na sessão.** Foi o que existia. Rejeitada: a
fila deixava de refletir o sistema e passava a refletir o navegador. Um operador que
abrisse a plataforma numa segunda-feira não veria o que ficou pendente na sexta.

**Uma tabela de pendências sem trocar o checkpointer.** Registraria o que está esperando,
mas não *o estado do grafo* — retomar exigiria reexecutar o ticket do zero, o que perde a
investigação já feita, gasta chamadas de API e pode produzir uma decisão diferente da que o
humano aprovou. A pendência precisa apontar para um checkpoint real.

**`SqliteSaver` em vez de Postgres.** Suficiente para um processo, problemático para
vários escrevendo ao mesmo tempo, e o projeto já sobe Postgres para o Phoenix e o histórico.
Trocaria uma dependência existente por outra sem ganho.

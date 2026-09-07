"""Configuração compartilhada dos testes.

O grafo passou a usar um checkpointer persistente no Postgres, o que é correto
para a plataforma mas errado para a suíte: os testes ficariam dependentes de um
container de pé e passariam a sujar o banco de desenvolvimento com checkpoints
de execuções fictícias.

`CHECKPOINTER=memory` é lido por `agent/graph/checkpointer.py` e precisa estar no
ambiente **antes** de `agent.graph.agent` ser importado — o grafo é compilado no
import do módulo. O conftest é carregado pelo pytest antes de qualquer módulo de
teste, então este é o único lugar onde a variável chega a tempo.
"""
import os

os.environ.setdefault("CHECKPOINTER", "memory")

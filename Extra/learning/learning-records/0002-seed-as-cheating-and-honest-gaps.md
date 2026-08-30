# Entendeu seed como trapaça e gaps como registro honesto

O usuário identificou corretamente que usar `seed=complete` para forçar dados
completos seria "cheating" — e confirmou que o agente não deve fazer isso.
Também entendeu que os gaps (o que faltou) devem ser registrados honestamente
para que a decisão sempre saiba o que o agente NÃO teve disponível.

**Status:** active

**Evidence:** Pergunta direta sobre "cheating" + insistência em que gaps sejam
anotados para que a decisão sempre considere o que faltou.

**Implications:** O usuário valoriza honestidade e transparência na arquitetura.
Posso avançar para avaliá-los como critérios de avaliação (métrica: honestidade
sob incerteza) e integrar gaps no `decide` node como já fizemos.

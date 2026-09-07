# Guia de Comandos Essenciais do Projeto Tractian

Este documento serve como uma referência rápida para os comandos mais importantes do projeto.

## 1. Configuração Inicial

### `make setup`

&gt; **Descrição:** Este comando realiza a configuração inicial completa do ambiente. Deve ser executado apenas uma vez, ou se você precisar resetar e reinstalar tudo.
&gt; **O que ele faz:**
&gt; 1.  Cria o ambiente virtual Python (`.venv`).
&gt; 2.  Instala todas as dependências do projeto (API e agente) usando `uv`.
&gt; 3.  Gera os dados sintéticos (`data/`, `agent-input/`, `eval/`).

```bash
make setup
```

## 2. Operações Diárias da API

### `make up`

&gt; **Descrição:** Inicia a API industrial da Tractian em background.
&gt; **O que ele faz:**
&gt; 1.  Sobe o servidor FastAPI na porta `8000`.
&gt; 2.  **Atenção:** Você deve estar no diretório raiz do projeto para que funcione.

```bash
make up
```

### `make stop`

&gt; **Descrição:** Encerra a API industrial que está rodando em background.

```bash
make stop
```

### `make test`

&gt; **Descrição:** Roda os testes automatizados da API industrial.

```bash
make test
```

### `make data`

&gt; **Descrição:** Regenera os dados sintéticos do projeto (arquivos `.parquet`, `agent-input/`, `eval/`).

```bash
make data
```

### `make clean`

&gt; **Descrição:** Para a API, apaga todos os dados gerados (`data/`, `agent-input/`, `eval/`) e remove o ambiente virtual (`.venv`).

```bash
make clean
```

## 3. Ambiente Python

### Ativar o Ambiente Virtual

&gt; **Descrição:** Para executar scripts Python ou instalar pacotes diretamente no ambiente virtual, você precisa ativá-lo.
&gt; **Atenção:** O ambiente virtual está dentro da pasta `api/`.

**No Windows (PowerShell):**

```powershell
cd api
.venv\Scripts\Activate.ps1
```

**No Linux/macOS (ou Git Bash no Windows):**

```bash
cd api
source .venv/bin/activate
```

Para desativar, digite `deactivate` no terminal.

## 4. Explorando a API

### Swagger UI

&gt; **Descrição:** Após executar `make up`, você pode visualizar a documentação interativa da API (Swagger UI) para explorar os endpoints, modelos e fazer requisições de teste diretamente no navegador.

```
http://localhost:8000/docs
```

### Requisições de Exemplo (com `curl` ou `Invoke-WebRequest`)

&gt; **Descrição:** Exemplo de como fazer uma requisição `GET` para a API.

**Exemplo de requisição GET (companhia `comp_mineracao_andes`):**

**No Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/companies/comp_mineracao_andes" -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json
```

**No Linux/macOS (ou Git Bash no Windows):**

```bash
curl http://localhost:8000/companies/comp_mineracao_andes
```

**Exemplo de requisição com `x-user-id` (para endpoints que exigem autenticação):**

**No Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/users/me" -Headers @{"x-user-id"="usr_ana"} -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json
```

**No Linux/macOS (ou Git Bash no Windows):**

```bash
curl -H "x-user-id: usr_ana" http://localhost:8000/users/me
```

## 5. Variáveis de Ambiente do Agente (`agent/.env.example`)

&gt; **Descrição:** Este arquivo define as variáveis de ambiente necessárias para o agente se conectar ao LLM (Groq/OpenRouter) e à API Tractian. Copie-o para `agent/.env` e configure suas chaves.

```ini
# LLM — compatível com a API da OpenAI
OPENAI_API_KEY=coloque_sua_chave_gratuita_aqui
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile

# Alternativa via OpenRouter (descomente e preencha se preferir):
# OPENAI_API_KEY=sua_chave_openrouter
# OPENAI_BASE_URL=https://openrouter.ai/api/v1
# OPENAI_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Endereço da API industrial Tractian (sobe com `make up`)
TRACTIAN_API_URL=http://localhost:8000
```

### Criar `agent/.env`

```bash
make agent-env
# Edite 'agent/.env' com suas credenciais
```

---

## Observabilidade

### `make up-obs`

> **Descrição:** Sobe a stack de observabilidade inteira e espera o Phoenix ficar pronto.
> **O que ele faz:**
> 1. Sobe Postgres (`:5432`) e Phoenix (`:6006`) via Docker.
> 2. Aguarda o Phoenix aceitar conexões — sem isso o primeiro lote de spans se perde.
> 3. Cria a tabela `execucoes`.
>
> O Phoenix persiste os traces **no mesmo Postgres**, em schema separado, então eles
> sobrevivem a `docker compose restart`.

```bash
make up-obs
```

> **Lembrete:** o tracing só liga com `PHOENIX_ENABLED=1` em `agent/.env`. Se estiver ligado e
> a instrumentação falhar, o programa para com a causa na tela — falha silenciosa aqui é
> indistinguível de "não há o que tracear".

## Avaliação

### `make eval` · `make run`

> `eval` roda o split de treino **sem** o juiz LLM — rápido, para desenvolvimento.
> `run` roda o mesmo split **com** o juiz.

```bash
make eval
make run
```

### `make derivados`

> **Descrição:** Roda os seis cenários construídos neste projeto, sobre ativos que o case
> original não usa.
> **Atenção:** o resultado é reportado **à parte**. Um gabarito escrito por quem também
> escreveu o agente pode favorecê-lo sem intenção — nunca some com os números dos 17 originais.

```bash
make derivados
```

### `make prova-final`

> **Descrição:** Roda o split de teste *held-out* — os 4 tickets que nunca foram usados no
> desenvolvimento.
> **Regra:** roda **uma vez só**, no fim. Ajustar o agente depois de ver esse resultado
> transforma aqueles tickets em treino, e não existe mais conjunto limpo.

```bash
make prova-final
```

### `make evolucao` · `make evolucao-md`

> **Descrição:** Tabela de evolução entre versões, juntando a tabela `execucoes` do Postgres
> com as anotações do juiz gravadas no Phoenix. A versão `-md` sai em markdown.

```bash
make evolucao
make evolucao --modelos     # agrupa pelo modelo que de fato respondeu
```

> O `--modelos` existe porque roteadores escolhem o modelo por requisição. Sem ele, uma média
> da rodada mistura modelos com vieses diferentes.

## Medição de custo e latência

O cache de decisões devolve resultados do disco sem chamar o LLM. Para medir custo e latência
**reais**, é obrigatório desligá-lo — senão você mede o tempo de ler um JSON.

```bash
.venv\Scripts\python.exe -m eval.runner --split train --no-cache
```

## Testes

```bash
.venv\Scripts\python.exe -m pytest tests/ -q     # 73 testes do agente, sem chamar LLM
make test                                          # 39 testes da API industrial
```

### `make demo`

> **Descrição:** Sobe a plataforma com todos os tickets já processados. Use antes de uma
> apresentação.
> **O que ele faz, em ordem:**
> 1. Sobe a API industrial (`:8000`).
> 2. Sobe Postgres e Phoenix, esperando o Phoenix aceitar conexões, e cria/atualiza o schema.
> 3. **Ingere os 17 tickets** (`python -m agent.ingest`) — cada um é investigado e decidido.
>    Toda ação que exigiria escrita na plataforma **congela na fila de aprovações**.
> 4. Abre o console Streamlit, já com métricas, traces e a caixa de entrada populados.

```bash
make demo
```

> **Duração:** ~6 minutos (17 tickets × ~21s). O custo é das chamadas à API industrial —
> são 9 por ticket, e o cache de decisão poupa o LLM, não as tools.

### Ingestão ≠ avaliação

São dois modos de rodar o mesmo grafo sobre os mesmos tickets, e a diferença está
inteiramente no tratamento do `interrupt()`:

| | `make eval` (avaliação) | `make ingest` (plataforma) |
| :--- | :--- | :--- |
| pergunta que responde | o agente decide certo? | o que o agente quer fazer agora? |
| ao chegar num `interrupt()` | **aprova sozinho**, para pontuar a trajetória inteira | **congela** e enfileira para um humano |
| onde grava | `eval/results-<split>.json` | tabelas `execucoes` e `fila_aprovacoes` |
| deixa fila pendente? | nunca, por construção | sim — é o ponto |

A ingestão também avalia: quando o ticket tem gabarito, a decisão esperada e a nota de
trajetória são gravadas junto. Por isso a aba **Notificações** mostra acerto de decisão
sem depender de nenhum arquivo de avaliação.

```bash
make ingest              # os 17 tickets
make ingest-derivados    # 17 + os 6 cenários derivados
```

```bash
.venv/Scripts/python.exe -m agent.ingest --tickets TKT-INV-09 TKT-EXE-12
```

### Por que a fila sobrevive a reinícios

O grafo usa o **`PostgresSaver`** como checkpointer (`agent/graph/checkpointer.py`). Uma
execução congelada no `interrupt()` é uma linha no banco, não um objeto na memória do
processo. Consequências práticas:

- a ingestão pausa num processo e a interface retoma em outro;
- fechar o navegador ou reiniciar o Streamlit não perde ação nenhuma;
- o `thread_id` guardado em `fila_aprovacoes` é a chave que o botão **Aprovar** usa para
  chamar `Command(resume=True)` no checkpoint certo.

Sem Postgres, o sistema cai para `MemorySaver` e avisa na aba — a fila fica vazia porque
não há onde compartilhar o estado. `CHECKPOINTER=memory` força esse modo (é o que a suíte
de testes usa, para não depender de um container).

### O que fica pronto depois do `make demo`

| aba | disponível? |
| :--- | :--- |
| Notificações → caixa de entrada | sim — as ações congeladas na ingestão |
| Notificações → autonomia e acerto | sim — lidos das tabelas do Postgres |
| Métricas & Avaliação | sim — lê de `eval/results-*.json` |
| Phoenix (`:6006`) | sim — um trace por ticket ingerido |
| Diagnóstico & HITL | precisa abrir um ticket na barra lateral |
| Trace & Sinais | precisa executar um ticket na sessão |

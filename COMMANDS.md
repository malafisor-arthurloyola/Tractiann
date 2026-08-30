# Guia de Comandos Essenciais do Projeto Tractian

Este documento serve como uma referência rápida para os comandos mais importantes do projeto.

## 1. Configuração Inicial

### `make setup`

&gt; **Descrição:** Este comando realiza a configuração inicial completa do ambiente. Deve ser executado apenas uma vez, ou se você precisar resetar e reinstalar tudo.
&gt; **O que ele faz:**
&gt; 1.  Cria o ambiente virtual Python (`api/.venv`).
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

&gt; **Descrição:** Para a API, apaga todos os dados gerados (`data/`, `agent-input/`, `eval/`) e remove o ambiente virtual (`api/.venv`).

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

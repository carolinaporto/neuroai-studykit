# NeuroAI Study Kit

App pessoal de *practice testing* para o curso GENED 1201. Ingere material de aula
(PDF, slides, transcrição), gera questões ancoradas no texto-fonte, e corrige respostas
digitadas de memória contra uma rubrica derivada daquele texto.

A arquitetura completa está em @docs/ARCHITECTURE.md. O trabalho é feito **um marco por
vez**, na ordem de @docs/IMPLEMENTATION_PLAN.md.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2,
  pydantic-settings, Alembic, Postgres 16 + pgvector. Gerenciado com `uv`.
- **Frontend:** React + Vite + TypeScript, TanStack Query, Tailwind.
- **Testes:** pytest (+ pytest-asyncio) no backend, vitest no frontend.
- **Lint/format:** ruff (backend), prettier + eslint (frontend).

## Comandos

```bash
make up            # docker compose up -d (postgres+pgvector)
make api           # uvicorn com reload
make worker        # consumidor da fila de ingestão
make web           # vite dev server
make test          # pytest + vitest
make lint          # ruff check --fix + prettier
make migrate m=".."  # alembic revision --autogenerate
make upgrade       # alembic upgrade head
python -m ingest.cli sync content/week01   # ingestão local, sem servidor
```

Se um comando ainda não existe no `Makefile`, crie-o no marco em que for necessário.

## Invariantes — não violar sem me perguntar

1. **Toda questão é ancorada.** Um `Item` sempre referencia `chunk_ids`, e cada ponto da
   rubrica carrega `support_quote` que existe **literalmente** no texto do chunk. Se a
   citação não bater por comparação de string, o item é rejeitado na validação. Nunca
   relaxe essa checagem para "quase igual" ou similaridade semântica.
2. **Nota é calculada em Python, não pelo LLM.** O modelo só decide, por ponto da rubrica,
   `covered: true|false`. O score é `Σ(peso coberto) / Σ(peso)`. Nunca peça um número ao
   modelo.
3. **Segredo nenhum chega ao frontend.** A chave da API vive só em variável de ambiente
   do backend. Nada de segredo em `VITE_*` — essas variáveis vão para o bundle do cliente.
   O repo é público e o histórico do git é permanente.
4. **`packages/ingest` não importa nada de `apps/api`.** Recebe bytes, devolve objetos
   Pydantic. Sem sessão de banco, sem `Depends`, sem config de app. É o que permite rodar
   e testar a ingestão sem subir servidor.
5. **Nenhum teste chama a API do Anthropic.** Todo acesso a LLM passa pelo protocolo
   `LLMClient` (`core/llm.py`); os testes injetam `FakeLLM` com respostas fixas, incluindo
   respostas malformadas para exercitar os validadores.
6. **`content/` é gitignored.** Material do GENED não entra no repo nem em fixture. Os
   testes usam o corpus sintético de `tests/fixtures/` — textos escritos por nós.
7. **Endpoint de correção tem escopo fechado.** `/api/study/answer` recebe `item_id` e o
   texto do aluno, nunca um prompt. O texto do aluno entra na chamada como dado
   delimitado, jamais concatenado no papel de instrução.
8. **Multiusuário está no schema desde o começo.** `owner_id`, `Deck.visibility` e
   `User.role` existem e toda query de deck passa por um filtro que recebe o usuário
   atual — mesmo havendo um usuário só. Não "simplifique" removendo isso.

## Convenções

- Type hints em todo código Python novo; `ruff` limpo antes de commitar.
- Toda mudança de modelo ORM vem com uma migration Alembic no mesmo commit.
- Schemas de entrada/saída da API em `apps/api/schemas/`, separados dos modelos ORM.
  Router nunca retorna objeto ORM direto.
- IDs são UUID v4. Timestamps são `timestamptz`, sempre UTC.
- Locators são jsonb com formato fixo: `{"page": 7}`, `{"slide": 12}`, `{"t0": 872, "t1": 965}`.
- Prompts de LLM são arquivos versionados em `packages/ingest/prompts/`, não strings
  inline. O hash do arquivo vai para `Item.gen_prompt_version`.
- Mensagens de commit em inglês, formato convencional (`feat:`, `fix:`, `test:`, `chore:`).
- Erros de LLM (JSON inválido, schema quebrado): uma retentativa, depois falha o job com
  o erro registrado em `IngestJob.error`. Não invente valor default para campo faltante.

## Como trabalhar comigo

- **Um marco por sessão.** Leia o marco atual no plano de implementação, proponha o
  caminho em plan mode, espere aprovação, implemente, e pare no critério de aceite.
  Não avance para o marco seguinte sem eu pedir.
- **Critério de aceite é lei.** Cada marco no plano tem um. Quando você acha que terminou,
  rode a verificação concretamente (comando, teste, requisição) e me mostre a saída real.
  Não declare pronto com base em leitura do código.
- **Pergunte antes de:** adicionar uma dependência nova, mudar schema fora do escopo do
  marco, introduzir um serviço externo (Redis, fila gerenciada, provedor de auth), ou
  alterar qualquer um dos invariantes acima.
- Prefira função pura e testável a método que precisa de banco. Se algo é difícil de
  testar sem mock elaborado, o desenho provavelmente está errado — me diga.
- Não escreva código para as fases futuras "já que estamos aqui". Abstração especulativa
  é o principal jeito de este projeto morrer pela metade.

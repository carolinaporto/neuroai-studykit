# NeuroAI Study Kit — Arquitetura

**Curso:** GENED 1201 — Foundations of NeuroAI
**Stack:** FastAPI (Python) + React (Vite/TS) + Postgres/pgvector
**Modo de IA:** banco de questões pré-gerado (offline) + correção ao vivo contra a fonte
**Acesso:** repositório público (portfólio), site privado (uso pessoal), com as costuras
prontas para abrir a estranhos ou a colegas depois, sem refatoração

---

## 1. O princípio que organiza tudo

O requisito pedagógico do curso não é "um site de quiz". É **practice testing**: o sistema
tem que te obrigar a *gerar* a resposta de memória e depois *verificar* contra o material
primário da aula.

Disso sai a regra que define o schema inteiro:

> **Toda questão carrega um ponteiro para o trecho exato da fonte que a justifica.**

Uma questão sem âncora não entra no banco. A correção não julga sua resposta contra a
opinião do modelo — julga contra uma rubrica derivada do trecho, e devolve o trecho junto
com o feedback (slide 12, página 7, 14:32–16:05). É isso que transforma o app de "IA me
disse que errei" em "eis a frase da aula que você não recuperou".

Duas consequências práticas:

- **Geração é offline e revisada por você.** Questão gerada nasce `draft`. Você aprova
  (ou edita) antes de ela virar item de estudo. Revisar 30 questões por semana *já é*
  estudo ativo, e é o filtro que impede alucinação de contaminar o kit.
- **Correção é online, mas de escopo fechado.** O endpoint recebe `item_id + resposta`,
  nunca um prompt livre. Isso é ao mesmo tempo a defesa contra abuso do site público e
  a garantia de que a correção sempre olha para a fonte certa.

---

## 2. Visão geral

```mermaid
flowchart LR
  subgraph Entrada
    A1[Upload PDF/PPTX na UI]
    A2[Transcrição de vídeo]
    A3[Pasta content/ no repo + CLI]
  end

  A1 & A2 & A3 --> Q[(job queue<br/>Postgres)]
  Q --> W[Worker de ingestão]

  W --> P[parse + locators]
  P --> C[chunking semântico]
  C --> E[embeddings]
  C --> G[geração LLM<br/>structured output]
  G --> V[validação:<br/>quote literal + dedup]
  V --> DB[(Postgres + pgvector)]

  DB --> R[UI de revisão<br/>draft → approved]
  R --> DB

  DB --> API[FastAPI]
  API --> S[Study Runner<br/>React]
  S -->|item_id + resposta| API
  API --> GR[Grader LLM<br/>rubrica + chunk]
  GR --> API
  API --> SCH[Scheduler FSRS]
```

---

## 3. Modelo de dados

```
User
  id, email, role: owner | student | demo, created_at

Source                        # uma aula, deck, transcrição ou paper
  id, week:int, title, kind: lecture_pdf | slides | transcript | paper | notes
  storage_uri, sha256, page_count/duration, status, ingested_at
  -- sha256 evita reingerir o mesmo arquivo

Chunk                         # a ÂNCORA de citação
  id, source_id, ordinal, text
  locator: jsonb  -- {page: 7} | {slide: 12, has_notes: true} | {t0: 872, t1: 965}
  token_count, embedding: vector(1536)

Item                          # uma questão
  id, source_id, chunk_ids: uuid[]
  type: free_recall | term_def | cloze | mcq | compare | application
  prompt, reference_answer
  rubric: jsonb   -- [{id, point, weight, support_quote, chunk_id}, ...]
  choices: jsonb  -- só para mcq
  difficulty:1-5, bloom: recall|understand|apply|analyze
  topics: text[]  -- "receptive fields", "backprop", "predictive coding"
  status: draft | approved | edited | retired
  gen_model, gen_prompt_version, created_at

Deck
  id, owner_id, title, kind: week | topic | exam_prep | demo
  visibility: private | shared | public_demo   -- costura: só 'private' é usado na v1
  DeckItem(deck_id, item_id, position)

Attempt
  id, user_id, item_id, response_text
  score: float 0-1, rubric_hits: jsonb  -- [{point_id, covered, evidence}]
  misconceptions: text[], feedback_md
  grader_model, latency_ms, created_at

ReviewState                   # FSRS / SM-2 por (user, item)
  user_id, item_id, stability, difficulty, due_at, reps, lapses, last_grade

IngestJob
  id, source_id, kind, status: queued|running|done|failed
  attempts, error, payload: jsonb, locked_at, locked_by
```

Notas de design:

- `rubric.support_quote` é o guard-rail barato: se a citação que o modelo alega não
  aparecer *literalmente* no chunk, o item é descartado na validação. Sem chamada extra
  de LLM, pega a maior parte das invenções.
- `topics[]` é o que alimenta o painel de fraquezas. Mantenha um vocabulário controlado
  (`topics.yaml` no repo) e peça ao gerador para escolher dessa lista — senão você
  termina com "backprop", "back-propagation" e "gradient descent" como três tópicos.
- `Attempt` guarda a resposta bruta. Depois de um mês você tem um corpus do que você
  *acha* que sabe versus o que recupera — que é, inclusive, material para o check-in
  semanal.
- **As costuras de multiusuário existem desde a v1, a UI não.** `owner_id`,
  `visibility` e `User.role` entram no schema agora e toda consulta de deck já passa por
  um filtro que recebe o usuário atual — mesmo havendo um usuário só. É barato agora e
  caro depois: abrir para colegas ou para um demo público passa a ser escrever a UI de
  convite e mudar um valor de enum, não migrar tabelas e auditar cada query.

---

## 4. Pipeline de ingestão

Três entradas, um caminho único a partir do `IngestJob`:

| Entrada | Parser | Locator gerado |
|---|---|---|
| PDF de aula/paper | PyMuPDF (`fitz`) | `{page: n}` |
| Slides `.pptx` | python-pptx (texto + speaker notes) | `{slide: n}` |
| Transcrição | VTT/SRT existente, ou `faster-whisper` | `{t0, t1}` em segundos |
| `content/` no repo | `python -m ingest.cli sync content/week03` | herda do tipo do arquivo |

Etapas:

1. **Hash e dedup de fonte** — `sha256` igual, pula.
2. **Parse** preservando o locator por bloco de texto.
3. **Chunking semântico** — agrupa por heading/slide, alvo de 500–900 tokens, overlap de
   ~15%. Nunca corte no meio de uma definição: prefira quebrar em heading, e se um slide
   for curto, junte com o vizinho mantendo os dois locators.
4. **Embeddings** dos chunks (pgvector) — serve para dedup e para "me mostre tudo do curso
   sobre X".
5. **Geração** — 1 chamada por grupo de chunks, saída estruturada validada por um modelo
   Pydantic (`GeneratedItemBatch`). Peça uma *mistura* de tipos por chunk, não 5 questões
   do mesmo formato. O prompt vai versionado em `packages/ingest/prompts/generate_v3.md`
   e o hash dele fica em `Item.gen_prompt_version` — assim você sabe quais questões vieram
   de qual versão quando melhorar o prompt.
6. **Validação** — quote literal presente no chunk; rubrica com 2–5 pontos; nenhum item
   respondível sem ter lido a fonte (rejeitar "O que é X?" quando X está no enunciado).
7. **Dedup de item** — embedding do `prompt`, descarta se cosseno > 0.92 contra item
   existente da mesma semana.
8. `status = draft` → fila de revisão.

**Fila de jobs:** tabela `IngestJob` no próprio Postgres com
`SELECT ... FOR UPDATE SKIP LOCKED`, consumida por um processo worker separado. Isso evita
adicionar Redis + Celery a um projeto solo. Se um dia precisar de agendamento e retry mais
sofisticado, migre para `arq` — a interface do serviço não muda.

---

## 5. Correção ao vivo

```
POST /api/study/answer  { item_id, response_text, session_id }
```

1. Carrega `Item` + `rubric` + o texto dos `chunk_ids`.
2. Uma chamada de LLM com saída estruturada:
   ```json
   { "points": [{"point_id":"p1","covered":true,"evidence":"trecho da resposta do aluno"}],
     "misconceptions": ["confundiu tuning curve com receptive field"],
     "feedback_md": "2 frases, corretivas, citando a fonte" }
   ```
3. **O score é calculado em Python**, não pelo modelo: `Σ(weight de pontos cobertos) / Σ(weight)`.
   Nota gerada por LLM oscila entre execuções; agregação determinística não.
4. Resposta inclui `reference_answer`, os pontos verdes/vermelhos, e o **locator + trecho**
   da fonte, para você pular direto ao slide.
5. `ReviewState` atualizado por FSRS a partir do score (>0.85 = good, 0.6–0.85 = hard,
   <0.6 = again).
6. **Cache** em `hash(item_id + resposta normalizada)` — respostas repetidas não gastam token.

Para `mcq` e `cloze`, a correção é determinística: zero chamada de LLM. Só
`free_recall`, `term_def`, `compare` e `application` passam pelo grader.

---

## 6. Layout do repositório

```
neuroai-studykit/
├─ apps/
│  ├─ api/                    # FastAPI
│  │  ├─ routers/             auth sources ingest items decks study progress
│  │  ├─ services/            ingestion grading scheduling budget
│  │  ├─ repos/               SQLAlchemy 2.0 (async)
│  │  ├─ core/                config.py (pydantic-settings) security.py llm.py
│  │  ├─ models/  schemas/    ORM  |  Pydantic I/O
│  │  └─ worker.py            consumidor da fila
│  └─ web/                    React + Vite + TS + TanStack Query + Tailwind
│     └─ src/routes/          landing study library review progress
├─ packages/
│  └─ ingest/                 parsers, chunker, generator, prompts/, cli.py
│                             (importado pela API *e* pelo CLI — uma implementação só)
├─ content/                   material do curso  ← GITIGNORED (ver §8)
│  └─ demo/                   deck público, escrito por você  ← commitado
├─ alembic/                   migrations
├─ docker-compose.yml         postgres+pgvector, api, worker, web
└─ .env.example
```

Regra que vale ouro: **`packages/ingest` não importa nada de `apps/api`.** Ele recebe
bytes e devolve objetos Pydantic. É isso que permite rodar a ingestão pelo CLI sem subir
servidor, e testá-la sem banco.

### Contratos de API (esboço)

```
POST   /api/auth/callback              troca código OIDC por sessão
GET    /api/sources                    lista + status de ingestão
POST   /api/sources                    upload multipart → cria IngestJob
GET    /api/items?status=draft&week=3  fila de revisão (owner)
PATCH  /api/items/{id}                 aprovar / editar / aposentar
POST   /api/study/session              {deck_id|topics|due_only} → fila de itens
POST   /api/study/answer               correção (acima)
GET    /api/progress                   mastery por tópico, due counts, curva de acerto
GET    /api/checkin/draft?week=3       rascunho do check-in semanal a partir das stats
```

---

## 7. Auth, segredos e custo

Três coisas distintas que a palavra "público" confunde, decididas separadamente:

| | v1 | depois |
|---|---|---|
| **Código** (GitHub) | público — é o portfólio | — |
| **Site** (a URL) | privado, só você entra | opcional: convite a colegas, ou demo anônimo |
| **Conteúdo** (decks) | tudo `private` | `shared` por convite / `public_demo` |

- **`ANTHROPIC_API_KEY` só existe no backend.** `core/config.py` com `pydantic-settings`,
  `.env` gitignorado, `.env.example` commitado. O bundle do React nunca toca em chave —
  nem em variável `VITE_*`, que **vai para o cliente** e é a pegadinha clássica. Isso vale
  independentemente do site ser privado: o repo é público e o histórico do git é para
  sempre.
- **Auth:** provedor OIDC hospedado (Auth0 / Clerk / Supabase Auth) com magic link,
  emitindo JWT; o FastAPI só *verifica*, na dependency `get_current_user`. Um usuário só,
  mas auth de verdade — você demonstra a competência sem virar responsável por armazenar
  senha, e sem inventar criptografia.
- **Papéis no enum desde já:** `owner` (ingere, aprova, vê tudo) · `student` (estuda decks
  a que foi convidado) · `demo` (anônimo, só `public_demo`, sem escrita). Na v1 só existe
  `owner`; os outros dois são a costura.
- **Allowlist de e-mail** em vez de porta aberta: `ALLOWED_EMAILS` no env. Quem não está na
  lista não cria conta, mesmo tendo a URL. É uma linha de código e é a coisa que
  efetivamente mantém o site privado.
- **Superfície de abuso fechada, ainda que privada:** nenhum endpoint aceita prompt livre.
  O grader recebe `item_id` + texto do aluno, e o texto entra na chamada **como dado
  delimitado**, nunca concatenado no papel de instrução. Vale manter assim desde o começo
  porque é o que torna abrir o site depois uma decisão de configuração, não de reescrita.
- **Orçamento:** teto diário de tokens por usuário em `services/budget.py` desde a v1 — o
  risco real com site privado não é abuso, é um bug de loop na ingestão consumindo a conta
  numa madrugada. Rate limit por IP entra junto com o acesso público, se ele vier.
- CORS restrito à origem do front. Uploads: só `.pdf/.pptx/.vtt/.srt/.md`, limite de
  tamanho, nome sanitizado, armazenado por UUID (nunca pelo nome original).

**O portfólio não depende do site estar aberto.** O que um recrutador avalia é o repo: o
`README` com um GIF do loop de estudo rodando, o desenho do pipeline de ingestão, a
validação de citação literal, os testes com corpus sintético, as migrations. Um link
"vídeo de 2 min" vale mais que uma URL pública — e não te custa auth com papéis, rate
limit e sanitização de abuso.

---

## 8. Direito autoral — decisão de arquitetura, não detalhe

O repo é público (portfólio). Os PDFs e slides do GENED 1201 **não são seus para
redistribuir**. Então:

- `content/` fica no `.gitignore`; o storage de produção é privado.
- Questões geradas a partir do material são trabalho derivado — mantenha-as no banco
  privado, não em fixtures do repo. Os testes usam um **corpus sintético** em
  `tests/fixtures/`: dois ou três "textos de aula" que você mesmo escreve, sobre conceitos
  básicos, suficientes para exercitar parser, chunker, gerador e grader de ponta a ponta.
- Esse mesmo corpus sintético é o que vira o deck de demonstração, se um dia você abrir o
  site. Ou seja: escrevê-lo agora não é trabalho jogado fora — é o fixture de teste e a
  vitrine futura na mesma pasta.
- O GIF do `README` usa o corpus sintético, não a Semana 3 do GENED.

Isso não é só conformidade: um recrutador que abre o repo e vê `content/` vazio com um
`README` explicando o porquê lê isso como bom julgamento.

---

## 9. Deploy

Implantado no M13 — o que segue é o que de fato está no ar, não o desenho original desta
seção (que previa um worker separado e storage em R2; nenhum dos dois chegou a existir).

- **Postgres (pgvector):** Neon. Free tier, sem prazo de expiração, pgvector incluso sem
  custo extra (confirmado em `neon.com/docs` — diferente do Postgres free do Render/Railway,
  que expira). O compute dorme após inatividade e acorda sozinho na próxima conexão.
- **API:** Render, ambiente nativo Python (sem Dockerfile), tier grátis de web service.
  Um serviço só — não existe worker; toda geração/correção roda inline na requisição.
- **Web:** Vercel, tier grátis, autodetecta Vite.
- **Arquivos:** ficam em bytea no Postgres (não em R2/S3) — decisão de antes deste marco,
  simples o bastante pro volume de um app pessoal.
- `docker-compose.yml` reproduz o banco local para desenvolvimento (`make up`); API e web
  rodam direto via `make api`/`make web`, sem container, tanto local quanto em produção.

---

## 10. Roadmap por fases

**Fase 1 — o loop fechado (MVP).**
Ingestão só por `content/` + CLI. Parser de PDF. Chunking. Geração de `free_recall` e
`term_def`. Tabelas `Source/Chunk/Item/Attempt` (já com `owner_id`/`visibility`). Study
runner com correção por rubrica. Um usuário, sem auth ainda — `owner_id` fixo via env.
*Critério de pronto: você estuda a Semana 1 de verdade no seu app.*

**Fase 2 — confiança.** UI de revisão draft→approved. Dedup. Validação de quote literal.
Tipos `cloze` e `mcq` com correção determinística. Corpus sintético em
`tests/fixtures/` + testes do pipeline.

**Fase 3 — o sistema de estudo.** FSRS e fila de revisão por vencimento. Página de
progresso por tópico. Gerador de rascunho do check-in semanal.

**Fase 4 — fechar a porta.** Auth OIDC com magic link + allowlist de e-mail, teto de
tokens, deploy. Curto: é a fase que torna o site seguro de deixar no ar, não a que o abre.

**Fase 5 — portfólio.** `README` com GIF do loop, diagrama, seção de decisões de design,
CI rodando os testes. **É esta a fase que faz o trabalho de portfólio**, não um site aberto.

**Fase 6 — extras, por vontade.** Upload pela UI, transcrições com Whisper, modo exame
cronometrado, busca semântica. E, se der vontade: convite a colegas (`visibility=shared`)
ou demo anônimo (`public_demo` + rate limit por IP) — as costuras já estão no lugar desde
a Fase 1.

Construa nessa ordem. A Fase 1 já satisfaz o requisito do curso; a Fase 5 é o portfólio.

---

## 11. Riscos e como cada um é mitigado

| Risco | Mitigação já embutida no design |
|---|---|
| Questão alucinada vira estudo errado | `support_quote` verificada literalmente + aprovação manual |
| Nota do grader instável entre execuções | rubrica fixa + agregação determinística em Python |
| Conta de API explodindo (bug de loop na ingestão) | teto diário de tokens, cache, endpoint de escopo fechado |
| Chave vazando no bundle ou no histórico do git | chave só no backend; `VITE_*` nunca recebe segredo; `.env` gitignorado desde o primeiro commit |
| Abrir o site depois exigir reescrita | `owner_id`/`visibility`/`role` e filtro por usuário desde a v1 |
| Questões redundantes entre aulas | dedup por embedding do enunciado |
| Estudo virar releitura passiva | resposta digitada obrigatória antes de revelar o gabarito |
| Material do curso num repo público | `content/` gitignorado, demo próprio commitado |
```

# Plano de implementação

Este documento é a **ordem de trabalho**. O `ARCHITECTURE.md` diz *o quê* e *por quê*;
este diz *em que ordem* e *como saber que terminou*.

## Como usar

Três arquivos, três papéis distintos — é isso que faz o Claude Code funcionar bem aqui:

| Arquivo | Papel | Quando é lido |
|---|---|---|
| `CLAUDE.md` | regras que valem sempre (invariantes, comandos, convenções) | carregado automaticamente em toda sessão |
| `docs/ARCHITECTURE.md` | contexto: modelo de dados, decisões, riscos | quando você aponta para ele |
| `docs/IMPLEMENTATION_PLAN.md` | a fila de marcos com critério de aceite | um marco por sessão |

**Um marco por sessão de Claude Code.** O ciclo:

1. `/clear` para começar com contexto limpo.
2. Cole o prompt do marco (estão prontos abaixo).
3. `Shift+Tab` até **plan mode** — ele explora e propõe sem editar nada. Leia o plano.
   Se estiver errado, corrija em palavras antes de aprovar. Corrigir um plano custa um
   minuto; corrigir 15 arquivos custa uma tarde.
4. Aprove, deixe implementar.
5. **Exija a verificação rodada de verdade** — o comando do critério de aceite, com a
   saída real na tela. "Implementei conforme especificado" não é evidência.
6. `git commit`. Um commit por marco, no mínimo.
7. `/clear` e próximo marco.

Por que não colar tudo de uma vez: um agente construindo 6 marcos seguidos produz muito
código que você não leu, e o primeiro erro de desenho se propaga para tudo que vem
depois. O valor deste app é a *qualidade das questões* — uma propriedade que só os seus
olhos verificam. Marcos pequenos mantêm você no circuito.

> Antes do M0, faça o passo 0 abaixo. Ele existe para que nenhum segredo entre no
> histórico do git, e histórico de repo público não se limpa de verdade.

---

## Passo 0 — Bootstrap (você, à mão, ~10 min)

```bash
# 1. crie o repo vazio no GitHub (pode ser público), depois:
git clone git@github.com:SEU_USER/neuroai-studykit.git
cd neuroai-studykit

# 2. PRIMEIRO commit = só higiene. Nada de código ainda.
#    (descompacte o starter kit aqui: CLAUDE.md, .gitignore, .env.example,
#     .claude/settings.json, docs/)
git add .gitignore .env.example CLAUDE.md .claude docs
git commit -m "chore: repo hygiene, architecture and implementation plan"
git push

# 3. sua chave de verdade, NUNCA commitada
cp .env.example .env
# edite .env e coloque ANTHROPIC_API_KEY=...

# 4. confirme que o git não vê o .env
git status --porcelain   # não deve listar .env
```

Só depois disso abra o `claude` na pasta.

Opcional, na primeira sessão: rode `/init`. Como já existe um `CLAUDE.md`, ele vai
*sugerir melhorias* em vez de sobrescrever — e as sugestões dele sobre comandos e
estrutura são úteis. Aceite só o que fizer sentido.

---

# FASE 1 — O loop fechado

Critério da fase: **você estuda a Semana 1 de verdade, no seu app.** Nada de auth, nada
de agendamento, nada de UI bonita.

---

## M0 — Esqueleto e ferramental

**Objetivo:** repo que sobe, testa e linta. Zero lógica de domínio.

**Entregas:** `pyproject.toml` (uv), `apps/api/main.py` com `GET /health`,
`packages/ingest/__init__.py`, `docker-compose.yml` (postgres 16 + pgvector),
`alembic/` inicializado, `Makefile`, `apps/web` criado com Vite+TS+Tailwind,
`tests/test_health.py`.

**Aceite:**
```bash
make up && make test        # verde, com pelo menos 1 teste de cada lado
curl localhost:8000/health  # {"status":"ok","db":"ok"}
make lint                   # limpo
```

**Prompt:**
```
Leia CLAUDE.md e docs/IMPLEMENTATION_PLAN.md. Implemente apenas o marco M0.

Monte o esqueleto do monorepo: uv/pyproject para o backend, FastAPI com GET /health que
também checa a conexão com o Postgres, docker-compose com postgres 16 + extensão pgvector,
Alembic inicializado (sem migrations de domínio ainda), Vite+React+TS+Tailwind em
apps/web, e um Makefile com os alvos listados no CLAUDE.md.

Nenhum modelo de domínio, nenhuma tabela, nenhuma chamada de LLM neste marco.

Quando terminar, rode `make up`, `make test`, `curl localhost:8000/health` e `make lint`
e me mostre a saída real de cada um.
```

---

## M1 — Parsers e chunker (puro, sem banco)

**Objetivo:** de arquivo para lista de chunks com locator correto. A peça mais fácil de
testar e a que todo o resto depende.

**Entregas:** em `packages/ingest/`: `parsers/pdf.py` (PyMuPDF), `parsers/pptx.py`
(python-pptx, texto + speaker notes), `parsers/transcript.py` (VTT/SRT),
`chunker.py`, `models.py` (`ParsedBlock`, `Chunk` como Pydantic), `cli.py` com
`ingest parse <arquivo>` imprimindo chunks + locators.

**Regras:** alvo de 500–900 tokens por chunk, overlap ~15%, quebra preferencial em
heading/slide, nunca no meio de uma definição. Slide curto funde com o vizinho
preservando os dois locators.

**Aceite:** corpus sintético em `tests/fixtures/` (um PDF de 3 páginas, um .pptx de 5
slides, um .vtt — gerados por script, commitados). Testes provam que: número de chunks é
plausível, todo chunk tem locator não-vazio e correto, nenhum chunk excede o teto de
tokens, o overlap existe. `python -m ingest.cli parse tests/fixtures/synthetic.pdf`
imprime chunks legíveis com `page`.

**Prompt:**
```
Leia CLAUDE.md. Implemente apenas o marco M1 do docs/IMPLEMENTATION_PLAN.md.

Atenção ao invariante 4: packages/ingest não importa nada de apps/api. Sem banco neste
marco — parser e chunker são funções puras sobre bytes/caminho, devolvendo Pydantic.

Inclua um script que gera o corpus sintético de fixtures (escreva você o conteúdo: textos
curtos sobre conceitos básicos de neurociência e ML, nossos, não de material de curso) e
commite os arquivos gerados.

Verifique rodando pytest e o CLI no fixture, e me mostre a saída.
```

---

## M2 — Schema, migrations e `sync`

**Objetivo:** persistir fontes e chunks, com dedup por hash.

**Entregas:** modelos ORM `User`, `Source`, `Chunk`, `IngestJob` (e enums); migration
Alembic; `ingest.cli sync <pasta>` que percorre arquivos, calcula sha256, pula o que já
existe, grava chunks; embeddings podem ficar `NULL` neste marco.

**Aceite:**
```bash
make upgrade
python -m ingest.cli sync tests/fixtures/    # grava N fontes, M chunks
python -m ingest.cli sync tests/fixtures/    # roda de novo: "0 novas fontes"
psql -c "select count(*) from chunk"         # não dobrou
```

**Prompt:**
```
Leia CLAUDE.md. Implemente apenas o marco M2.

Modelos conforme docs/ARCHITECTURE.md §3 — incluindo owner_id e os campos de
multiusuário (invariante 8), mesmo sem auth ainda; use um owner_id fixo vindo de env.
Migration Alembic no mesmo commit. Locators em jsonb no formato fixo do CLAUDE.md.

Prove a idempotência rodando o sync duas vezes e mostrando as contagens.
```

---

## M3 — Gerador de questões e validadores

**Objetivo:** o coração da qualidade. De chunk para `Item` com rubrica ancorada.

**Entregas:** `core/llm.py` com o protocolo `LLMClient` + implementação Anthropic +
`FakeLLM`; `packages/ingest/generator.py`; `packages/ingest/prompts/generate_v1.md`;
`packages/ingest/validators.py`; modelo `Item` + migration; `ingest.cli generate --week N`.

**Validadores obrigatórios:**
- JSON parseia e satisfaz o modelo Pydantic (1 retentativa, depois falha)
- todo `support_quote` aparece **literalmente** no texto do chunk
- rubrica tem 2 a 5 pontos, pesos somando > 0
- rejeita questão auto-respondível (o termo perguntado aparece no enunciado)
- `topics[]` só aceita valores de `topics.yaml`

**Aceite:** testes com `FakeLLM` cobrindo: saída boa → itens salvos como `draft`; quote
inventada → rejeitado; JSON malformado → uma retentativa e então falha registrada;
rubrica de 1 ponto → rejeitada. E uma execução real contra o fixture, com você lendo
5 questões geradas e julgando se são boas.

**Prompt:**
```
Leia CLAUDE.md. Implemente apenas o marco M3.

Invariante 1 e 5 são o ponto deste marco: rubrica com support_quote verificada por
comparação literal de string, e todo acesso a LLM atrás do protocolo LLMClient com FakeLLM
nos testes. Prompt como arquivo versionado, não string inline.

Antes de escrever o generator, me mostre o prompt que você pretende usar e o modelo
Pydantic da saída esperada — quero revisar os dois antes da implementação.

Cubra com testes os quatro casos de falha listados no marco.
```

> **Este é o marco que decide se o app presta.** Não o apresse. Espere revisar o prompt
> pessoalmente, e depois de gerar, leia questões de verdade. Se estiverem genéricas
> ("O que é aprendizado de máquina?"), o problema é o prompt e o chunking, não o código.

---

## M4 — API de estudo e corretor

**Objetivo:** sessão de estudo e correção por rubrica, via HTTP.

**Entregas:** `Attempt` + migration; `services/grading.py`; routers `items`, `study`;
`POST /api/study/session`, `POST /api/study/answer`, `PATCH /api/items/{id}`;
cache de correção por `hash(item_id + resposta normalizada)`.

**Aceite:** testes de integração com `FakeLLM` provando que o score é a soma ponderada
determinística (mesma entrada → mesmo score, sempre), que a resposta inclui o locator e o
trecho da fonte, e que resposta repetida vem do cache sem nova chamada. Mais uma
requisição real via `curl` mostrando feedback coerente.

**Prompt:**
```
Leia CLAUDE.md. Implemente apenas o marco M4.

Invariante 2: o LLM devolve apenas covered:true|false por ponto da rubrica; o score é
calculado em Python. Invariante 7: o endpoint recebe item_id + texto, nunca um prompt, e o
texto do aluno entra na chamada como dado delimitado.

Teste que a mesma entrada produz exatamente o mesmo score em execuções repetidas.
```

---

## M5 — Study runner (frontend)

**Objetivo:** a tela onde você estuda. Feia é aceitável; funcional não é negociável.

**Entregas:** rota `/study`: pega a fila, mostra o enunciado, textarea, submete, exibe
pontos da rubrica em verde/vermelho, o gabarito, o trecho da fonte com locator, e avança.
Atalhos de teclado (Ctrl+Enter envia, Espaço avança).

**Regra pedagógica:** o gabarito **não aparece** antes de a resposta ser enviada. Sem
botão "revelar". A geração ativa é o mecanismo todo; um atalho para espiar destrói o
valor do app.

**Aceite:** você estuda 10 questões da Semana 1 do começo ao fim, sem tocar no terminal.
Grave o GIF aqui — serve para o README na Fase 5.

**Prompt:**
```
Leia CLAUDE.md. Implemente apenas o marco M5.

React + TanStack Query + Tailwind, apenas a rota /study. Sem biblioteca de componentes
nova. O gabarito e a rubrica só são buscados/exibidos depois do submit — nunca enviados ao
cliente junto com o enunciado (senão dá para ler no devtools e o app perde o sentido).

Ao terminar, me diga o que testar manualmente, passo a passo.
```

---

# FASES SEGUINTES (esboço)

Detalhar quando chegar. Cada marco ganha prompt e critério de aceite na hora — escrever
agora é adivinhação, porque o que você aprender na Fase 1 muda o resto.

**Fase 2 — confiança**
- **M6** UI de revisão `draft → approved/edited/retired`, com o chunk-fonte ao lado.
  *Aceite: você aprova 30 questões numa sessão sem abrir o banco.*
- **M7** Dedup por embedding do enunciado (pgvector, cosseno > 0.92) + tipos `cloze` e
  `mcq` com correção determinística (zero LLM).
- **M8** CI no GitHub Actions rodando `make test` e `make lint` em cada push.

**Fase 3 — o sistema de estudo**
- **M9** FSRS: `ReviewState`, fila por vencimento, mapeamento score → grade.
- **M10** Página de progresso: acerto por tópico, itens vencidos, pontos fracos.
- **M11** `GET /api/checkin/draft?week=N` — rascunho do check-in semanal a partir das suas
  estatísticas reais. *Serve diretamente o requisito do curso.*

**Fase 4 — fechar a porta**
- **M12** Auth OIDC com magic link + `ALLOWED_EMAILS` + teto diário de tokens.
- **M13** Deploy (Neon + Render + Vercel), `.env` de produção, backup do Postgres.

**Fase 5 — portfólio**
- **M14** README com GIF do loop, diagrama, seção de decisões de design e trade-offs,
  badge do CI. **É esta fase que faz o trabalho de portfólio**, não um site aberto.

**Fase 6 — por vontade**
Upload pela UI · transcrição com Whisper · modo exame cronometrado · busca semântica ·
convite a colegas (`visibility=shared`) · demo anônimo (`public_demo` + rate limit por IP).

---

## Higiene de sessão

- `/clear` entre marcos. Contexto acumulado de um marco terminado só atrapalha o próximo.
- `/compact` no meio de um marco longo, se começar a ficar lento.
- `/review` no diff antes de commitar um marco grande.
- Se ele propuser instalar um serviço novo (Redis, Celery, uma lib de auth), isso viola o
  "pergunte antes" do `CLAUDE.md` — recuse e pergunte por quê antes de aceitar.
- Quando algo der errado duas vezes seguidas do mesmo jeito, pare. Não peça "tenta de
  novo": volte ao plan mode e questione o desenho.

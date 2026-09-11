# NeuroAI Study Kit

A personal **practice-testing** app for Harvard's GENED 1201 (*Foundations of NeuroAI*).
It ingests lecture material — PDFs, slide decks, transcripts — generates recall
questions grounded in that source text, and grades free-text answers against a rubric
derived from the same text.

The core idea: **every question carries a pointer back to the exact passage that
justifies it.** No citation, no question. Grading doesn't compare your answer to a
model's opinion — it compares it to a rubric anchored in the source, and hands back the
passage (slide 12, page 7, 14:32–16:05) alongside the feedback.

## Status

🚧 Early build. **M0 (skeleton & tooling)** is done: the repo boots, tests, and lints,
with zero domain logic yet. See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
for the milestone roadmap and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the
full design — data model, ingestion pipeline, grading flow, and the reasoning behind
each decision.

## Stack

| | |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic — managed with [`uv`](https://docs.astral.sh/uv/) |
| Database | Postgres 16 + [pgvector](https://github.com/pgvector/pgvector) |
| Frontend | React + Vite + TypeScript, TanStack Query, Tailwind |
| Tests | pytest (+ pytest-asyncio) · vitest |
| Lint/format | ruff · eslint + prettier |

## Getting started

Requires [`uv`](https://docs.astral.sh/uv/), Node.js, and Docker.

```bash
cp .env.example .env        # then fill in your own secrets
make up                     # postgres + pgvector, via docker compose
make test                   # backend + frontend test suites
make api                    # FastAPI with reload, on :8000
make web                    # Vite dev server
```

```bash
curl localhost:8000/health
# {"status":"ok","db":"ok"}
```

Other targets: `make lint` (ruff + eslint/prettier), `make migrate m="..."` /
`make upgrade` (Alembic).

## Repository layout

```
apps/
  api/          FastAPI app — routers, services, models, core config
  web/          React + Vite + TS frontend
packages/
  ingest/       Parsers, chunker, question generator — pure, no DB, no server
                (imported by apps/api and by a standalone CLI; never the reverse)
alembic/        Migrations
docker-compose.yml
docs/
  ARCHITECTURE.md         data model, pipeline, design decisions, risks
  IMPLEMENTATION_PLAN.md  milestone-by-milestone build order and acceptance criteria
```

`content/` (lecture material) is gitignored on purpose — it isn't mine to redistribute.
Tests and the demo deck run on a synthetic corpus written from scratch, committed under
`tests/fixtures/`.

## Why this exists

Built to satisfy GENED 1201's weekly check-in requirement the honest way: by actually
recalling the material, not rereading slides. The design choices — literal-quote
validation against hallucinated questions, deterministic (non-LLM) scoring, a
multi-user schema from day one even with a single user — are documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#11-riscos-e-como-cada-um-é-mitigado).

## License

MIT — see [`LICENSE`](LICENSE).

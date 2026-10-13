# AnswerForge — Stages 1–3

AnswerForge is an enterprise questionnaire workflow built around reusable
company knowledge and evidence-aware AI assistance. This repository implements
Stage 1 knowledge management, Stage 2 human questionnaire workflow, and the
Stage 3 grounded-generation orchestration baseline.

## Roadmap

1. **Stage 1 — Knowledge Base:** workspaces, document ingestion,
   parser output/chunk inspection, pgvector retrieval, and lifecycle-safe
   removal.
2. **Stage 2 — Questionnaire Workflow:** CSV/XLSX mapping/import,
   immutable answer versions, manual evidence, review decisions, and CSV export.
3. **Stage 3 — Agent Orchestration (current baseline):** bounded retrieval,
   grounded drafts, verification, AgentRun tracing, and Redis/RQ workers.

## Architecture

```text
                  Next.js
                     |
                     v
                  FastAPI
                /    |    \
               v     v     v
        PostgreSQL  Storage  Redis/RQ Worker
         + pgvector             |
                |               v
                v          LLM Provider
          Embedding Provider
```

```text
Upload → Parse → Chunk → Embed → Store → Search
```

The frontend is in `frontend/`; the FastAPI application, Alembic migration, and
tests are in `backend/`. PostgreSQL uses `pgvector/pgvector:pg16` locally.

## Run locally

1. Start PostgreSQL and Redis: `docker compose up -d db redis`. If port 5432 is already used,
   start it on another host port with `POSTGRES_PORT=5433 docker compose up -d db`
   and set `DATABASE_URL` in `backend/.env` to port 5433. If Redis port 6379
   is already in use, either use that local Redis through `REDIS_URL`, or run
   `REDIS_PORT=6380 docker compose up -d redis` and set `REDIS_URL=redis://localhost:6380/0`.
2. Create `backend/.env` from `backend/.env.example`, add a Gemini API key as
   `GEMINI_API_KEY` (the existing generic `EMBEDDING_API_KEY` alias also works),
   and install API dependencies: `cd backend && pip install -e '.[dev]'`.
3. Run the database migration: `cd backend && alembic upgrade head`.
4. Start the API: `cd backend && uvicorn app.main:app --reload`.
5. In another terminal, start the UI: `cd frontend && npm run dev`.
6. Start an agent worker when using generation. On macOS use the non-forking
   worker required by the Gemini SDK: `cd backend && rq worker --worker-class
   rq.worker.SimpleWorker answerforge-agent`. Linux deployments can use the
   default RQ worker process.

The frontend expects `http://localhost:8000` by default. Set
`NEXT_PUBLIC_API_URL` when it differs. `EMBEDDING_DIMENSIONS` must match the
vector column created by the migration (1536 for the Gemini output dimension).

## Run with Docker

For a production-like local stack with Caddy, FastAPI, the RQ worker,
PostgreSQL/pgvector, Redis, and Next.js, see [docs/deployment.md](docs/deployment.md).
The stack is reached at <http://localhost>; the proxied health endpoint is
<http://localhost/api/health>.

## API

- `GET /health`
- `POST|GET /workspaces`, `GET /workspaces/{id}`
- `POST|GET /workspaces/{id}/documents` (list uses `active`, `removed`, or
  `all` visibility)
- `GET /documents/{id}`, `/content`, `/chunks`, and `/original`
- `PATCH /documents/{id}` for notes
- `POST /documents/{id}/remove`
- `POST /workspaces/{id}/search`
- `POST /workspaces/{id}/knowledge/ask` (ephemeral grounded answer; optional active `document_id` scope)
- `POST /workspaces/{id}/questionnaires/preview`, then `POST /workspaces/{id}/questionnaires`
- `GET /workspaces/{id}/questionnaires`, `GET /questionnaires/{id}`, and `/questions`
- `DELETE /questionnaires/{id}` permanently removes a questionnaire, its questions,
  answer history, and retained questionnaire source file.
- `POST /questions/{id}/answers`, `/approve`, `/reject`, and `/not-applicable`
- `GET /questions/{id}/answers`, `GET /answer-versions/{id}`, and `/citations`
- `POST /answer-versions/{id}/citations`, `DELETE /citations/{id}`
- `GET /questionnaires/{id}/export?format=csv`

The questionnaire export contains the configured question and answer columns,
and includes only questions currently marked **APPROVED** with an answer.
- `POST /questionnaires/{id}/generate`, `POST /questions/{id}/generate`, and `/regenerate`
- `GET /agent-runs/{id}` and `GET /questions/{id}/agent-runs`

## Stage 3 design

Generation is an automation layer over the same immutable AnswerVersion and
Citation model used by human review. An AgentRun performs a bounded research,
draft, and verification sequence outside database transactions; one short
transaction then persists an AGENT version, citation snapshots, current pointer,
question state, and run outcome together. Missing evidence is a successful,
deterministic abstention that still goes to human review. Redis/RQ only enqueue
and invoke work—the core orchestrator remains directly testable without them.

## Stage 2 design

Answers are immutable `AnswerVersion` rows; the `Question` owns its review
state. Evidence coverage is a separate field, and every `Citation` snapshots
quoted text and provenance. This preserves historical evidence even after a
knowledge document is removed and its chunks are deleted. Export is an action,
not a questionnaire lifecycle state.

## Removal behaviour

**Remove from Knowledge** intentionally preserves the `Document` record and
the original stored source file. It sets `is_deleted = true` and `deleted_at`,
then hard-deletes the document's chunks and embeddings. The source immediately
stops appearing in retrieval; repeat removal requests are safe.

This split is intentional: a later `Citation` can retain a snapshot of its
quoted text/page/section and continue naming a removed source even after its
chunk is gone. A future, explicit permanent-source deletion can apply a
separate retention policy.

## Important design decisions

- **Soft document lifecycle, hard chunk deletion:** preserves historical source
  identity while eliminating active retrievable evidence.
- **Snapshot evidence later:** citations should store quoted text because chunk
  IDs may become null after removal; keeping all chunks forever is simpler but
  conflicts with removing active knowledge.
- **Local `FileStorage`:** fastest local setup and a clean `save/exists/get_path`
  contract. It will be replaced by an S3-compatible implementation for shared,
  durable deployments.
- **PostgreSQL + pgvector:** relational lifecycle data and vector queries share
  a transaction boundary. At much larger scale, indexing/tuning or a separate
  retrieval service may be warranted.
- **Paragraph-aware character chunks:** a defensible, inspectable baseline with
  overlap and page/offset metadata. Semantic chunking is deferred until
  evaluation proves it useful.
- **Embedding abstraction:** ingestion and search depend on a small interface;
  the current Gemini Embedding 2 implementation uses 1536-dimensional output
  and retrieval-specific query/document formatting. Changing providers or
  dimensions requires re-embedding/migration work.
- **Workspace-scoped retrieval:** the SQL join filters both workspace and
  `is_deleted = false` before top-k ranking, avoiding cross-company evidence.
- **Synchronous ingestion:** easy to observe and test now; the service can move
  unchanged behind a future worker when document volume makes HTTP processing
  too slow.

## Limits today

- Local filesystem storage
- Synchronous ingestion
- Dense semantic retrieval only
- PDF/TXT/MD only; PDF OCR is not enabled
- No authentication or multi-user collaboration
- No public-web browsing, autonomous approval, source-authority policy, or
  unbounded agent loops

## Tests

Run `cd backend && pytest`. Tests cover parsing failure modes, chunk ordering
and overlap, the critical removal lifecycle, questionnaire import, and the
independent retrieval/end-to-end evaluation metrics. Add a PostgreSQL test
database for API-level upload/retrieval and queued-worker integration tests
when running this as CI.

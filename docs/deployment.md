# Docker Compose deployment

AnswerForge runs as six Compose services on one bridge network. Caddy is the
only public ingress; PostgreSQL, Redis, FastAPI, and Next.js are internal.

```text
browser -> caddy:80 -> /api/* -> api:8000 -> db:5432 / redis:6379
                    -> /*    -> frontend:3000
```

The `api` and `worker` services build the same `backend/Dockerfile` image and
share the `upload_data` volume mounted at `/app/storage`. This is required so a
file uploaded by the API is readable by any processing job. PostgreSQL uses
`pgvector/pgvector:pg16`; Redis uses AOF persistence. Named volumes preserve
state across restarts and normal `down`/`up` cycles.

## First run

```bash
cp .env.example .env
# Add GEMINI_API_KEY (or EMBEDDING_API_KEY) to .env for embeddings/generation.
docker compose config
docker compose build
docker compose up -d db redis
docker compose ps
docker compose run --rm api alembic upgrade head
docker compose up -d
docker compose ps
```

The application is available at <http://localhost>. The proxied health check is
<http://localhost/api/health>.

Migrations are deliberately explicit and are not run automatically by API or
worker containers:

```bash
docker compose run --rm api alembic upgrade head
```

## Environment variables

The root `.env.example` documents the complete stack. The important container
values are:

| Variable | Container value | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...@db:5432/...` | SQLAlchemy/pgvector connection |
| `REDIS_URL` | `redis://redis:6379/0` | RQ queue connection |
| `STORAGE_PATH` | `/app/storage` | Shared API/worker upload volume |
| `NEXT_PUBLIC_API_URL` | `/api` | Browser calls through Caddy |
| `INTERNAL_API_BASE_URL` | `http://api:8000` | Reserved for server-side Next routes |
| `CORS_ORIGINS` | localhost origins | Direct-development browser support |

Never put provider credentials in a Dockerfile or Compose file. `.env` is
ignored by the backend image and should remain local.

## Logs and operations

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=100 frontend
docker compose logs --tail=100 caddy
docker compose restart
docker compose down
docker compose up -d
```

Do not use `docker compose down -v` unless intentionally deleting all named
database, Redis, upload, or Caddy data.

## Validation

```bash
curl http://localhost/api/health
curl -I http://localhost
docker compose ps
backend/.venv/bin/python -m pytest -q
```

The production image does not include test dependencies. Run the repository
virtual-environment suite (`backend/.venv/bin/python -m pytest -q`) or build a
temporary development image if container-only test execution is required.

An end-to-end upload can only reach `READY` when a valid Gemini embedding key
with available quota is configured. Without it, API health and database
migrations remain testable but embedding/generation must be treated as
unverified; never fake a provider response.

## Small VPS outline

Install Docker Engine and Compose on a single VM, copy the repository and a
permissioned `.env`, then run the first-run commands above. Point DNS at the
VM, replace `http://localhost` in `caddy/Caddyfile` with the real domain, and
remove any external port other than Caddy's 80/443 bindings when enabling TLS.
Use encrypted off-host PostgreSQL backups (including the pgvector database),
retain the `upload_data` volume or back it up separately, and protect the
provider key and `.env` with VM secret/file permissions.

## Troubleshooting

- `api` unhealthy: inspect API logs and verify the `db` healthcheck, URL, and
  migration status.
- `worker` idle: confirm Redis is healthy and that its queue is exactly
  `answerforge-agent`.
- `/api/health` fails through Caddy: check Caddy logs and remember that
  `handle_path` removes `/api` because FastAPI routes start at `/health`, not
  `/api/health`.
- Upload processing fails: inspect document metadata and confirm both API and
  worker use `/app/storage` on `upload_data`; then verify Gemini credentials.
- Port 80 is busy: stop the conflicting local service or temporarily change
  only the host-side Caddy mapping for local testing.

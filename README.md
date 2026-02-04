# Tickets API

FastAPI service using a `src/` layout (`src/app/...`), Postgres, Redis, and async SQLAlchemy.

## Running (Docker)

```bash
docker compose up -d --build
docker compose logs -f api
```

## Migrations (Alembic)

Alembic is configured to read `DATABASE_URL` via `pydantic-settings` (see `app.core.settings`).
`alembic/env.py` runs migrations using an async engine.

### Local (virtualenv)

```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

### Docker

```bash
docker compose exec api alembic revision --autogenerate -m "init"
docker compose exec api alembic upgrade head
```

## Smoke test

`GET /db-ping` executes `SELECT 1` to confirm DB connectivity.

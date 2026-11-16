# OpsAnalyst Agent

A business data agent that answers plain-English questions by writing SQL, running it safely
and showing its work, with a reliability layer that traces, blocks and diagnoses failures.

> 🚧 In progress. See [DESIGN.md](DESIGN.md) for the architecture and phase plan.

## Setup (local)

Needs: [uv](https://docs.astral.sh/uv/), Docker Desktop.

```bash
uv sync                      # install Python 3.12 + libraries into .venv
docker compose up -d --wait  # start Postgres 16 + pgvector
uv run pytest                # run all tests
```

Copy `.env.example` to `.env` to change settings. By default `LLM_PROVIDER=fake`,
so **nothing calls a paid API** unless you switch it on.

## Useful commands

| What | Command |
|---|---|
| Tests without the database | `uv run pytest -m "not db"` |
| Lint | `uv run ruff check .` |
| Stop Postgres (keeps data) | `docker compose down` |
| Wipe the database | `docker compose down -v` |

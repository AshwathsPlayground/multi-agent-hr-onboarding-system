# Zensible: multi-agent HR onboarding

A production-minded assignment using FastAPI, LangChain, LangGraph, PostgreSQL,
and LangSmith, with simulated enterprise integrations.

## Status

Only the development environment is implemented. Application code and tests will
follow architecture discussions. See [ADR-0001: Scope and execution modes](docs/adr/0001-scope-and-execution-modes.md)
for the accepted scope, completion criteria, and documentation standards. The
execution invariants and implementation simplifications are recorded in
[ADR-0008](docs/adr/0008-execution-invariants-and-implementation-shape.md).

## Environment setup

Prerequisites: Git, uv, and Docker with Docker Compose.

```bash
uv sync --locked
git config core.hooksPath .githooks
docker compose up -d --wait postgres
docker compose ps
```

Python is pinned to 3.12. PostgreSQL 18 Alpine uses a persistent Docker volume
and is available with these local development credentials:

```text
postgresql://zensible:zensible_dev@localhost:5433/zensible
```

Stop the service without deleting its volume:

```bash
docker compose stop postgres
```

For future live-model execution, populate the CLIProxyAPI placeholders from
`.env.example` in a Git-ignored `.env`. Preserve any existing local values.
The proxy URL currently used is `http://127.0.0.1:8317/v1`. Application consumption
of these settings, model selection, and LangSmith configuration are not implemented.

## Planned reviewer commands

**These interfaces are planned, not implemented.** Offline means no external calls
during tests after dependencies and the Docker image are available. PostgreSQL
integration tests will use isolated test data rather than reset development data.

| Purpose | Planned command |
| --- | --- |
| General offline suite | `uv run pytest` |
| Isolated PDF scenario, also included in the offline suite | `uv run pytest -m assignment -v -s` |
| Explicit live-model verification | `uv run pytest --live tests/live -v` |

Both modes use the same application and simulated enterprise tools. Offline tests
script model responses; live tests use a real model. Live execution is optional
for reviewers but must be exercised by us before submission.

The PDF fixture uses John Smith, Engineering Manager, Bangalore, joining October 1,
2026. It demonstrates partial completion and resumption after missing bank details
and training updates. FastAPI will expose creation, status, and update entry points;
routes and launch instructions will follow implementation.

## Navigation and development standards

- `pyproject.toml` and `uv.lock`: dependencies and reproducible installation.
- `compose.yaml`: local PostgreSQL.
- `.env.example`: placeholders; secrets belong in `.env`.
- `.githooks/`: Conventional Commit validation and Ruff lint/format checks on
  commit and push. Activate once per checkout with the setup command above.
- `docs/adr/`: focused architecture decisions and their trade-offs.

ADR-0002 through ADR-0006 define specialist boundaries. ADR-0007 defines the
parent graph and concurrency. ADR-0008 defines the small set of cross-cutting
execution rules that make the implementation robust without adding infrastructure.

Source layout, graph topology, state/recovery design, and detailed observability
remain open for subsequent discussions. Ruff is already installed:

```bash
uv run ruff check .
uv run ruff format --check .
```

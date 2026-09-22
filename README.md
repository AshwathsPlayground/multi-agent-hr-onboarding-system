# Zensible: multi-agent HR onboarding

A production-minded assignment using FastAPI, LangChain, LangGraph, PostgreSQL,
and LangSmith, with simulated enterprise integrations.

## Status

The first implementation slice is in place: typed domain contracts, deterministic
enterprise mocks, an idempotent operation executor, a reusable LangSmith tracing
seam, and a LangGraph parent with HR, IT, Compliance, Payroll, and Communication
specialist subgraphs. The PDF-shaped John Smith scenario runs offline and resumes
from a typed event after missing bank details and training evidence.

See [ADR-0001: Scope and execution modes](docs/adr/0001-scope-and-execution-modes.md)
for the accepted scope, [ADR-0008](docs/adr/0008-execution-invariants-and-implementation-shape.md)
for execution invariants, and [ADR-0009](docs/adr/0009-domain-contracts-and-state-seam.md)
for the contracts used by the implementation.

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

For live-model execution, populate the CLIProxyAPI placeholders from
`.env.example` in a Git-ignored `.env`. Preserve any existing local values.
The proxy URL currently used is `http://127.0.0.1:8317/v1`. Application consumption
of these settings is centralized in the typed settings and LangChain model factory.
The default graph and tests do not call the live model.

## Reviewer commands

Offline means no model or enterprise-provider calls. The simulation is stateful,
so tests exercise replay, failure, unknown outcomes, reconciliation, dependency
gating, resume events, and notification delivery through the same application
seams used by a future live adapter.

| Purpose | Command |
| --- | --- |
| General offline suite | `uv run pytest` |
| PDF scenario | `uv run pytest -m assignment -v -s` |
| PostgreSQL checkpointer smoke test | `uv run pytest --postgres tests/integration/test_postgres_checkpointer.py -v` |
| Explicit live-model verification | `uv run pytest --live tests/live -v` |

Both modes use the same model factory and application contracts. Live execution is
optional for reviewers and requires the local CLIProxyAPI settings in `.env`.

To run the local HTTP demo:

```bash
uv run uvicorn zensible.api.app:app --reload
```

Then create the PDF-shaped onboarding with `POST /onboardings` using the request
shown in `tests/integration/test_api.py`, and submit a `ResumeEvent` to
`POST /onboardings/{onboarding_id}/events` when training or bank details arrive.

The PDF fixture uses John Smith, Engineering Manager, Bangalore, joining October 1,
2026. It demonstrates partial completion and resumption after missing bank details
and training updates. The FastAPI service is intentionally an in-memory demo seam;
the PostgreSQL checkpoint adapter is implemented and tested separately so it can be
introduced without changing the graph contracts.

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

The current source layout is:

- `src/zensible/domain/`: serializable business contracts.
- `src/zensible/agents/`: private specialist subgraphs.
- `src/zensible/orchestration/`: parent graph and checkpoint-friendly state.
- `src/zensible/simulation/`: deterministic enterprise fixtures.
- `src/zensible/tools/`: idempotent side-effect boundary.
- `src/zensible/observability.py`: one opt-in native LangSmith seam.
- `src/zensible/config.py` and `src/zensible/llm.py`: runtime settings and model factory.

Ruff is already installed:

```bash
uv run ruff check .
uv run ruff format --check .
```

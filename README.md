# Zensible: multi-agent HR onboarding

A production-minded assignment using FastAPI, LangChain, LangGraph, PostgreSQL,
and LangSmith, with simulated enterprise integrations.

## Status

The implementation includes typed domain contracts, deterministic enterprise
mocks, an idempotent operation executor, a reusable LangSmith tracing seam, and a
LangGraph parent with HR, IT, Compliance, Payroll, and Communication specialist
subgraphs. The same graph accepts either a scripted structured model for offline
replay or the configured live LangChain model. The PDF-shaped John Smith scenario
runs offline and resumes from a typed event after missing bank details and training
evidence.

See [ADR-0001: Scope and execution modes](docs/adr/0001-scope-and-execution-modes.md)
for the accepted scope, [ADR-0008](docs/adr/0008-execution-invariants-and-implementation-shape.md)
for execution invariants, [ADR-0009](docs/adr/0009-domain-contracts-and-state-seam.md)
for the contracts used by the implementation, and [ADR-0010](docs/adr/0010-provider-switching-and-observable-e2e.md)
for model providers and reviewer-visible execution.

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

Offline means no network calls. The simulation is stateful, and the scripted model
plus simulated enterprise tools exercise replay, failure, unknown outcomes,
reconciliation, dependency gating, resume events, and notification delivery through
the same application seams used by live execution.

| Purpose | Command |
| --- | --- |
| General offline suite | `uv run pytest` |
| PDF scenario | `uv run pytest -m assignment -v -s` |
| Agent-level scenarios with visible output | `uv run pytest tests/unit/agents -v -s` |
| Observable offline end-to-end flow | `uv run pytest tests/e2e -v -s` |
| PostgreSQL checkpointer smoke test | `uv run pytest --postgres tests/integration/test_postgres_checkpointer.py -v` |
| Live model and onboarding flow | `uv run pytest --live tests/live -v -s` |
| Offline reviewer demo | `uv run zensible-demo --mode offline` |
| Live reviewer demo with simulated tools | `uv run zensible-demo --mode live` |

The default graph and tests use the scripted provider. Live execution is explicit,
requires the local CLIProxyAPI settings in `.env`, and uses the same graph, typed
contracts, and simulated enterprise tools. The live tests assert structured results
and business invariants rather than exact natural-language wording.

The reviewer demo prints a compact, human-readable transcript of model
requests/responses, simulated tool requests/responses, agent results, and the
initial/resumed graph status. `--no-resume` shows only the first run. Use
`--format json` when a machine-readable JSON Lines transcript is needed.

```bash
uv run zensible-demo --mode offline --format json
```

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
- `src/zensible/modeling/`: scripted and live structured model adapters.
- `src/zensible/observability.py`: one opt-in native LangSmith seam.
- `src/zensible/config.py` and `src/zensible/llm.py`: runtime settings and model factory.
- `src/zensible/demo.py`: reviewer-facing offline/live transcript command.

Ruff is already installed:

```bash
uv run ruff check .
uv run ruff format --check .
```

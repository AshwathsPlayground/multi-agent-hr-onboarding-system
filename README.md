# Zensible: multi-agent HR onboarding

A production-minded HR onboarding assignment built with FastAPI, LangChain,
LangGraph, PostgreSQL checkpoints, and optional LangSmith tracing.

The parent graph coordinates five specialist subgraphs:

```text
HR → IT + Compliance + Payroll (parallel) → actions → Communication
```

The enterprise systems are deterministic simulated tools. The model provider is
switchable, so the same graph can run offline or against the configured live
CLIProxyAPI model.

Models return bounded specialist guidance: proceed, request input, escalate, or
approve a subset of candidate tasks. The parent graph validates that guidance
before it permits any dependency-checked side effect.

## Setup

Requirements: Python 3.12, `uv`, and Docker.

```bash
uv sync --locked
git config core.hooksPath .githooks
docker compose up -d --wait postgres
```

PostgreSQL is available at:

```text
postgresql://zensible:zensible_dev@localhost:5433/zensible
```

Live mode reads CLIProxyAPI settings from the ignored `.env` file. Copy the
placeholders from `.env.example` and keep the proxy running at the configured URL.

## Demo modes

### Offline assignment demo

No network or live model calls. Uses scripted model responses and simulated tools.

```bash
uv run zensible-demo --mode offline
```

This runs the PDF-shaped John Smith scenario twice: first it waits for missing
bank/training evidence, then it resumes with a `ResumeEvent` and completes the
available work. Use `--no-resume` to show only the first run.

### Live model demo

Uses the real configured model but keeps enterprise tools simulated:

```bash
uv run zensible-demo --mode live
```

Both demos print model requests/responses, agent results, tool effects, and graph
status in a readable transcript. Add `--format json` for JSON Lines output.

## Test commands

```bash
# All offline tests
uv run pytest -q

# PDF scenario with visible transcript
uv run pytest -m assignment -v -s

# Agent and offline end-to-end scenarios
uv run pytest tests/unit/agents tests/e2e -v -s

# PostgreSQL checkpoint recovery
uv run pytest --postgres tests/integration/test_postgres_checkpointer.py -v -s

# Live provider happy path and specialist edge cases
uv run pytest --live tests/live -v -s
```

The `-s` flag shows printed transcripts. Live tests call the configured model;
their tools remain simulated and assertions check stable business outcomes rather
than exact natural-language wording.

Pull requests run the offline suite, Ruff, and PostgreSQL checkpoint tests in
GitHub Actions. Live-provider tests remain opt-in because they require credentials.

## Where to look

- `src/zensible/domain/`: typed business contracts and graph state.
- `src/zensible/agents/`: HR, IT, Compliance, Payroll, and Communication subgraphs.
- `src/zensible/orchestration/`: parent graph, planning, actions, and status rules.
- `src/zensible/tools/`: idempotent side-effect executor.
- `src/zensible/modeling/`: scripted and live structured model adapters.
- `src/zensible/observability.py`: shared event transcript and LangSmith seam.
- `tests/`: unit, offline end-to-end, PostgreSQL, and live-provider tests.
- `docs/adr/`: architecture decisions and scope.

The FastAPI demo is available with:

```bash
uv run uvicorn zensible.api.app:app --reload
```

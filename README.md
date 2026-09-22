# Zensible: multi-agent HR onboarding

A production-minded onboarding application using FastAPI, LangChain, LangGraph,
PostgreSQL, and LangSmith, with simulated enterprise integrations.

The planned application coordinates HR, IT, Compliance, Payroll, and Communication
agents. It handles incomplete information, changing dependencies, tool failures,
uncertain operation outcomes, and human intervention.

## Current status

**Only the development environment is implemented.** Python dependencies are
locked, PostgreSQL is configured through Docker Compose, and connectivity and a
temporary FastAPI server have been smoke-tested. No application, test suite, model
provider adapter, or evaluation runner exists yet.

The structure and application/test commands below describe the proposed interface
we will implement after documenting the architecture. They are not runnable yet.

## Set up the existing environment

Prerequisites: Git, uv, and Docker with Docker Compose.

From the repository root:

```bash
git config core.hooksPath .githooks
uv sync --locked
docker compose up -d --wait postgres
docker compose ps
```

The Git hook configuration is tracked in `.githooks/`. The `commit-msg` hook
enforces Conventional Commits. The `pre-commit` and `pre-push` hooks run Ruff
lint and format checks. Run the `git config` command once after cloning this
repository to activate the tracked hooks in that checkout.

The project pins Python 3.12. PostgreSQL 18 Alpine runs on `localhost:5433`, with
database/user `zensible` and development password `zensible_dev`. Data is stored in
the Compose-managed `postgres_data` volume. These are local development settings.

```text
postgresql://zensible:zensible_dev@localhost:5433/zensible
```

Stop the database without deleting its volume:

```bash
docker compose stop postgres
```

## Execution and testing approach

One application implementation will serve the API, deterministic tests, and
optional live-model evaluations. Tests substitute dependencies at the model and
enterprise-service boundaries; they do not implement a separate workflow.

| Component | Offline verification | Optional live-agent verification |
| --- | --- | --- |
| Graph, routing, state validation | Real application | Same application |
| Dependency checks and operation recovery | Real application | Same application |
| Model | Scripted responses, including tool calls | Configured model provider |
| Enterprise tools | Stateful simulated services | Same simulated services |
| Checkpoints | In-memory for unit tests; PostgreSQL for integration tests | PostgreSQL |
| LangSmith | Disabled | Optional tracing and evaluation reporting |

Offline means no external API calls during tests after dependencies and the Docker
image have been installed. Database tests still require local PostgreSQL.
Live tests require credentials, network access, and may incur model charges.
They must be explicitly selected and never run as part of the default suite.

Production-minded means explicit boundaries, validated state, bounded retries,
idempotent operations, resumable execution, and inspectable outcomes. Authentication
will initially be represented by a production TODO at the request boundary.
Real enterprise integrations, durable job dispatch, and multiple workers remain
future deployment concerns.

## Planned repository layout

Only the root environment files and this README currently exist as tracked files.
The following is the proposed layout, subject to architecture decisions:

```text
src/zensible/
  api/                  # FastAPI request/response handling
  onboarding/           # Shared application entry points and domain schemas
  agents/               # Five specialist agents and their structured outputs
  workflow/             # LangGraph coordination, dependencies, pause/resume
  tools/                # Enterprise-tool contracts and guarded operations
  simulation/           # Stateful fake enterprise systems and fault injection
  persistence/          # Checkpointer and operation-record integration
  observability/        # Shared trace context, metadata, and redaction
  config.py             # Validated configuration
tests/
  unit/                 # Isolated deterministic checks
  integration/          # PostgreSQL persistence and recovery
  scenarios/            # General end-to-end offline business scenarios
  live/                 # Explicitly enabled real-model evaluations
  fixtures/             # Reusable requests, policies, and simulated environments
docs/
  adr/                  # Architecture decisions; currently empty
compose.yaml
pyproject.toml
uv.lock
README.md
```

Start with `onboarding/` to understand the application boundary, then `workflow/`
for coordination, `agents/` for reasoning, and `tools/` plus `simulation/` for
external actions. Tests should be the executable description of required behavior.

## Planned reviewer commands (not implemented yet)

After setup, the default command will run the general offline suite, including
database integration tests against an isolated test database:

```bash
uv run pytest
```

The test harness will create/prepare a dedicated test database and isolate each
case's records and checkpoint IDs. It must never reset the development database.
Unit tests alone will require no PostgreSQL service:

```bash
uv run pytest tests/unit
```

The assignment's example will be a separately selectable scenario in the same
suite, using the same application and simulation infrastructure:

```bash
uv run pytest -m assignment -v -s
```

This command will display the onboarding summary and verify both the initial
partially completed state and completion after supplying missing information.
The assignment marker will also be included in the default offline suite.

Optional real-model cases will use an explicit opt-in:

```bash
uv run pytest --live tests/live -v
```

`assignment` and `--live` are proposed pytest interfaces, not existing options.
Model-provider selection and credential configuration will be documented when
implemented. LangSmith reporting will be separately configurable; ordinary
assertions must remain useful without it.

## Planned PDF scenario walkthrough

The initial request is:

```json
{
  "employee_name": "John Smith",
  "role": "Engineering Manager",
  "location": "Bangalore",
  "joining_date": "2026-10-01"
}
```

Scenario configuration is separate from this business request. The fixture sets
company policy, missing bank details, training status, and any simulated faults.

1. HR validates the employee and job information.
2. IT, Compliance, and Payroll assess their requirements in parallel.
3. Their results establish task dependencies before provisioning starts.
4. Eligible independent work proceeds: a laptop request and compliance case can
   complete while AWS access waits for training and payroll waits for bank details.
5. Communication records an interim notification. The application returns completed,
   blocked, and pending tasks, with reasons and next actions.
6. The test submits bank details and records completed training in the simulated
   systems. The workflow resumes and verifies those updates.
7. Remaining work completes and a final notification is recorded.

Creating a request is not automatically equivalent to completing its downstream
fulfilment. Mock status responses and explicit completion criteria will determine
when each task is finished. No real equipment, accounts, payroll, or email is created.

## Planned general scenario coverage

The application will support role/location/policy variations rather than hard-code
John Smith. The PDF case is one fixture among the broader scenarios.

| Scenario | Required evidence |
| --- | --- |
| Happy path | All required work completes and the summary agrees with state |
| Missing personal or payroll information | Targeted input request; independent work continues |
| Cross-agent prerequisite | Dependent action cannot execute before verified completion |
| Conflicting source data | Explicit resolution or escalation; affected work waits |
| Transient failure | Bounded retry and recorded recovery |
| Timeout after successful write | Reconciliation finds the existing operation without duplication |
| Permanent failure | Accurate failure/escalation, no false completion |
| Human interruption and resume | Input is validated and remaining work continues |
| Duplicate requests or updates | No repeated business effects |
| Process restart | Checkpoints and simulated operation history remain consistent |
| Invalid agent proposal or no progress | Validation rejects it or execution exits within a defined bound |

Offline assertions verify business outcomes and prerequisite ordering, allowing
valid differences in execution order. Live evaluations additionally measure
requirement discovery, tool selection, structured-output validity, and explanation
accuracy. Critical correctness failures cannot be offset by a high language-quality
score. LangSmith will make individual executions and evaluation results inspectable.

## Planned API usage

FastAPI will accept the same validated input used by tests and expose creation,
status, and submission of external updates. Exact routes will follow the API design.
The proposed launch command is:

```bash
uv run uvicorn zensible.api.app:app --app-dir src --reload
```

This module does not exist yet. Once implemented, Swagger at
`http://127.0.0.1:8000/docs` will provide an interactive entry point.

## Linting and formatting

Ruff is already installed. Once Python source exists:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Documentation plan

This README is the entry point for setup, navigation, and reviewer commands.
Architecture decisions will be discussed and recorded under `docs/adr/` before
implementation. No documents in that directory have been created yet.

# ADR-0001: Scope and execution modes

- Status: Accepted
- Date: 2026-09-22
- Basis: Scope interview and explicit user confirmation before documentation

## Context

The assignment requires HR, IT, Compliance, Payroll, and Communication to coordinate
onboarding while handling missing information, dependencies, failures, conflicting
data, and idempotency. Mock integrations and additional tools are permitted.

The submission should demonstrate production-minded engineering without building
deployment infrastructure. Reviewers need repeatable verification without model
credentials, while we must also verify actual model behavior before completion.

## Decision

### Application scope

Implement all five areas as focused modules with clear responsibilities and
meaningful agent-specific coverage. No agent is the sole robustness showcase.
Choose a finite set of common and domain-specific scenarios rather than claiming
to cover every real-world situation.

Prefer native LangChain, LangGraph, and LangSmith capabilities. Custom logic should
focus on business rules and reliable integration behavior. Use one application
implementation for FastAPI, offline tests, and live execution.

FastAPI will accept validated onboarding requests and expose status and external
updates. Authentication is represented by a production TODO at the input boundary.
Enterprise records, provisioning, payroll, training, and notifications remain
simulated in both modes; no real accounts, requests, or messages are created.

Keep PostgreSQL checkpointing. Require interruption and resumption within the
running application. Process-restart recovery is deferred: persistent checkpoints
alone do not establish complete recovery across restarts.

### Execution modes

| Concern | Offline | Live |
| --- | --- | --- |
| Graph, validation, business and recovery logic | Real application | Same application |
| Model | Scripted responses, including tool calls | Real model through configured provider/proxy |
| Enterprise tools | Stateful simulated services | Same simulated services |
| Persistence | PostgreSQL where integration is tested; isolated unit tests may use memory | PostgreSQL |
| External calls | None during tests after dependency/image installation | Explicit model access and optional LangSmith reporting |
| LangSmith tracing | Disabled | Enabled when configured |

Live tests require explicit opt-in and must never run merely because credentials
are present. Reviewers may run offline only. We must successfully exercise a small
live-model suite before declaring the submission complete.

Offline tests replace model responses and enterprise integrations at their
boundaries, not the graph or its final outcomes. Live tests verify the same business
rules while allowing different valid tool-call sequences.

### Scenario strategy

General scenarios use reusable fixtures for requests, starting enterprise state,
and fault behavior. Simulation controls are separate from normal onboarding input.
Tests isolate state and database records without resetting development data.

Implement common reliability patterns once, test them independently, and exercise
them through representative agent scenarios. Do not duplicate the full fault
matrix for every agent. Common patterns include bounded retries, idempotent writes,
reconciliation of uncertain outcomes, interruption/resume, and explicit escalation.

Checkpoints and interrupts support saved progress and waiting. They do not alone
prevent duplicate downstream operations after a timeout. Verify actual effects,
not only status summaries.

| Agent | Representative focused coverage to refine during design |
| --- | --- |
| HR | Missing employee/job information and conflicting sources |
| IT | Equipment/access requirements and unmet prerequisites |
| Compliance | Applicable requirements and incomplete checks/training |
| Payroll | Missing/invalid details and uncertain submission outcomes |
| Communication | Accurate interim/final notices and duplicate prevention |

Across the suite, cover success, missing information, cross-agent dependencies,
transient failures/timeouts, conflicts, timeout after a successful write, duplicate
inputs/actions, interruption/resume, and failures requiring human resolution.
Routine waiting for information is distinct from escalation. Creating a downstream
request is not inherently proof of fulfilment; summaries must reflect actual state.

The PDF scenario is separately selectable and included in the general offline
suite. It uses the same implementation with John Smith's Engineering Manager role,
Bangalore location, and October 1, 2026 joining date. Show partial completion with
missing bank details and incomplete training, then resume after updates.
Include a small number of input/policy variations in general tests so behavior
is not hard-coded to John Smith.

### Observability and evaluation budget

Use native LangChain/LangGraph tracing and LangSmith's `@traceable` for meaningful
application operations not already traced. Use native trace/run IDs and consistent
onboarding/agent metadata. Avoid duplicate spans and a custom tracing framework.
The detailed instrumentation design remains open.

Prioritize inspectable, debuggable execution. Ordinary assertions enforce business
correctness. Minimal optional LangSmith pytest pass/fail reporting is acceptable
if straightforward. Custom judges, extensive scoring, and dashboards are deferred;
qualitative scores cannot compensate for incorrect business outcomes.

### Completion criteria

- All five functional areas participate in the complete demonstration.
- General offline tests pass without model credentials or external API calls.
- Shared reliability patterns and focused agent-specific scenarios have meaningful
  outcome-based assertions.
- The isolated PDF scenario reports partial completion and resumes after updates.
- PostgreSQL checkpointing and in-process interruption/resumption are exercised.
- FastAPI uses the same application behavior verified by the tests.
- A small live-model suite has been successfully exercised against simulated tools.
- Basic LangSmith tracing has been exercised and supports inspection of agent work.
- README setup and reviewer commands match implemented behavior at submission.

### Deferred scope

Process-restart recovery guarantees, multiple workers, durable job queues, real
authentication/authorization, real enterprise integrations, deployment scaling
infrastructure, exhaustive real-world coverage, and elaborate evaluation scoring.

Scalability is a design consideration, not a claimed measured capacity. Describe
the submission as production-minded rather than production-ready.

## Standard for subsequent work

Keep README concise: setup, navigation, status, and reviewer commands. Use numbered
ADRs for focused decisions with status, context, decision, and consequences.
Distinguish proposals from accepted decisions and plans from working features.
Discuss open architecture choices before recording acceptance. Update or supersede
decisions explicitly as scope changes.

Next discussions: agent orchestration and boundaries; state ownership and recovery
mechanics; shared observability details. This ADR does not choose graph topology,
agent write permissions, database schemas, retry limits, or API routes.

Use the existing uv lockfile, Conventional Commit hooks, and Ruff checks. Add
behavioral tests alongside implementation, keep credentials out of Git, and preserve
one application path across modes. Add infrastructure only when required by scope.

## Consequences

Reviewers receive repeatable verification, while live runs check model behavior
that scripted tests cannot establish. Shared patterns limit duplication while
giving all agents meaningful coverage.

Simulations cannot prove real integration behavior. Offline success does not prove
model quality, and a small live suite offers limited evidence of reliability.
PostgreSQL adds setup overhead but remains an explicit choice. Deferred deployment
and recovery capabilities must not be presented as implemented.

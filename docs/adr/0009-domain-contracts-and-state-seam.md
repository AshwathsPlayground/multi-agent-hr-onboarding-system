# ADR-0009: Typed domain contracts and the state seam

- Status: Accepted
- Date: 2026-09-22

## Context

The onboarding workflow crosses a parent LangGraph, specialist subgraphs,
simulated enterprise tools, a PostgreSQL checkpointer, and a future live API.
Those boundaries need stable data shapes. LangSmith traces are useful for
diagnosis, but they must not become the source of truth for business state.

## Decision

Use Pydantic contracts for data that crosses graph, agent, tool, API, or
checkpoint boundaries.

- `OnboardingRequest` is the typed input for one onboarding.
- `AgentContext` is compact checkpointable state: onboarding identity, state and
  facts revisions, policy version, validated HR facts, findings, tasks,
  operations, and an optional resume event.
- `SpecialistResult[T]` is the common result envelope. It carries the owning
  agent, phase, outcome, typed payload, findings, missing inputs, conflicts,
  proposed tasks, effects, notifications, and errors.
- `TaskProposal` and `TaskRecord` identify work independently from its outcome.
  Named `RequirementCode` values are validated by deterministic parent logic;
  models do not supply executable dependency expressions.
- `OperationRecord` is the idempotency and reconciliation record. An operation
  key identifies one logical write and a request fingerprint prevents the same
  key from being reused for different data.
- `ResumeEvent` is the controlled input for corrections, evidence, external
  updates, conflict resolutions, and notification retries.

The parent graph owns durable state, dependency validation, scheduling, status
classification, and interruption/resumption. Specialist subgraphs receive typed
snapshots and return typed results; they do not mutate parent state directly.

## Consequences

- Graph state can be serialized and restored without storing arbitrary model
  messages as business state.
- Parent routing can be tested without a live model or provider integration.
- Operation effects can be replayed safely and unknown outcomes can be
  reconciled before retrying.
- Specialist implementations can change internally while their public seams
  remain stable.
- Additional payload models can be added without changing the common routing
  envelope.

## Non-goals

- No provider-specific integrations are part of the offline assignment slice.
- The LLM does not generate arbitrary state, dependency predicates, or final
  business status.
- LangSmith traces, spans, and evaluations are observability data only; they are
  not a durable transaction log or checkpoint store.
- The first implementation does not introduce a general workflow engine beyond
  the parent LangGraph and named requirement predicates.

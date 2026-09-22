# ADR-0010: Provider switching and observable end-to-end execution

- Status: Accepted
- Date: 2026-09-22

## Context

The assignment needs both reproducible offline verification and evidence that the
agents can call the configured live model. Assertions on only the final graph state
hide what each agent and simulated enterprise tool produced. A test-only fake graph
would also fail to prove that the real application path works.

## Decision

Use one structured model interface for every specialist graph. Select the adapter at
the composition seam:

- Offline tests and the default demo use `ScriptedStructuredAgentModel`.
- Explicit live tests and the live demo use `LangChainStructuredAgentModel`, backed
  by the existing `ChatOpenAI` CLIProxyAPI factory.

Both adapters validate their response through the caller-provided Pydantic model.
The model can propose an assessment, but deterministic domain policy, proposal
validation, and the operation executor remain authoritative for side effects.

Use a small `RecordingEventSink` for reviewer-visible JSON-line transcripts. It
records model and tool requests/responses without becoming business state, a
transaction log, or a replacement for LangSmith. LangSmith remains the tracing
system when its environment is explicitly enabled.

Pytest selection remains explicit:

- no `--live`: scripted provider and offline tests;
- `--live`: real provider tests;
- `--postgres`: PostgreSQL checkpoint tests.

The live onboarding test uses the real model but keeps enterprise tools simulated.
It asserts parseable structured outputs, expected agents, simulated effects, and
valid business states rather than exact prose.

## Consequences

Reviewers can run the exact same graph offline, inspect every intermediate model and
tool event, and then opt into a live provider run without changing graph code. The
scripted adapter makes failure and resume scenarios deterministic. The live suite is
slower and can vary in wording, so it is opt-in and invariant-based.

The current model output is an observable structured assessment with bounded guidance
for proceed, input requests, escalation, and optional candidate-task selection.
Deterministic domain rules still produce the candidate tasks and remain authoritative
for prerequisites, validation, and side effects. ADR-0011 records how model guidance
is applied without allowing arbitrary model-generated writes.

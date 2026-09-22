# ADR-0008: Execution invariants and implementation shape

- Status: Accepted
- Date: 2026-09-22
- Basis: Review of ADR-0001 through ADR-0007 and user approval to record the notes

## Context

The preceding ADRs cover scope, five specialist boundaries, Communication, and
the parent graph. A robust implementation still needs a few cross-cutting rules
at the seams between planning, action, interruption, and notification. Without
them, the graph could loop, reuse stale proposals, misreport completion, or retry
an uncertain side effect more than once.

The assignment rewards dynamic coordination and resilience. We want to demonstrate
those properties with a small codebase and stateful simulations, rather than build
a general workflow platform.

## Decision

### Re-assessment is an explicit outcome

Agent results may report `requires_reassessment` when a tool or action reveals new
requirements, a relevant fact changes, or an earlier proposal is no longer valid.
The parent routes that result to the responsible specialist before making another
write eligible. Re-checking the old task list is not sufficient.

The parent will initially reassess all relevant specialist branches after a relevant
update. Fine-grained dependency invalidation is deferred until measurements show it
is needed. This conservative approach is simpler and avoids stale downstream plans.

### No runnable work has distinct meanings

After each merge, the parent classifies the state as one of:

- `complete`: all required task goals have reached their defined terminal success.
- `waiting_for_input`: an actionable external value is required.
- `waiting_for_external_event`: a submitted task is still progressing elsewhere.
- `needs_resolution`: a human decision is required for conflict, uncertainty, or
  an adverse/review-required result.
- `blocked_by_failure`: bounded recovery has failed and the task cannot proceed.
- `invalid_plan`: a malformed proposal, missing dependency, unknown task reference,
  or dependency cycle was rejected.
- `no_progress`: the graph made no state change within its execution bound.

Only actionable waiting states interrupt. Completion, terminal failure, and invalid
plans return a final status. The parent validates dependency references and rejects
cycles when proposals are merged.

### Task completion is defined per intent

Every task carries an explicit goal and completion predicate. For example:

- A `submit_it_request` task succeeds when the simulated downstream request is
  accepted and its request reference is recorded.
- A `verify_security_training` task succeeds only when trusted evidence reports
  completion.
- A `deliver_notification` task succeeds when the simulated delivery is confirmed.

Acceptance, fulfilment, verification, and delivery are separate states. Overall
onboarding completion is computed from required task predicates, not from an LLM
summary or the existence of a request record.

### One retry owner per side effect

The application operation executor owns retries and reconciliation for writes.
Model-provider retries and graph-level reruns must not independently retry a write.
Reads may use bounded transient retries. For an uncertain write, reconcile by the
stable operation key before another submission. If reconciliation remains uncertain,
return `needs_resolution` and preserve the uncertainty.

An operation key is derived from the onboarding ID, logical task ID, operation type,
and relevant request revision. It remains unchanged across retries of the same
operation and changes only when the business action is intentionally revised.

### State revisions prevent stale actions

The onboarding state has a monotonically increasing revision. Specialist proposals
record the revision and relevant fact/policy versions used to produce them. The
parent accepts a proposal for action only when those versions still match. A
changed employee fact, policy, or prerequisite makes affected proposals stale and
routes them to reassessment before another write.

Updates for one onboarding are serialized. Concurrent specialist results merge into
separate result slots and are validated by the parent; they do not overwrite a
shared overall status or each other's task collections.

### Notification recovery is separate

If the business workflow is complete but Communication cannot deliver the final
notification, the parent records business completion and schedules a notification-only
retry or resolution path. It never re-runs provisioning to retry a message. The
notification operation has its own stable identity and reconciliation record.

### Keep the implementation small

Use these shared pieces instead of building an agent platform:

1. One typed result envelope for specialist findings, blockers, proposed tasks,
   reassessment requests, and notification needs, with typed domain payloads for
   HR facts, compliance evidence, and other specialist data.
2. One specialist runner helper that supplies the model, prompt, scoped tools,
   structured output schema, and trace metadata. Domain validation remains outside
   the helper.
3. One deterministic operation executor for stable keys, existing-result lookup,
   submission, uncertainty, and reconciliation.
4. One stateful simulated company whose scoped adapters expose HR, IT, Compliance,
   Payroll, and Communication tools and record actual effects.
5. Deterministic execution of validated action proposals; do not add a second LLM
   call merely to execute a safe, already-approved operation.
6. Templates for authoritative status fields and next actions; use a model only
   when readable explanation adds value.
7. Parameterized tests for shared reliability patterns, plus focused agent tests
   for domain rules. The PDF scenario is a fixture using the same implementation.

The initial reassessment strategy may rerun a few small assessments. Do not add
fine-grained scheduling, a custom queue, multiple workers, or a general dependency
engine for this assignment.

## Consequences

These rules close the main correctness gaps without expanding the infrastructure
scope. New requirements can feed back into planning, blocked states are explainable,
stale plans cannot silently create writes, and notification failure is recoverable
without repeating business effects.

The parent performs more validation and may repeat assessments after updates. That
cost is acceptable for the assignment and easier to reason about than incremental
invalidation. The state revision and operation key contracts must be designed before
implementation; exact database tables and LangGraph state schemas remain part of
the next state/recovery discussion.

This ADR does not choose agent prompts, model provider, retry counts, API routes,
or the final subgraph state schemas.

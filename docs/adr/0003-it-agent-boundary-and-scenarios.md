# ADR-0003: IT agent boundary and scenarios

- Status: Accepted
- Date: 2026-09-22
- Basis: User approval of the IT agent proposal

## Context

IT must determine equipment, applications, and access requirements while respecting
HR facts and Compliance prerequisites. Provisioning changes external state, so
timeouts and repeated execution must not produce duplicate effects.

## Decision

### Responsibility and boundary

IT owns provisioning requirements and their operational status. It consumes
validated employee facts and verified Compliance results. It cannot waive training,
resolve employment conflicts, or bypass policy. It may submit provisioning requests
through shared validation and idempotency handling.

Policy must explicitly permit substitutions. Changes to requirements after a
request is submitted require human review. Automated cancellation, access revocation,
and compensation are outside this assignment's scope.

### Inputs and outputs

Inputs include validated employee ID, role, location, joining date, IT policy,
verified compliance results, existing resources, and request statuses.

Return required resources, prerequisites, blockers, existing/new request references,
per-item outcomes, and next actions. Preserve partial progress. Request acceptance
is distinct from resource provisioning; pending fulfilment must not be reported as
completed provisioning.

### Tools and enforcement

Use `get_it_requirements()`, `create_it_request()`, and `get_task_status()`.
Add `get_existing_it_resources()` for existing assets/access and
`get_operation_status()` for uncertain submission reconciliation. Signatures and
ownership of shared adapters remain implementation decisions.

Model reasoning interprets requirements, proposes requests, identifies blockers,
and explains next steps. Code validates fields and allowed resources/access,
enforces verified prerequisites, derives stable business-action idempotency keys,
bounds retries, reconciles uncertainty, and validates status transitions.

Training completion must come from verified evidence, not an unsupported model
assertion. The model must not generate a fresh idempotency key for each retry.

### Required scenario coverage

| Scenario | Expected evidence |
| --- | --- |
| Valid requirements and prerequisites | Correct requests submitted |
| Resource already assigned | Reused when policy permits, without duplication |
| Equivalent request pending | Existing reference returned |
| Training incomplete | Dependent access blocked; independent work proceeds |
| Training completes | Eligibility revalidated; remaining work submitted |
| Unsupported resource or excessive access proposed | Proposal rejected |
| Missing/conflicting employee facts | Affected decisions wait for HR resolution |
| Equipment unavailable | Blocker reported; substitution only under explicit policy |
| Transient tool failure | Appropriate shared bounded retry behavior |
| Submission succeeds then times out | Operation reconciled without duplicate effects |
| Outcome remains uncertain | Uncertainty preserved and escalated, no blind retry |
| Mixed successes and failures | Per-item outcomes preserve partial progress |
| Duplicate update or invocation | No repeated provisioning effect |
| Request accepted, fulfilment pending | Accurate pending status |
| Malformed tool data or invented success | Unsupported completion rejected |
| Requirements change after submission | Mismatch identified and human review requested |

Use shared reliability tests plus representative IT cases. Inspect simulated request
history, prerequisite evidence at submission, and effect counts rather than relying
solely on final prose. Live checks allow different valid tool sequences.

## Consequences

IT demonstrates meaningful guarded writes and cross-agent dependencies while keeping
scope bounded. Existing-resource and operation lookups require stateful mock services.
Human review for post-submission changes avoids implementing a separate compensation
workflow. Parent orchestration and shared state/recovery mechanics remain open.

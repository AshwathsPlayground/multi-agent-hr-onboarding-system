# ADR-0011: Bounded model guidance for specialist decisions

- Status: Accepted
- Date: 2026-09-22
- Basis: Follow-up review identified that model output was previously observable but not behaviorally relevant

## Context

The first implementation called a structured model for every specialist, but the
deterministic specialist code generated all proposals regardless of the model's
assessment. This made the model an observability detail rather than a participant
in agent decision-making.

The model must influence the workflow without being allowed to invent facts,
bypass prerequisites, or perform side effects directly.

## Decision

Extend `ModelAssessment` with bounded guidance:

- `decision=proceed`: continue with eligible deterministic work.
- `decision=request_input`: add structured requested inputs. If the model also
  supplies `approved_task_ids`, safe independent candidates may proceed while
  the remaining candidates are deferred; without an explicit approval list, all
  proposed work is deferred for that specialist.
- `decision=escalate`: produce an explicit resolution outcome and prevent proposed
  writes for that specialist.
- `approved_task_ids`: optionally select from deterministic candidate task IDs.

The specialist supplies candidate IDs to the model. The shared runtime validates
any selected IDs against that allowlist and filters proposals accordingly. Unknown
IDs are invalid model output and result in a safe resolution state. Candidates
that are omitted from an explicit approval list are retained as visible deferred
tasks rather than being dropped. A ready deferred task becomes
`needs_resolution`, so a model cannot silently suppress required work and allow
the onboarding to complete. Deterministic prerequisite-blocked tasks remain
blocked until their requirements are satisfied.

The parent graph remains authoritative for schema validation, cross-agent
dependencies, state revisions, operation identity, idempotency, and side effects.
Model guidance cannot make an ineligible task ready or bypass a required
requirement.

## Consequences

Model output now changes specialist outcomes and parent orchestration while keeping
the safety boundary deterministic. Offline tests can prove model-guided routing
without network calls, and live tests can exercise the same structured contract.

The model still does not directly call enterprise tools. Tool execution remains a
validated parent-graph responsibility so that model mistakes become visible,
bounded outcomes rather than duplicate or unauthorized writes.

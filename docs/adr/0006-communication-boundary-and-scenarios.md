# ADR-0006: Communication boundary and scenarios

- Status: Accepted
- Date: 2026-09-22
- Basis: User approval of centrally invoked Communication

## Context

Independent notifications from every specialist can duplicate requests or report
incomplete status. Communication needs an authoritative onboarding snapshot and a
clear trigger while remaining a distinct functional area.

## Decision

Use a small Communication subgraph invoked by the main onboarding graph. HR, IT,
Compliance, and Payroll return findings or notification needs rather than calling
Communication directly.

The parent identifies meaningful changes, determines overall work completion,
requests interim/action-needed/escalation/final notifications, and supplies the
authoritative snapshot. Communication prepares content, selects recipients using
explicit rules, validates facts and recipient details, sends via simulated tools,
and returns delivery outcomes.

Communication does not independently declare onboarding complete. Model-generated
wording must remain grounded in the supplied facts. Templates may serve standard
messages without an LLM call. Code enforces eligibility, required facts, and allowed
recipient information. Exact implementation and state mechanics remain open.

Use shared idempotency and reconciliation for delivery. Stable notification identity
must suppress equivalent repeated sends while permitting meaningful new updates.
Keep business-work completion and notification delivery status separate: a failed
final notification must not cause provisioning to run again.

## Required scenarios

- Partial completion accurately separates completed work, blockers, and next actions.
- Missing-information messages combine related requests clearly.
- Final completion notices require the parent's confirmed completion decision.
- Repeated unchanged state produces no duplicate notification.
- Meaningful new state permits a new notification.
- Missing recipients become delivery blockers rather than invented addresses.
- Recipient-specific messages exclude bank details and irrelevant sensitive data.
- Transient delivery failures use shared bounded retry behavior.
- Successful send followed by timeout is reconciled before retrying.
- Unsupported completion claims or contradictory model wording are rejected.

## Consequences

Central invocation consolidates communication and clarifies authority. The parent
must supply consistent snapshots and notification intent. Delivery is independently
observable and recoverable without repeating completed business actions. All
notifications remain simulated under ADR-0001.

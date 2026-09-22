# ADR-0002: HR agent boundary and scenarios

- Status: Accepted
- Date: 2026-09-22
- Basis: User approval of the HR agent proposal

## Context

Other onboarding specialists need grounded employee and employment facts. Missing
information, ambiguous identity, and conflicting records must be resolved explicitly
without allowing the model to invent facts or silently modify enterprise records.
This decision refines ADR-0001 without selecting the main orchestration topology.

## Decision

### Responsibility and boundary

HR is primarily a read-and-validate specialist. It establishes employee identity,
role, location, joining date, and additional fields required by simulated policy,
such as manager or department. A name alone is not a unique employee identifier.

IT owns equipment/access decisions, Compliance owns checks and training, Payroll
owns payroll-specific validation, and Communication owns outbound notifications.
HR returns structured information requests rather than sending notifications itself.

Corrections enter through a controlled application boundary, update simulated
records as appropriate, and are revalidated. HR has no unrestricted record-editing
tools and does not silently repair source records.

### Inputs and outputs

Inputs are the onboarding request, employee/job records, relevant company policy,
and previously supplied corrections or resolutions.

Return a structured outcome: `validated`, `needs_input`, `needs_resolution`, or
`failed`. Include validated facts with source references, missing fields and targeted
input requests, conflicting values and their sources, and a grounded explanation.
These are HR outcomes, not overall onboarding statuses. Waiting for information is
an expected business outcome rather than an exception.

### Tools and reasoning

Use `get_employee_details()`, `get_job_details()`, and `get_company_policy()`.
Add employee search if needed to separate identity resolution from retrieval by ID.
Exact signatures remain an implementation decision.

Use model reasoning to interpret requirements, identify inconsistencies, formulate
clarifications, and explain blockers. Use deterministic validation for schemas,
dates, required fields, value comparisons, provenance, allowed outcomes, and bounds
on execution. Reject unsupported facts and invalid model proposals.

Source-authority rules are explicit and field-specific. If policy does not resolve
a conflict, request human resolution rather than choosing the most plausible value.

### Required scenario coverage

| Scenario | Expected evidence |
| --- | --- |
| Complete consistent records | Validated facts with source references |
| Required field missing | Targeted request without invented values |
| Optional field missing | No unnecessary interruption |
| No employee match | Unresolved lookup or request for identification |
| Multiple employee matches | Explicit disambiguation, no arbitrary selection |
| Request conflicts with source record | Authority rule applied or conflict returned |
| Authoritative sources disagree | Both values preserved and resolution requested |
| Invalid date or unsupported value | Actionable validation issue |
| Past joining date | Policy applied, not unconditional rejection |
| Corrected information | Revalidation clears only resolved issues |
| Partial or invalid response | Remaining issues stay open with targeted follow-up |
| Transient lookup failure | Shared bounded retry or explicit failure |
| Malformed tool result | Integration failure, not misclassified missing information |
| Invented fact or invalid model output | Rejected with bounded correction or controlled failure |
| Repeated unchanged input | Equivalent facts/outcomes without duplicate effects |

Reuse shared reliability tests where appropriate rather than duplicating every
fault test. Offline tests script model responses, including invalid proposals,
while exercising actual validation. A small live subset covers consistent,
missing-information, and conflicting-record cases. Assert structured outcomes and
facts rather than exact wording.

### Engineering practices

Preserve provenance for accepted facts. Request only necessary information within
HR's responsibility. Keep evidence compact and avoid copying complete raw histories
into downstream contexts. Bound reasoning/tool loops. Distinguish missing input,
conflicts needing resolution, and unavailable integrations.

## Consequences

Downstream agents receive explicit, traceable facts and blockers. Controlled
correction and centralized notification ownership avoid hidden edits and duplicate
messages. This requires source-authority fixtures and validation at the model
boundary. Specialist subgraphs remain the working architectural proposal; detailed
topology, state ownership, and parent routing will be decided separately.

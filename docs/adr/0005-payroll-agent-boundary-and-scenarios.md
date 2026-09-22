# ADR-0005: Payroll agent boundary and scenarios

- Status: Accepted
- Date: 2026-09-22
- Basis: User approval of the Payroll agent proposal

## Context

Payroll setup requires complete, consistent compensation and bank information.
Submitting setup changes external state, so uncertain outcomes and repeated
invocations must not produce duplicate requests.

## Decision

### Responsibility and boundary

Payroll validates salary, currency, pay schedule, and bank-detail readiness against
fixture policy, using validated employee facts and authoritative compensation
records. It may submit simulated payroll setup requests. It cannot change salary,
invent bank details, resolve compensation disputes, or execute payments.

Tax calculations, deductions, salary proration, and money movement are out of scope.
Changes after submission require human review rather than automatic replacement.

### Inputs and outputs

Inputs include employee identity/location/joining date, authoritative compensation
details, bank-detail references and validation results, policy, and existing setup.
Outputs include requirements, validation results, missing fields, conflicts,
existing/new request references, setup status, blockers, and next actions.

Use references or masked bank details in model context and summaries. Mock-service
validation can inspect synthetic details without distributing them through prompts
and traces. Simulation does not claim to verify real account ownership.

### Tools and enforcement

Use `get_payroll_requirements()`, `create_payroll_request()`, and
`get_task_status()`. Add `get_compensation_details()`, `validate_bank_details()`,
`get_existing_payroll_setup()`, and shared `get_operation_status()` as needed.
Exact signatures remain implementation decisions.

The model interprets requirements and explains missing information or discrepancies.
Code enforces required fields, allowed currencies, effective-date rules, source
authority, and submission eligibility. Represent money with decimals; model arithmetic
is not authoritative. Apply shared stable idempotency keys and reconciliation.
Request acceptance is distinct from completed setup or activation.

### Required scenario coverage

| Scenario | Expected evidence |
| --- | --- |
| Complete consistent data | One eligible setup request |
| Bank details missing | Targeted information request and payroll waiting |
| Bank details malformed/rejected | Specific validation issue without full-detail exposure |
| Optional field absent | No unnecessary blocker |
| Salary/currency missing | Submission blocked pending authoritative information |
| Compensation sources disagree | Human resolution, no salary modification |
| Currency unsupported | Explicit issue, no invented conversion |
| Effective date inconsistent | Discrepancy surfaced |
| Equivalent setup active | Existing setup returned |
| Equivalent request pending | Existing reference reused |
| Transient tool failure | Shared bounded retry behavior |
| Request created then response times out | Reconciliation and exactly one setup request |
| Outcome remains uncertain | Uncertainty preserved and review requested |
| Corrected bank details supplied | Revalidation before submission |
| Duplicate input or invocation | No duplicate setup effect |
| Details change after submission | Human review rather than silent replacement |
| Request accepted but still processing | Pending setup, no false activation claim |
| Invented salary, validation, or success | Unsupported claims rejected |

Reuse shared reliability tests alongside focused payroll scenarios. Verify actual
submission eligibility, effect counts, and agreement between reported status and
the simulated system. Parent orchestration and state mechanics remain open.

## Consequences

Payroll provides meaningful validation and guarded writes within a bounded scope.
Masked references limit unnecessary sensitive data in agent context. Disputes and
post-submission changes require human review. Payment processing and actual payroll
compliance are not provided by this simulation.

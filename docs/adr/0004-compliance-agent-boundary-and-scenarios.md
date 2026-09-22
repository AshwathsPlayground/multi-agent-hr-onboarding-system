# ADR-0004: Compliance agent boundary and scenarios

- Status: Accepted
- Date: 2026-09-22
- Basis: User approval of the Compliance agent proposal

## Context

Onboarding requirements must be established and verified before dependent actions
proceed. The assignment uses fictional company policies and structured simulated
evidence; it does not implement real legal compliance.

## Decision

### Responsibility and boundary

Compliance owns applicable documents, background checks, and security training.
It may open simulated compliance cases and inspect their status. It cannot invent
clearance, waive requirements, or accept an unsupported employee assertion as
verified completion. IT enforces the resulting prerequisites before provisioning.

Adverse or review-required check results go to human review, not an automated
employment decision. Waivers and overrides are deferred. Human input can correct
facts or supply authoritative evidence, but cannot silently bypass policy.

### Inputs and outputs

Inputs include validated employee role/location, company and compliance policy,
existing cases, completion evidence, and new documents or status updates.

Return applicable requirements with policy references, per-requirement statuses,
evidence references, verified prerequisites, missing evidence, blockers, and review
requests. Avoid a blanket compliant flag: different requirements may independently
block different actions according to policy.

### Tools and enforcement

Use `get_compliance_requirements()`, `get_company_policy()`,
`create_compliance_case()`, and `get_task_status()`. Add
`get_compliance_evidence()` for structured evidence and `get_operation_status()`
for uncertain case creation. Exact signatures remain open.

Fixtures or controlled updates change simulated evidence. The agent cannot mark
training complete merely to unblock onboarding. Model reasoning interprets retrieved
policy, identifies requirements, and explains missing evidence. Code validates
requirement IDs, checks structured evidence against explicit rules, preserves
provenance, and rejects unsupported clearance. Contradictory or ambiguous policies
produce review requests. OCR and document-forensics features are out of scope.

### Required scenario coverage

| Scenario | Expected evidence |
| --- | --- |
| All required evidence valid | Requirements satisfied with evidence references |
| Required document missing | Targeted information request |
| Optional document absent | No unnecessary blocker |
| Training incomplete | Relevant prerequisite remains unsatisfied |
| Training completion verified | Only the matching requirement cleared |
| Wrong employee or course evidence | Rejected as irrelevant |
| Evidence expired under fixture policy | Renewal required with explicit reason |
| Background check pending | Pending without a clearance claim |
| Adverse/review-required check result | Human review, no automatic employment decision |
| Policy sources conflict | Conflict surfaced; affected determinations blocked |
| Equivalent case already exists | Existing case reused |
| Case creation succeeds then times out | Reconciliation without duplication |
| Transient evidence/status failure | Bounded retries; unavailable is not a negative result |
| Duplicate completion update | No duplicate case or repeated completion effect |
| Model claims unsupported clearance | Validation rejects the claim |
| Mixed satisfied/pending requirements | Partial progress and specific blockers preserved |

Reuse common reliability tests and add focused evidence/policy scenarios. Assert
structured outcomes, evidence provenance, and simulated effects rather than exact
wording. Detailed orchestration and state ownership are separate decisions.

## Consequences

Other agents receive evidence-backed prerequisites rather than model assertions.
Structured policy and evidence fixtures keep the simulation testable and bounded.
Human review remains necessary for ambiguity and adverse results; automated waivers,
employment decisions, and real-world compliance assurances are not provided.

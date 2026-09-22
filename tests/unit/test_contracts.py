from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from zensible.domain.contracts import (
    AgentContext,
    AgentName,
    ComplianceAssessment,
    ComplianceRequirement,
    ComplianceRequirementStatus,
    DeliveryResult,
    DeliveryStatus,
    Finding,
    OnboardingRequest,
    OnboardingStatus,
    OperationRecord,
    OperationStatus,
    PayrollAssessment,
    ProvisioningAssessment,
    ProvisioningItem,
    RequirementCode,
    ResumeEvent,
    ResumeEventKind,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
    TaskRecord,
    TaskStatus,
    ValidatedEmployeeFacts,
)


def john_request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_123",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


def validated_facts() -> ValidatedEmployeeFacts:
    return ValidatedEmployeeFacts(
        employee_id="emp_123",
        name="John Smith",
        role="Engineering Manager",
        location="Bangalore",
        joining_date=date(2026, 10, 1),
    )


def test_onboarding_request_is_typed_and_json_serializable() -> None:
    request = john_request()

    assert request.requested_joining_date == date(2026, 10, 1)
    assert request.model_dump(mode="json") == {
        "onboarding_id": "onb_123",
        "employee_reference": "John Smith",
        "requested_role": "Engineering Manager",
        "requested_location": "Bangalore",
        "requested_joining_date": "2026-10-01",
        "requested_by": "hr_user_42",
    }


def test_contracts_reject_invalid_revisions_and_empty_identifiers() -> None:
    with pytest.raises(ValidationError):
        AgentContext(
            onboarding_id="",
            state_revision=-1,
            facts_version=0,
            policy_version="2026-09",
        )

    with pytest.raises(ValidationError):
        TaskProposal(
            task_id="task_1",
            owner_agent=AgentName.IT,
            intent=TaskIntent.SUBMIT_IT_REQUEST,
            goal="submit laptop request",
            source_revision=-1,
        )


def test_task_proposal_becomes_a_record_without_losing_dependencies() -> None:
    proposal = TaskProposal(
        task_id="task_aws",
        owner_agent=AgentName.IT,
        intent=TaskIntent.SUBMIT_IT_REQUEST,
        goal="submit AWS access request",
        source_revision=3,
        depends_on=["task_training"],
        required_requirements=[RequirementCode.SECURITY_TRAINING_VERIFIED],
        required_evidence=["evidence_training_1"],
        operation_key="onb_123:task_aws:submit_it_request:3",
    )
    record = TaskRecord(**proposal.model_dump(), status=TaskStatus.BLOCKED)

    assert record.status is TaskStatus.BLOCKED
    assert record.depends_on == ["task_training"]
    assert record.required_requirements == [RequirementCode.SECURITY_TRAINING_VERIFIED]
    assert record.model_dump(mode="json")["status"] == "blocked"


def test_operation_record_preserves_idempotency_identity_and_unknown_outcome() -> None:
    operation = OperationRecord(
        operation_key="onb_123:task_payroll:submit_payroll_setup:2",
        task_id="task_payroll",
        operation_type="submit_payroll_setup",
        request_fingerprint="sha256:abc",
        status=OperationStatus.UNKNOWN,
        attempts=1,
        last_error="response timed out after submission",
    )

    serialized = operation.model_dump(mode="json")
    assert serialized["status"] == "unknown"
    assert serialized["operation_key"].endswith(":2")
    assert serialized["attempts"] == 1


def test_resume_event_accepts_json_payload_and_serializes_datetime() -> None:
    event = ResumeEvent(
        kind=ResumeEventKind.BANK_DETAILS_SUBMITTED,
        payload={"bank_details_reference": "bank_ref_123"},
        source="hr_user_42",
        submitted_at=datetime(2026, 9, 22, 10, 30, tzinfo=UTC),
    )

    assert event.model_dump(mode="json")["kind"] == "bank_details_submitted"
    assert event.model_dump(mode="json")["submitted_at"] == "2026-09-22T10:30:00Z"


def test_specialist_result_has_shared_routing_fields_and_typed_payload() -> None:
    result = SpecialistResult[ValidatedEmployeeFacts](
        agent=AgentName.HR,
        phase=SpecialistPhase.ASSESSMENT,
        outcome=SpecialistOutcome.COMPLETED,
        state_revision=1,
        payload=validated_facts(),
        findings=[Finding(code="facts_validated", message="HR facts are complete")],
    )

    assert result.payload is not None
    assert result.payload.employee_id == "emp_123"
    assert result.model_dump(mode="json")["agent"] == "hr"
    assert result.model_dump(mode="json")["phase"] == "assessment"


def test_agent_context_contains_compact_checkpointable_state() -> None:
    context = AgentContext(
        onboarding_id="onb_123",
        state_revision=4,
        facts_version=2,
        policy_version="2026-09",
        validated_hr_facts=validated_facts(),
        relevant_findings={
            "compliance": [Finding(code="training_pending", message="Training pending")]
        },
    )

    dumped = context.model_dump(mode="json")
    assert dumped["state_revision"] == 4
    assert dumped["validated_hr_facts"]["employee_id"] == "emp_123"
    assert dumped["relevant_findings"]["compliance"][0]["code"] == "training_pending"


def test_specialist_payloads_cover_each_domain_boundary() -> None:
    compliance = ComplianceAssessment(
        requirements=[
            ComplianceRequirement(
                code=RequirementCode.SECURITY_TRAINING_VERIFIED,
                status=ComplianceRequirementStatus.PENDING,
                evidence_references=[],
            )
        ]
    )
    provisioning = ProvisioningAssessment(
        items=[
            ProvisioningItem(
                resource="aws",
                status=TaskStatus.BLOCKED,
                required_requirements=[RequirementCode.SECURITY_TRAINING_VERIFIED],
            )
        ]
    )
    payroll = PayrollAssessment(
        compensation_reference="comp_123",
        bank_details_reference=None,
        salary=Decimal("150000.00"),
        currency="INR",
        eligible=False,
    )
    delivery = DeliveryResult(
        status=DeliveryStatus.DELIVERED,
        recipient_references=["employee:emp_123"],
        notification_reference="notification_123",
    )

    assert compliance.requirements[0].status is ComplianceRequirementStatus.PENDING
    assert provisioning.items[0].status is TaskStatus.BLOCKED
    assert payroll.model_dump(mode="json")["salary"] == "150000.00"
    assert delivery.status is DeliveryStatus.DELIVERED


def test_status_and_outcome_values_are_stable_wire_values() -> None:
    assert OnboardingStatus.WAITING_FOR_INPUT.value == "waiting_for_input"
    assert SpecialistOutcome.REQUIRES_REASSESSMENT.value == "requires_reassessment"
    assert OperationStatus.NEEDS_RESOLUTION.value == "needs_resolution"
    assert DeliveryStatus.UNKNOWN.value == "unknown"

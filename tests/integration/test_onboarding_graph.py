import asyncio
from datetime import UTC, date, datetime

import pytest

from zensible.domain.contracts import (
    OnboardingRequest,
    OnboardingStatus,
    OperationStatus,
    ResumeEvent,
    ResumeEventKind,
    TaskStatus,
)
from zensible.orchestration.graph import build_onboarding_graph
from zensible.simulation import FailureMode, SimulatedCompany
from zensible.tools import OperationExecutor

pytestmark = pytest.mark.assignment


def john_request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_123",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


def test_first_run_completes_independent_work_and_waits_for_inputs() -> None:
    company = SimulatedCompany()
    executor = OperationExecutor(company)
    graph = build_onboarding_graph(executor=executor)

    state = asyncio.run(graph.ainvoke({"request": john_request()}))

    assert state["status"] is OnboardingStatus.WAITING_FOR_INPUT
    assert state["context"].validated_hr_facts is not None
    assert company.effect_count("submit_it_request") == 1
    assert company.effect_count("create_compliance_case") == 1
    assert company.effect_count("submit_payroll_setup") == 0
    assert any(
        task.status is TaskStatus.BLOCKED and task.intent.value == "submit_it_request"
        for task in state["tasks"]
    )
    assert any(error.code == "missing_input" for error in state["errors"])


def test_resume_event_unlocks_payroll_and_aws_without_repeating_effects() -> None:
    company = SimulatedCompany()
    executor = OperationExecutor(company)
    graph = build_onboarding_graph(executor=executor)

    first = asyncio.run(graph.ainvoke({"request": john_request()}))
    resume_event = ResumeEvent(
        kind=ResumeEventKind.TRAINING_EVIDENCE_SUBMITTED,
        payload={
            "status": "verified",
            "bank_details_reference": "bank_ref_123",
        },
        source="hr_user_42",
        submitted_at=datetime(2026, 9, 22, 10, 30, tzinfo=UTC),
    )
    second = asyncio.run(
        graph.ainvoke(
            {
                "request": john_request(),
                "context": first["context"],
                "tasks": first["tasks"],
                "operations": first["operations"],
                "resume_event": resume_event,
            }
        )
    )

    assert second["status"] is OnboardingStatus.COMPLETE
    assert company.effect_count("submit_it_request") == 2
    assert company.effect_count("create_compliance_case") == 1
    assert company.effect_count("submit_payroll_setup") == 1
    assert all(
        operation.status is OperationStatus.SUCCEEDED
        for operation in second["operations"]
    )


def test_unresolved_employee_routes_to_resolution_without_actions() -> None:
    request = john_request().model_copy(
        update={"employee_reference": "Ambiguous Person"}
    )
    graph = build_onboarding_graph()

    state = asyncio.run(graph.ainvoke({"request": request}))

    assert state["status"] is OnboardingStatus.NEEDS_RESOLUTION
    assert all(
        operation.operation_type == "deliver_notification"
        for operation in state["operations"]
    )
    assert state["context"].validated_hr_facts is None


def test_missing_employee_input_does_not_look_complete() -> None:
    request = john_request().model_copy(update={"employee_reference": "Unknown Person"})
    graph = build_onboarding_graph()

    state = asyncio.run(graph.ainvoke({"request": request}))

    assert state["status"] is OnboardingStatus.WAITING_FOR_INPUT
    assert state["operations"]
    assert state["context"].validated_hr_facts is None


def test_notification_status_reflects_delivery_failure() -> None:
    company = SimulatedCompany()
    company.set_failure("deliver_notification", FailureMode.FAILURE)
    graph = build_onboarding_graph(executor=OperationExecutor(company))

    state = asyncio.run(graph.ainvoke({"request": john_request()}))

    assert state["notifications"][0].payload.status.value == "failed"

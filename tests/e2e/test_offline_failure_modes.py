import asyncio
from datetime import UTC, date, datetime

from zensible.domain.contracts import (
    OnboardingRequest,
    OnboardingStatus,
    ResumeEvent,
    ResumeEventKind,
    TaskStatus,
)
from zensible.orchestration.graph import build_onboarding_graph
from zensible.simulation import FailureMode, SimulatedCompany
from zensible.tools import OperationExecutor


def request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_failure_e2e",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


def test_action_failure_is_visible_in_parent_graph_status() -> None:
    company = SimulatedCompany()
    company.set_failure("submit_it_request", FailureMode.FAILURE)
    graph = build_onboarding_graph(executor=OperationExecutor(company))

    state = asyncio.run(graph.ainvoke({"request": request()}))

    assert state["status"] is OnboardingStatus.BLOCKED_BY_FAILURE
    assert any(task.status is TaskStatus.FAILED for task in state["tasks"])
    assert company.effect_count("create_compliance_case") == 1


def test_unknown_after_effect_is_reconciled_on_resume_without_duplicate_effect() -> (
    None
):
    company = SimulatedCompany()
    executor = OperationExecutor(company)
    graph = build_onboarding_graph(executor=executor)

    first = asyncio.run(graph.ainvoke({"request": request()}))
    company.set_failure("submit_payroll_setup", FailureMode.UNKNOWN_AFTER_EFFECT)
    event = ResumeEvent(
        kind=ResumeEventKind.TRAINING_EVIDENCE_SUBMITTED,
        payload={"status": "verified", "bank_details_reference": "bank_ref_123"},
        source="hr_user_42",
        submitted_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    uncertain = asyncio.run(
        graph.ainvoke(
            {
                "request": request(),
                "context": first["context"],
                "tasks": first["tasks"],
                "operations": first["operations"],
                "resume_event": event,
            }
        )
    )
    reconciled = asyncio.run(
        graph.ainvoke(
            {
                "request": request(),
                "context": uncertain["context"],
                "tasks": uncertain["tasks"],
                "operations": uncertain["operations"],
                "resume_event": event,
            }
        )
    )

    assert uncertain["status"] is OnboardingStatus.WAITING_FOR_EXTERNAL_EVENT
    assert reconciled["status"] is OnboardingStatus.COMPLETE
    assert company.effect_count("submit_payroll_setup") == 1

from datetime import UTC, date, datetime

import pytest

from zensible.agents import communication, compliance, hr, it, payroll
from zensible.domain.contracts import (
    AgentContext,
    AgentName,
    DeliveryStatus,
    OnboardingRequest,
    ResumeEvent,
    ResumeEventKind,
    SpecialistOutcome,
    TaskIntent,
)
from zensible.modeling import ScriptedStructuredAgentModel


def model_for(*agents: AgentName) -> ScriptedStructuredAgentModel:
    return ScriptedStructuredAgentModel(
        {
            agent.value: {
                "summary": f"{agent.value} model response",
                "recommendation": "continue",
                "confidence": 0.9,
                "evidence": [f"{agent.value} fixture"],
            }
            for agent in agents
        }
    )


def request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_agent_test",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


def context(*, resume_event: ResumeEvent | None = None) -> AgentContext:
    return AgentContext(
        onboarding_id="onb_agent_test",
        state_revision=1 if resume_event else 0,
        facts_version=0,
        policy_version="2026-09",
        resume_event=resume_event,
    )


@pytest.mark.asyncio
async def test_hr_agent_returns_domain_result_and_model_output() -> None:
    graph = hr.build_graph(model_for(AgentName.HR))

    state = await graph.ainvoke({"request": request(), "context": context()})

    result = state["result"]
    assert result.outcome is SpecialistOutcome.COMPLETED
    assert result.payload is not None
    assert result.model_output.summary == "hr model response"


@pytest.mark.asyncio
async def test_hr_agent_preserves_ambiguity_as_resolution() -> None:
    graph = hr.build_graph(model_for(AgentName.HR))
    ambiguous = request().model_copy(update={"employee_reference": "Ambiguous Person"})

    result = (await graph.ainvoke({"request": ambiguous, "context": context()}))[
        "result"
    ]

    assert result.outcome is SpecialistOutcome.NEEDS_RESOLUTION
    assert result.conflicts
    assert result.model_output is not None


@pytest.mark.asyncio
async def test_it_agent_proposes_gated_and_independent_work() -> None:
    graph = it.build_graph(model_for(AgentName.IT))

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.model_output is not None
    assert {task.intent for task in result.proposed_tasks} == {
        TaskIntent.SUBMIT_IT_REQUEST
    }
    assert any(task.required_requirements for task in result.proposed_tasks)


@pytest.mark.asyncio
async def test_compliance_agent_reports_training_pending() -> None:
    graph = compliance.build_graph(model_for(AgentName.COMPLIANCE))

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.payload is not None
    assert result.payload.requirements[0].status.value == "pending"
    assert result.model_output is not None


@pytest.mark.asyncio
async def test_payroll_agent_requests_missing_bank_details() -> None:
    graph = payroll.build_graph(model_for(AgentName.PAYROLL))

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.missing_inputs[0].field == "bank_details_reference"
    assert result.proposed_tasks == []
    assert result.model_output is not None


@pytest.mark.asyncio
async def test_payroll_agent_proposes_setup_after_bank_details() -> None:
    event = ResumeEvent(
        kind=ResumeEventKind.BANK_DETAILS_SUBMITTED,
        payload={"bank_details_reference": "bank_ref_123"},
        source="employee:emp_123",
        submitted_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    graph = payroll.build_graph(model_for(AgentName.PAYROLL))

    result = (await graph.ainvoke({"context": context(resume_event=event)}))["result"]

    assert result.payload.eligible is True
    assert result.proposed_tasks[0].intent is TaskIntent.SUBMIT_PAYROLL_SETUP


@pytest.mark.asyncio
async def test_communication_agent_returns_pending_delivery() -> None:
    graph = communication.build_graph(model_for(AgentName.COMMUNICATION))

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.payload.status is DeliveryStatus.PENDING
    assert result.payload.recipient_references
    assert result.model_output is not None

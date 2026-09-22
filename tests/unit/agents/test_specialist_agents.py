from datetime import UTC, date, datetime

import pytest

from zensible.agents import communication, compliance, hr, it, payroll
from zensible.domain.contracts import (
    AgentContext,
    AgentDecision,
    AgentName,
    DeliveryStatus,
    MissingInput,
    ModelAssessment,
    OnboardingRequest,
    ResumeEvent,
    ResumeEventKind,
    SpecialistOutcome,
    TaskIntent,
    TaskRecord,
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


async def payroll_result(
    resume_event: ResumeEvent | None = None,
):
    graph = payroll.build_graph(model_for(AgentName.PAYROLL))
    return (await graph.ainvoke({"context": context(resume_event=resume_event)}))[
        "result"
    ]


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
async def test_it_agent_uses_model_task_selection_within_policy_candidates() -> None:
    model = ScriptedStructuredAgentModel(
        {
            AgentName.IT.value: ModelAssessment(
                summary="laptop is ready to request",
                recommendation="request the laptop only",
                confidence=0.95,
                decision=AgentDecision.PROCEED,
                approved_task_ids=["onb_agent_test:it:laptop"],
            )
        }
    )
    graph = it.build_graph(model)

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert [task.task_id for task in result.proposed_tasks] == [
        "onb_agent_test:it:laptop"
    ]


@pytest.mark.asyncio
async def test_payroll_model_request_for_input_suppresses_ready_task() -> None:
    resume_event = ResumeEvent(
        kind=ResumeEventKind.BANK_DETAILS_SUBMITTED,
        payload={"bank_details_reference": "bank_ref_123"},
        source="employee:emp_123",
        submitted_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    model = ScriptedStructuredAgentModel(
        {
            AgentName.PAYROLL.value: ModelAssessment(
                summary="payroll needs one more verification",
                recommendation="request payroll confirmation",
                confidence=0.9,
                decision=AgentDecision.REQUEST_INPUT,
                requested_inputs=[
                    MissingInput(
                        field="payroll_confirmation",
                        reason="Payroll confirmation is required",
                        requested_from="payroll",
                    )
                ],
            )
        }
    )
    graph = payroll.build_graph(model)

    result = (await graph.ainvoke({"context": context(resume_event=resume_event)}))[
        "result"
    ]

    assert result.outcome is SpecialistOutcome.NEEDS_INPUT
    assert result.proposed_tasks == []
    assert result.missing_inputs[0].field == "payroll_confirmation"


@pytest.mark.asyncio
async def test_model_request_for_input_preserves_approved_independent_task() -> None:
    model = ScriptedStructuredAgentModel(
        {
            AgentName.IT.value: ModelAssessment(
                summary="laptop is safe, AWS needs training evidence",
                recommendation="request the laptop and verify training before AWS",
                confidence=0.95,
                decision=AgentDecision.REQUEST_INPUT,
                approved_task_ids=["onb_agent_test:it:laptop"],
                requested_inputs=[
                    MissingInput(
                        field="security_training_verified",
                        reason="AWS access requires verified training",
                        requested_from="it",
                    )
                ],
            )
        }
    )
    graph = it.build_graph(model)

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.proposed_tasks[0].task_id == "onb_agent_test:it:laptop"
    assert [task.task_id for task in result.deferred_tasks] == ["onb_agent_test:it:aws"]
    assert result.outcome is SpecialistOutcome.NEEDS_INPUT
    assert result.missing_inputs[0].field == "security_training_verified"


@pytest.mark.asyncio
async def test_invalid_model_task_selection_is_rejected_before_planning() -> None:
    model = ScriptedStructuredAgentModel(
        {
            AgentName.IT.value: ModelAssessment(
                summary="invalid selection",
                recommendation="request an unsupported resource",
                confidence=0.7,
                approved_task_ids=["onb_agent_test:it:forged"],
            )
        }
    )
    graph = it.build_graph(model)

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.outcome is SpecialistOutcome.NEEDS_RESOLUTION
    assert result.proposed_tasks == []
    assert result.errors[0].code == "invalid_model_output"


@pytest.mark.asyncio
async def test_compliance_agent_reports_training_pending() -> None:
    graph = compliance.build_graph(model_for(AgentName.COMPLIANCE))

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.payload is not None
    assert result.payload.requirements[0].status.value == "pending"
    assert result.model_output is not None


@pytest.mark.asyncio
async def test_compliance_agent_does_not_reopen_succeeded_case() -> None:
    existing_context = context().model_copy(
        update={
            "existing_tasks": [
                TaskRecord(
                    task_id="onb_agent_test:compliance:case",
                    owner_agent=AgentName.COMPLIANCE,
                    intent=TaskIntent.CREATE_COMPLIANCE_CASE,
                    goal="open the compliance onboarding case",
                    source_revision=0,
                    status="succeeded",
                )
            ]
        }
    )
    graph = compliance.build_graph(model_for(AgentName.COMPLIANCE))

    result = (await graph.ainvoke({"context": existing_context}))["result"]

    assert result.proposed_tasks == []


@pytest.mark.parametrize(
    ("resume_event", "eligible", "has_missing_input", "has_task"),
    [
        (None, False, True, False),
        (
            ResumeEvent(
                kind=ResumeEventKind.BANK_DETAILS_SUBMITTED,
                payload={"bank_details_reference": "bank_ref_123"},
                source="employee:emp_123",
                submitted_at=datetime(2026, 9, 22, tzinfo=UTC),
            ),
            True,
            False,
            True,
        ),
        (
            ResumeEvent(
                kind=ResumeEventKind.BANK_DETAILS_SUBMITTED,
                payload={"bank_details_reference": ""},
                source="employee:emp_123",
                submitted_at=datetime(2026, 9, 22, tzinfo=UTC),
            ),
            False,
            True,
            False,
        ),
    ],
)
@pytest.mark.asyncio
async def test_payroll_agent_handles_bank_detail_variants(
    resume_event: ResumeEvent | None,
    eligible: bool,
    has_missing_input: bool,
    has_task: bool,
) -> None:
    result = await payroll_result(resume_event)

    assert result.payload.eligible is eligible
    assert bool(result.missing_inputs) is has_missing_input
    assert bool(result.proposed_tasks) is has_task
    assert result.model_output is not None


@pytest.mark.asyncio
async def test_communication_agent_returns_pending_delivery() -> None:
    graph = communication.build_graph(model_for(AgentName.COMMUNICATION))

    result = (await graph.ainvoke({"context": context()}))["result"]

    assert result.payload.status is DeliveryStatus.PENDING
    assert result.payload.recipient_references
    assert result.model_output is not None

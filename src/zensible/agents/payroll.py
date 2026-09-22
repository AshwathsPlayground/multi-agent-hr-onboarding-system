"""Payroll setup assessment specialist."""

from langgraph.graph import END, StateGraph

from zensible.agents.runtime import model_assessment, record_result
from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    MissingInput,
    PayrollAssessment,
    ResumeEventKind,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
)
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink, trace_operation


@trace_operation("payroll.assess", tags=("onboarding", "payroll"))
async def assess(
    context,
    *,
    state_revision: int,
    model: StructuredAgentModel | None = None,
) -> SpecialistResult[PayrollAssessment]:
    model_output = await model_assessment(
        model,
        agent=AgentName.PAYROLL,
        context=context.model_dump(mode="json"),
    )
    bank_reference = None
    if (
        context.resume_event is not None
        and context.resume_event.kind is ResumeEventKind.BANK_DETAILS_SUBMITTED
    ):
        bank_reference = context.resume_event.payload.get("bank_details_reference")
    if context.resume_event is not None and context.resume_event.payload.get(
        "bank_details_reference"
    ):
        bank_reference = context.resume_event.payload["bank_details_reference"]

    eligible = isinstance(bank_reference, str) and bool(bank_reference)
    assessment = PayrollAssessment(
        compensation_reference="comp_123",
        bank_details_reference=bank_reference
        if isinstance(bank_reference, str)
        else None,
        salary="150000.00",
        currency="INR",
        pay_schedule="monthly",
        effective_date=context.resume_event.submitted_at.date()
        if context.resume_event is not None
        else None,
        eligible=eligible,
    )
    missing_inputs = (
        []
        if eligible
        else [
            MissingInput(
                field="bank_details_reference",
                reason="Verified bank details are required before payroll setup",
                requested_from="employee",
            )
        ]
    )
    proposed_tasks = (
        []
        if not eligible
        else [
            TaskProposal(
                task_id=f"{context.onboarding_id}:payroll:setup",
                owner_agent=AgentName.PAYROLL,
                intent=TaskIntent.SUBMIT_PAYROLL_SETUP,
                goal="submit payroll setup request",
                source_revision=state_revision,
                required_requirements=[],
                operation_key=f"{context.onboarding_id}:payroll:setup",
            )
        ]
    )
    return SpecialistResult(
        agent=AgentName.PAYROLL,
        phase=SpecialistPhase.ASSESSMENT,
        outcome=SpecialistOutcome.COMPLETED,
        state_revision=state_revision,
        payload=assessment,
        missing_inputs=missing_inputs,
        proposed_tasks=proposed_tasks,
        model_output=model_output,
    )


def build_graph(
    model: StructuredAgentModel | None = None,
    *,
    events: EventSink | None = None,
):
    workflow = StateGraph(SpecialistState)

    async def assess_node(state: SpecialistState) -> dict[str, object]:
        result = await assess(
            state["context"],
            state_revision=state["context"].state_revision,
            model=model,
        )
        return {"result": record_result(events, result)}

    workflow.add_node("assess", assess_node)
    workflow.add_edge("assess", END)
    workflow.set_entry_point("assess")
    return workflow.compile()

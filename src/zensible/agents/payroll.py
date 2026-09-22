"""Payroll setup assessment specialist."""

from langgraph.graph import END, StateGraph

from zensible.agents.runtime import (
    apply_model_guidance,
    model_assessment,
    record_result,
)
from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    MissingInput,
    PayrollAssessment,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
)
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink, trace_operation


def _bank_reference(context) -> str | None:
    event = context.resume_event
    if event is None:
        return None
    reference = event.payload.get("bank_details_reference")
    return reference if isinstance(reference, str) and reference else None


def _assessment(context, bank_reference: str | None) -> PayrollAssessment:
    return PayrollAssessment(
        compensation_reference="comp_123",
        bank_details_reference=bank_reference,
        salary="150000.00",
        currency="INR",
        pay_schedule="monthly",
        effective_date=(
            context.resume_event.submitted_at.date()
            if context.resume_event is not None
            else None
        ),
        eligible=bank_reference is not None,
    )


def _missing_inputs(eligible: bool) -> list[MissingInput]:
    if eligible:
        return []
    return [
        MissingInput(
            field="bank_details_reference",
            reason="Verified bank details are required before payroll setup",
            requested_from="employee",
        )
    ]


def _proposed_tasks(context, state_revision: int, eligible: bool) -> list[TaskProposal]:
    if not eligible:
        return []
    return [
        TaskProposal(
            task_id=f"{context.onboarding_id}:payroll:setup",
            owner_agent=AgentName.PAYROLL,
            intent=TaskIntent.SUBMIT_PAYROLL_SETUP,
            goal="submit payroll setup request",
            source_revision=state_revision,
            operation_key=f"{context.onboarding_id}:payroll:setup",
        )
    ]


@trace_operation("payroll.assess", tags=("onboarding", "payroll"))
async def assess(
    context,
    *,
    state_revision: int,
    model: StructuredAgentModel | None = None,
) -> SpecialistResult[PayrollAssessment]:
    bank_reference = _bank_reference(context)
    eligible = bank_reference is not None
    task_id = f"{context.onboarding_id}:payroll:setup"
    payroll_assessment = _assessment(context, bank_reference)
    deterministic_missing_inputs = _missing_inputs(eligible)
    model_context = context.model_dump(mode="json")
    model_context["deterministic_payroll_assessment"] = payroll_assessment.model_dump(
        mode="json"
    )
    model_context["deterministic_missing_inputs"] = [
        item.model_dump(mode="json") for item in deterministic_missing_inputs
    ]
    model_context["candidate_task"] = {
        "task_id": task_id,
        "goal": "submit payroll setup request",
    }
    model_output = await model_assessment(
        model,
        agent=AgentName.PAYROLL,
        context=model_context,
        candidate_task_ids=[task_id],
    )
    return apply_model_guidance(
        SpecialistResult(
            agent=AgentName.PAYROLL,
            phase=SpecialistPhase.ASSESSMENT,
            outcome=SpecialistOutcome.COMPLETED,
            state_revision=state_revision,
            payload=payroll_assessment,
            missing_inputs=deterministic_missing_inputs,
            proposed_tasks=_proposed_tasks(context, state_revision, eligible),
            model_output=model_output,
        ),
        model_output=model_output,
        candidate_task_ids=[task_id],
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

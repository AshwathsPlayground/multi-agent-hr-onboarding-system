"""HR facts validation specialist."""

from langgraph.graph import END, StateGraph

from zensible.agents.runtime import model_assessment, record_result
from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    Conflict,
    Finding,
    MissingInput,
    OnboardingRequest,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    ValidatedEmployeeFacts,
)
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink, trace_operation


@trace_operation("hr.assess", tags=("onboarding", "hr"))
async def assess(
    request: OnboardingRequest,
    *,
    state_revision: int,
    model: StructuredAgentModel | None = None,
) -> SpecialistResult[ValidatedEmployeeFacts]:
    """Validate the employee fixture without changing HR source data."""

    model_output = await model_assessment(
        model,
        agent=AgentName.HR,
        context=request.model_dump(mode="json"),
    )

    if request.employee_reference.lower() == "john smith":
        facts = ValidatedEmployeeFacts(
            employee_id="emp_123",
            name="John Smith",
            role=request.requested_role,
            location=request.requested_location,
            joining_date=request.requested_joining_date,
            manager_id="mgr_001",
            department="engineering",
            provenance={"employee_id": []},
        )
        return SpecialistResult(
            agent=AgentName.HR,
            phase=SpecialistPhase.ASSESSMENT,
            outcome=SpecialistOutcome.COMPLETED,
            state_revision=state_revision,
            payload=facts,
            findings=[
                Finding(code="hr_facts_validated", message="HR facts are complete")
            ],
            model_output=model_output,
        )

    if "ambiguous" in request.employee_reference.lower():
        return SpecialistResult(
            agent=AgentName.HR,
            phase=SpecialistPhase.ASSESSMENT,
            outcome=SpecialistOutcome.NEEDS_RESOLUTION,
            state_revision=state_revision,
            conflicts=[
                Conflict(
                    field="employee_reference",
                    values={"candidate_1": "emp_123", "candidate_2": "emp_987"},
                )
            ],
            model_output=model_output,
        )

    return SpecialistResult(
        agent=AgentName.HR,
        phase=SpecialistPhase.ASSESSMENT,
        outcome=SpecialistOutcome.NEEDS_INPUT,
        state_revision=state_revision,
        missing_inputs=[
            MissingInput(
                field="employee_reference",
                reason="No employee matched the supplied reference",
                requested_from="hr",
            )
        ],
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
            state["request"],
            state_revision=state["context"].state_revision,
            model=model,
        )
        return {"result": record_result(events, result)}

    workflow.add_node("assess", assess_node)
    workflow.add_edge("assess", END)
    workflow.set_entry_point("assess")
    return workflow.compile()

"""Notification delivery specialist called by the parent graph."""

from langgraph.graph import END, StateGraph

from zensible.agents.runtime import (
    apply_model_guidance,
    model_assessment,
    record_result,
)
from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    DeliveryResult,
    DeliveryStatus,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
)
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink, trace_operation


@trace_operation("communication.assess", tags=("onboarding", "communication"))
async def assess(
    context,
    *,
    state_revision: int,
    model: StructuredAgentModel | None = None,
) -> SpecialistResult[DeliveryResult]:
    model_output = await model_assessment(
        model,
        agent=AgentName.COMMUNICATION,
        context=context.model_dump(mode="json"),
    )
    return apply_model_guidance(
        SpecialistResult(
            agent=AgentName.COMMUNICATION,
            phase=SpecialistPhase.ASSESSMENT,
            outcome=SpecialistOutcome.COMPLETED,
            state_revision=state_revision,
            payload=DeliveryResult(
                status=DeliveryStatus.PENDING,
                recipient_references=[
                    f"hr:{context.onboarding_id}",
                    "employee:emp_123",
                ],
            ),
            model_output=model_output,
        ),
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

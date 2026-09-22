"""Notification delivery specialist called by the parent graph."""

from langgraph.graph import END, StateGraph

from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    DeliveryResult,
    DeliveryStatus,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
)
from zensible.observability import trace_operation


@trace_operation("communication.assess", tags=("onboarding", "communication"))
def assess(context, *, state_revision: int) -> SpecialistResult[DeliveryResult]:
    return SpecialistResult(
        agent=AgentName.COMMUNICATION,
        phase=SpecialistPhase.ASSESSMENT,
        outcome=SpecialistOutcome.COMPLETED,
        state_revision=state_revision,
        payload=DeliveryResult(
            status=DeliveryStatus.PENDING,
            recipient_references=[f"hr:{context.onboarding_id}", "employee:emp_123"],
        ),
    )


def build_graph():
    workflow = StateGraph(SpecialistState)

    def assess_node(state: SpecialistState) -> dict[str, object]:
        return {
            "result": assess(
                state["context"],
                state_revision=state["context"].state_revision,
            )
        }

    workflow.add_node("assess", assess_node)
    workflow.add_edge("assess", END)
    workflow.set_entry_point("assess")
    return workflow.compile()

"""IT provisioning assessment specialist."""

from langgraph.graph import END, StateGraph

from zensible.agents.runtime import model_assessment, record_result
from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    ProvisioningAssessment,
    ProvisioningItem,
    RequirementCode,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
    TaskStatus,
)
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink, trace_operation


@trace_operation("it.assess", tags=("onboarding", "it"))
async def assess(
    context,
    *,
    state_revision: int,
    model: StructuredAgentModel | None = None,
) -> SpecialistResult[ProvisioningAssessment]:
    model_output = await model_assessment(
        model,
        agent=AgentName.IT,
        context=context.model_dump(mode="json"),
    )
    items = [
        ProvisioningItem(resource="laptop"),
        ProvisioningItem(
            resource="aws",
            status=TaskStatus.BLOCKED,
            required_requirements=[RequirementCode.SECURITY_TRAINING_VERIFIED],
        ),
    ]
    proposals = [
        TaskProposal(
            task_id=f"{context.onboarding_id}:it:laptop",
            owner_agent=AgentName.IT,
            intent=TaskIntent.SUBMIT_IT_REQUEST,
            goal="submit laptop provisioning request",
            source_revision=state_revision,
            operation_key=f"{context.onboarding_id}:it:laptop",
        ),
        TaskProposal(
            task_id=f"{context.onboarding_id}:it:aws",
            owner_agent=AgentName.IT,
            intent=TaskIntent.SUBMIT_IT_REQUEST,
            goal="submit AWS access request",
            source_revision=state_revision,
            required_requirements=[RequirementCode.SECURITY_TRAINING_VERIFIED],
            operation_key=f"{context.onboarding_id}:it:aws",
        ),
    ]
    return SpecialistResult(
        agent=AgentName.IT,
        phase=SpecialistPhase.ASSESSMENT,
        outcome=SpecialistOutcome.COMPLETED,
        state_revision=state_revision,
        payload=ProvisioningAssessment(items=items),
        proposed_tasks=proposals,
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

"""IT provisioning assessment specialist."""

from langgraph.graph import END, StateGraph

from zensible.agents.runtime import (
    apply_model_guidance,
    model_assessment,
    record_result,
)
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
    laptop_task_id = f"{context.onboarding_id}:it:laptop"
    aws_task_id = f"{context.onboarding_id}:it:aws"
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
            task_id=laptop_task_id,
            owner_agent=AgentName.IT,
            intent=TaskIntent.SUBMIT_IT_REQUEST,
            goal="submit laptop provisioning request",
            source_revision=state_revision,
            operation_key=f"{context.onboarding_id}:it:laptop",
        ),
        TaskProposal(
            task_id=aws_task_id,
            owner_agent=AgentName.IT,
            intent=TaskIntent.SUBMIT_IT_REQUEST,
            goal="submit AWS access request",
            source_revision=state_revision,
            required_requirements=[RequirementCode.SECURITY_TRAINING_VERIFIED],
            operation_key=f"{context.onboarding_id}:it:aws",
        ),
    ]
    model_context = context.model_dump(mode="json")
    model_context["deterministic_provisioning_assessment"] = {
        "items": [item.model_dump(mode="json") for item in items],
        "candidate_tasks": [task.model_dump(mode="json") for task in proposals],
    }
    model_output = await model_assessment(
        model,
        agent=AgentName.IT,
        context=model_context,
        candidate_task_ids=[laptop_task_id, aws_task_id],
    )
    return apply_model_guidance(
        SpecialistResult(
            agent=AgentName.IT,
            phase=SpecialistPhase.ASSESSMENT,
            outcome=SpecialistOutcome.COMPLETED,
            state_revision=state_revision,
            payload=ProvisioningAssessment(items=items),
            proposed_tasks=proposals,
            model_output=model_output,
        ),
        model_output=model_output,
        candidate_task_ids=[laptop_task_id, aws_task_id],
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

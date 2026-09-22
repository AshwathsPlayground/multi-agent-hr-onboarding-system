"""Compliance assessment specialist."""

from langgraph.graph import END, StateGraph

from zensible.agents.state import SpecialistState
from zensible.domain.contracts import (
    AgentName,
    ComplianceAssessment,
    ComplianceRequirement,
    ComplianceRequirementStatus,
    RequirementCode,
    ResumeEventKind,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
    TaskStatus,
)
from zensible.observability import trace_operation


@trace_operation("compliance.assess", tags=("onboarding", "compliance"))
def assess(context, *, state_revision: int) -> SpecialistResult[ComplianceAssessment]:
    training_verified = (
        context.resume_event is not None
        and context.resume_event.kind is ResumeEventKind.TRAINING_EVIDENCE_SUBMITTED
        and context.resume_event.payload.get("status") == "verified"
    )
    requirement = ComplianceRequirement(
        code=RequirementCode.SECURITY_TRAINING_VERIFIED,
        status=(
            ComplianceRequirementStatus.VERIFIED
            if training_verified
            else ComplianceRequirementStatus.PENDING
        ),
        evidence_references=["training_evidence_123"] if training_verified else [],
    )
    case_exists = any(
        task.intent is TaskIntent.CREATE_COMPLIANCE_CASE
        and task.status is TaskStatus.SUCCEEDED
        for task in context.existing_tasks
    )
    proposed_tasks = (
        []
        if case_exists
        else [
            TaskProposal(
                task_id=f"{context.onboarding_id}:compliance:case",
                owner_agent=AgentName.COMPLIANCE,
                intent=TaskIntent.CREATE_COMPLIANCE_CASE,
                goal="open the compliance onboarding case",
                source_revision=state_revision,
            )
        ]
    )
    return SpecialistResult(
        agent=AgentName.COMPLIANCE,
        phase=SpecialistPhase.ASSESSMENT,
        outcome=SpecialistOutcome.COMPLETED,
        state_revision=state_revision,
        payload=ComplianceAssessment(requirements=[requirement]),
        proposed_tasks=proposed_tasks,
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

"""Parent LangGraph for deterministic, production-shaped onboarding runs."""

import asyncio
from typing import Any

from langgraph.graph import END, StateGraph

from zensible.agents import communication, compliance, hr, it, payroll
from zensible.domain.contracts import (
    AgentContext,
    AgentName,
    ComplianceAssessment,
    ComplianceRequirementStatus,
    DeliveryStatus,
    ErrorDetail,
    OnboardingStatus,
    OperationStatus,
    RequirementCode,
    SpecialistOutcome,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
    TaskRecord,
    TaskStatus,
)
from zensible.orchestration.state import OnboardingState
from zensible.orchestration.validation import validate_task_proposals
from zensible.simulation import SimulatedCompany
from zensible.tools import OperationExecutor, OperationRequest


def _context_for(state: OnboardingState) -> AgentContext:
    request = state["request"]
    previous = state.get("context")
    event = state.get("resume_event")
    if previous is None:
        return AgentContext(
            onboarding_id=request.onboarding_id,
            state_revision=0,
            facts_version=0,
            policy_version="2026-09",
            resume_event=event,
        )
    return previous.model_copy(
        update={
            "state_revision": previous.state_revision + (1 if event else 0),
            "resume_event": event,
            "existing_tasks": state.get("tasks", previous.existing_tasks),
            "existing_operations": state.get(
                "operations", previous.existing_operations
            ),
        }
    )


def _prepare(state: OnboardingState) -> dict[str, Any]:
    return {
        "context": _context_for(state),
        "assessment_results": {},
        "errors": [],
        "notifications": [],
    }


async def _run_hr(state: OnboardingState, graph) -> dict[str, Any]:
    result = (
        await graph.ainvoke({"request": state["request"], "context": state["context"]})
    )["result"]
    context = state["context"]
    validated_facts = result.payload if result.payload is not None else None
    findings = dict(context.relevant_findings)
    findings[AgentName.HR.value] = result.findings
    return {
        "assessment_results": {"hr": result},
        "context": context.model_copy(
            update={
                "validated_hr_facts": validated_facts,
                "facts_version": context.facts_version + (1 if validated_facts else 0),
                "relevant_findings": findings,
            }
        ),
    }


def _route_after_hr(state: OnboardingState) -> str:
    result = state["assessment_results"]["hr"]
    return (
        "assess_specialists"
        if result.outcome is SpecialistOutcome.COMPLETED
        else "classify"
    )


async def _run_parallel_assessments(
    state: OnboardingState, graphs: dict[str, Any]
) -> dict[str, Any]:
    context = state["context"]

    async def invoke(item: tuple[str, Any]) -> tuple[str, Any]:
        name, graph = item
        result = await graph.ainvoke({"context": context})
        return name, result["result"]

    results = dict(await asyncio.gather(*(invoke(item) for item in graphs.items())))
    return {"assessment_results": {**state["assessment_results"], **results}}


def _requirement_satisfied(
    requirement: RequirementCode,
    results: dict[str, SpecialistResult[Any]],
) -> bool:
    if requirement is RequirementCode.EMPLOYEE_IDENTITY_RESOLVED:
        return results["hr"].payload is not None
    if requirement is RequirementCode.HR_FACTS_VALIDATED:
        return results["hr"].outcome is SpecialistOutcome.COMPLETED
    if requirement is RequirementCode.SECURITY_TRAINING_VERIFIED:
        compliance_result = results.get("compliance")
        if compliance_result is None or compliance_result.payload is None:
            return False
        assessment: ComplianceAssessment = compliance_result.payload
        return any(
            requirement_item.code is requirement
            and requirement_item.status is ComplianceRequirementStatus.VERIFIED
            for requirement_item in assessment.requirements
        )
    return False


def _task_from_proposal(
    proposal: TaskProposal,
    existing: TaskRecord | None,
    results: dict[str, SpecialistResult[Any]],
) -> TaskRecord:
    if existing is not None and existing.status is TaskStatus.SUCCEEDED:
        return existing
    ready = all(
        _requirement_satisfied(requirement, results)
        for requirement in proposal.required_requirements
    )
    status = TaskStatus.READY if ready else TaskStatus.BLOCKED
    return TaskRecord(**proposal.model_dump(), status=status)


def _plan_tasks(state: OnboardingState) -> dict[str, Any]:
    results = state["assessment_results"]
    existing_by_id = {task.task_id: task for task in state.get("tasks", [])}
    proposals = [
        proposal for result in results.values() for proposal in result.proposed_tasks
    ]
    invalid_ids, plan_errors = validate_task_proposals(
        proposals,
        current_revision=state["context"].state_revision,
        known_task_ids=set(existing_by_id),
    )
    tasks_by_id = dict(existing_by_id)
    for proposal in proposals:
        if proposal.task_id in invalid_ids:
            continue
        tasks_by_id[proposal.task_id] = _task_from_proposal(
            proposal,
            existing_by_id.get(proposal.task_id),
            results,
        )
    errors = [
        ErrorDetail(code="missing_input", message=missing.reason)
        for result in results.values()
        for missing in result.missing_inputs
    ]
    errors = [*plan_errors, *errors]
    errors.extend(
        ErrorDetail(code="conflict", message=conflict.field)
        for result in results.values()
        for conflict in result.conflicts
    )
    return {"tasks": list(tasks_by_id.values()), "errors": errors}


def _operation_type(intent: TaskIntent) -> str:
    return {
        TaskIntent.SUBMIT_IT_REQUEST: "submit_it_request",
        TaskIntent.CREATE_COMPLIANCE_CASE: "create_compliance_case",
        TaskIntent.SUBMIT_PAYROLL_SETUP: "submit_payroll_setup",
    }[intent]


async def _execute_actions(
    state: OnboardingState, executor: OperationExecutor
) -> dict[str, Any]:
    executor.restore(state.get("operations", []))
    operations_by_key = {
        operation.operation_key: operation for operation in state.get("operations", [])
    }
    ready_tasks = [
        task
        for task in state.get("tasks", [])
        if task.status is TaskStatus.READY
        and task.intent is not TaskIntent.DELIVER_NOTIFICATION
    ]

    def request_for(task: TaskRecord) -> OperationRequest:
        operation_key = task.operation_key or f"{task.task_id}:operation"
        return OperationRequest(
            operation_key=operation_key,
            task_id=task.task_id,
            operation_type=_operation_type(task.intent),
            payload={"task_id": task.task_id, "goal": task.goal},
        )

    results = await asyncio.gather(
        *(
            asyncio.to_thread(executor.execute, request_for(task))
            for task in ready_tasks
        )
    )
    results_by_task = dict(
        zip((task.task_id for task in ready_tasks), results, strict=True)
    )
    updated_tasks: list[TaskRecord] = []
    for task in state.get("tasks", []):
        if (
            task.status is not TaskStatus.READY
            or task.intent is TaskIntent.DELIVER_NOTIFICATION
        ):
            updated_tasks.append(task)
            continue
        result = results_by_task[task.task_id]
        operation_key = result.operation.operation_key
        operations_by_key[operation_key] = result.operation
        status = {
            OperationStatus.SUCCEEDED: TaskStatus.SUCCEEDED,
            OperationStatus.UNKNOWN: TaskStatus.WAITING,
            OperationStatus.FAILED: TaskStatus.FAILED,
            OperationStatus.NEEDS_RESOLUTION: TaskStatus.NEEDS_RESOLUTION,
        }.get(result.status, TaskStatus.WAITING)
        updated_tasks.append(
            task.model_copy(
                update={
                    "status": status,
                    "attempts": task.attempts + 1,
                    "result_reference": result.operation.external_reference,
                }
            )
        )
    return {
        "tasks": updated_tasks,
        "operations": list(operations_by_key.values()),
    }


def _classify(state: OnboardingState) -> dict[str, Any]:
    hr_result = state["assessment_results"].get("hr")
    if any(error.code == "invalid_plan" for error in state.get("errors", [])):
        status = OnboardingStatus.INVALID_PLAN
    elif (
        hr_result is not None
        and hr_result.outcome is SpecialistOutcome.NEEDS_RESOLUTION
        or any(error.code == "conflict" for error in state.get("errors", []))
    ):
        status = OnboardingStatus.NEEDS_RESOLUTION
    elif hr_result is not None and hr_result.outcome is SpecialistOutcome.NEEDS_INPUT:
        status = OnboardingStatus.WAITING_FOR_INPUT
    elif any(task.status is TaskStatus.FAILED for task in state.get("tasks", [])):
        status = OnboardingStatus.BLOCKED_BY_FAILURE
    elif any(error.code == "missing_input" for error in state.get("errors", [])):
        status = OnboardingStatus.WAITING_FOR_INPUT
    elif any(
        task.status in {TaskStatus.BLOCKED, TaskStatus.WAITING}
        for task in state.get("tasks", [])
    ):
        status = OnboardingStatus.WAITING_FOR_EXTERNAL_EVENT
    else:
        status = OnboardingStatus.COMPLETE
    return {"status": status}


async def _communicate(
    state: OnboardingState, graph, executor: OperationExecutor
) -> dict[str, Any]:
    result = (await graph.ainvoke({"context": state["context"]}))["result"]
    request = OperationRequest(
        operation_key=f"{state['context'].onboarding_id}:notification:{state['context'].state_revision}:{state['status'].value}",
        task_id=f"{state['context'].onboarding_id}:notification",
        operation_type="deliver_notification",
        payload={
            "status": state["status"].value,
            "recipients": result.payload.recipient_references,
        },
    )
    delivery = executor.execute(request)
    notification_status = {
        OperationStatus.SUCCEEDED: DeliveryStatus.DELIVERED,
        OperationStatus.FAILED: DeliveryStatus.FAILED,
        OperationStatus.UNKNOWN: DeliveryStatus.UNKNOWN,
        OperationStatus.NEEDS_RESOLUTION: DeliveryStatus.NEEDS_RESOLUTION,
    }.get(delivery.status, DeliveryStatus.UNKNOWN)
    operations = {
        operation.operation_key: operation for operation in state.get("operations", [])
    }
    operations[delivery.operation.operation_key] = delivery.operation
    return {
        "notifications": [
            result.model_copy(
                update={
                    "payload": result.payload.model_copy(
                        update={"status": notification_status}
                    )
                }
            )
        ],
        "operations": list(operations.values()),
    }


def build_onboarding_graph(
    *,
    executor: OperationExecutor | None = None,
    checkpointer: Any | None = None,
):
    """Compile the parent graph with injected tools and optional checkpointing."""

    operation_executor = executor or OperationExecutor(SimulatedCompany())
    specialist_graphs = {
        "it": it.build_graph(),
        "compliance": compliance.build_graph(),
        "payroll": payroll.build_graph(),
    }
    hr_graph = hr.build_graph()
    communication_graph = communication.build_graph()

    workflow = StateGraph(OnboardingState)
    workflow.add_node("prepare", _prepare)

    async def hr_node(state: OnboardingState) -> dict[str, Any]:
        return await _run_hr(state, hr_graph)

    async def parallel_node(state: OnboardingState) -> dict[str, Any]:
        return await _run_parallel_assessments(state, specialist_graphs)

    async def action_node(state: OnboardingState) -> dict[str, Any]:
        return await _execute_actions(state, operation_executor)

    async def communication_node(state: OnboardingState) -> dict[str, Any]:
        return await _communicate(state, communication_graph, operation_executor)

    workflow.add_node("hr_assessment", hr_node)
    workflow.add_node(
        "parallel_assessments",
        parallel_node,
    )
    workflow.add_node("plan", _plan_tasks)
    workflow.add_node("actions", action_node)
    workflow.add_node("classify", _classify)
    workflow.add_node("communicate", communication_node)
    workflow.set_entry_point("prepare")
    workflow.add_edge("prepare", "hr_assessment")
    workflow.add_conditional_edges(
        "hr_assessment",
        _route_after_hr,
        {"assess_specialists": "parallel_assessments", "classify": "classify"},
    )
    workflow.add_edge("parallel_assessments", "plan")
    workflow.add_edge("plan", "actions")
    workflow.add_edge("actions", "classify")
    workflow.add_edge("classify", "communicate")
    workflow.add_edge("communicate", END)
    return workflow.compile(checkpointer=checkpointer)

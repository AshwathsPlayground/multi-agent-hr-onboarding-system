"""Parent LangGraph for deterministic, production-shaped onboarding runs."""

import asyncio
import hashlib
import json
from collections.abc import Mapping
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
from zensible.modeling import ScriptedStructuredAgentModel, StructuredAgentModel
from zensible.observability import EventSink
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


def _result_errors(result: SpecialistResult[Any]) -> list[ErrorDetail]:
    errors = list(result.errors)
    errors.extend(
        ErrorDetail(code="missing_input", message=missing.reason)
        for missing in result.missing_inputs
    )
    errors.extend(
        ErrorDetail(code="conflict", message=conflict.field)
        for conflict in result.conflicts
    )
    return errors


def _input_fingerprint(state: OnboardingState) -> str:
    context = state["context"]
    material = {
        "resume_event": (
            context.resume_event.model_dump(mode="json")
            if context.resume_event is not None
            else None
        ),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _notification_operation_key(state: OnboardingState) -> str:
    context = state["context"]
    event_material = (
        context.resume_event.model_dump(mode="json")
        if context.resume_event is not None
        else {"kind": "initial"}
    )
    event_fingerprint = hashlib.sha256(
        json.dumps(event_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return (
        f"{context.onboarding_id}:notification:{state['status'].value}:"
        f"{event_fingerprint}"
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
        "errors": _result_errors(result),
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
    task_records: Mapping[str, TaskRecord] | None = None,
) -> TaskRecord:
    if existing is not None and existing.status is TaskStatus.SUCCEEDED:
        return existing
    if existing is not None and existing.status is TaskStatus.FAILED:
        return existing
    ready = all(
        _requirement_satisfied(requirement, results)
        for requirement in proposal.required_requirements
    )
    records = task_records or {}
    unmet_dependencies = [
        dependency
        for dependency in proposal.depends_on
        if records.get(dependency) is None
        or records[dependency].status is not TaskStatus.SUCCEEDED
    ]
    if unmet_dependencies:
        ready = False
    status = TaskStatus.READY if ready else TaskStatus.BLOCKED
    block_reason = (
        f"dependencies not succeeded: {', '.join(unmet_dependencies)}"
        if unmet_dependencies
        else None
    )
    return TaskRecord(**proposal.model_dump(), status=status, block_reason=block_reason)


def _deferred_task_from_proposal(
    proposal: TaskProposal,
    existing: TaskRecord | None,
    results: dict[str, SpecialistResult[Any]],
    reason: str,
    task_records: Mapping[str, TaskRecord] | None = None,
) -> TaskRecord:
    """Keep model-deferred work visible instead of silently dropping it."""

    task = _task_from_proposal(proposal, existing, results, task_records)
    if task.status is TaskStatus.SUCCEEDED:
        return task
    return task.model_copy(
        update={
            "status": (
                TaskStatus.NEEDS_RESOLUTION
                if task.status is TaskStatus.READY
                else task.status
            ),
            "block_reason": "; ".join(
                item for item in (reason, task.block_reason) if item
            ),
        }
    )


def _plan_tasks(state: OnboardingState) -> dict[str, Any]:
    results = state["assessment_results"]
    existing_by_id = {task.task_id: task for task in state.get("tasks", [])}
    active_proposals = [
        proposal for result in results.values() for proposal in result.proposed_tasks
    ]
    deferred_proposals = [
        proposal for result in results.values() for proposal in result.deferred_tasks
    ]
    proposals = [proposal for proposal in [*active_proposals, *deferred_proposals]]
    invalid_ids, plan_errors = validate_task_proposals(
        proposals,
        current_revision=state["context"].state_revision,
        known_task_ids=set(existing_by_id),
    )
    tasks_by_id = dict(existing_by_id)
    candidate_records = dict(existing_by_id)
    for proposal in proposals:
        if proposal.task_id not in invalid_ids:
            candidate_records[proposal.task_id] = TaskRecord(
                **proposal.model_dump(), status=TaskStatus.PENDING
            )
    for proposal in active_proposals:
        if proposal.task_id in invalid_ids:
            continue
        tasks_by_id[proposal.task_id] = _task_from_proposal(
            proposal,
            existing_by_id.get(proposal.task_id),
            results,
            candidate_records,
        )
        candidate_records[proposal.task_id] = tasks_by_id[proposal.task_id]
    for result in results.values():
        reason = (
            result.model_output.recommendation
            if result.model_output is not None
            else "task was deferred by specialist guidance"
        )
        for proposal in result.deferred_tasks:
            if proposal.task_id in invalid_ids:
                continue
            tasks_by_id[proposal.task_id] = _deferred_task_from_proposal(
                proposal,
                existing_by_id.get(proposal.task_id),
                results,
                reason,
                candidate_records,
            )
            candidate_records[proposal.task_id] = tasks_by_id[proposal.task_id]
    errors = [*plan_errors]
    errors.extend(error for result in results.values() for error in result.errors)
    errors.extend(
        ErrorDetail(code="missing_input", message=missing.reason)
        for result in results.values()
        for missing in result.missing_inputs
    )
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
    task_records = {task.task_id: task for task in state.get("tasks", [])}
    prepared_tasks: list[TaskRecord] = []
    for task in state.get("tasks", []):
        if task.status is not TaskStatus.READY:
            prepared_tasks.append(task)
            continue
        unmet_dependencies = [
            dependency
            for dependency in task.depends_on
            if task_records.get(dependency) is None
            or task_records[dependency].status is not TaskStatus.SUCCEEDED
        ]
        if unmet_dependencies:
            prepared_tasks.append(
                task.model_copy(
                    update={
                        "status": TaskStatus.BLOCKED,
                        "block_reason": (
                            "dependencies not succeeded: "
                            + ", ".join(unmet_dependencies)
                        ),
                    }
                )
            )
        else:
            prepared_tasks.append(task)
    ready_tasks = [
        task
        for task in prepared_tasks
        if task.status is TaskStatus.READY
        and task.intent is not TaskIntent.DELIVER_NOTIFICATION
    ]

    def request_for(task: TaskRecord) -> OperationRequest:
        input_fingerprint = _input_fingerprint(state)
        operation_key = (
            f"{task.operation_key or f'{task.task_id}:operation'}:"
            f"{input_fingerprint[:16]}"
        )
        return OperationRequest(
            operation_key=operation_key,
            task_id=task.task_id,
            operation_type=_operation_type(task.intent),
            payload={
                "task_id": task.task_id,
                "goal": task.goal,
                "input_fingerprint": input_fingerprint,
            },
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
    for task in prepared_tasks:
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
    if any(
        error.code in {"invalid_plan", "invalid_model_output"}
        for error in state.get("errors", [])
    ):
        status = OnboardingStatus.INVALID_PLAN
    elif (
        hr_result is not None
        and hr_result.outcome is SpecialistOutcome.NEEDS_RESOLUTION
        or any(
            error.code in {"conflict", "model_escalation"}
            for error in state.get("errors", [])
        )
    ):
        status = OnboardingStatus.NEEDS_RESOLUTION
    elif hr_result is not None and hr_result.outcome is SpecialistOutcome.NEEDS_INPUT:
        status = OnboardingStatus.WAITING_FOR_INPUT
    elif any(task.status is TaskStatus.FAILED for task in state.get("tasks", [])):
        status = OnboardingStatus.BLOCKED_BY_FAILURE
    elif any(error.code == "missing_input" for error in state.get("errors", [])):
        status = OnboardingStatus.WAITING_FOR_INPUT
    elif any(
        task.status is TaskStatus.NEEDS_RESOLUTION for task in state.get("tasks", [])
    ):
        status = OnboardingStatus.NEEDS_RESOLUTION
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
    current_status = state["status"]
    communication_errors = list(state.get("errors", []))
    communication_errors.extend(_result_errors(result))
    blocked = (
        bool(result.errors) or result.outcome is SpecialistOutcome.NEEDS_RESOLUTION
    )
    waiting = (
        bool(result.missing_inputs) or result.outcome is SpecialistOutcome.NEEDS_INPUT
    )
    if blocked or waiting:
        status = current_status
        if current_status not in {
            OnboardingStatus.INVALID_PLAN,
            OnboardingStatus.BLOCKED_BY_FAILURE,
        }:
            status = (
                OnboardingStatus.NEEDS_RESOLUTION
                if blocked
                else OnboardingStatus.WAITING_FOR_INPUT
            )
        notification = result.model_copy(
            update={
                "payload": result.payload.model_copy(
                    update={"status": DeliveryStatus.NEEDS_RESOLUTION}
                )
            }
        )
        return {
            "status": status,
            "errors": communication_errors,
            "notifications": [notification],
        }
    request = OperationRequest(
        operation_key=_notification_operation_key(state),
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
        "errors": communication_errors,
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
    agent_model: StructuredAgentModel | None = None,
    events: EventSink | None = None,
):
    """Compile the parent graph with injected providers and checkpointing."""

    operation_executor = executor or OperationExecutor(
        SimulatedCompany(), events=events
    )
    model = agent_model or ScriptedStructuredAgentModel(
        {
            agent.value: {
                "summary": f"{agent.value} scripted assessment completed",
                "recommendation": "follow deterministic domain policy",
                "confidence": 1.0,
                "evidence": ["offline scripted model"],
            }
            for agent in AgentName
        },
        events=events,
    )
    specialist_graphs = {
        "it": it.build_graph(model, events=events),
        "compliance": compliance.build_graph(model, events=events),
        "payroll": payroll.build_graph(model, events=events),
    }
    hr_graph = hr.build_graph(model, events=events)
    communication_graph = communication.build_graph(model, events=events)

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

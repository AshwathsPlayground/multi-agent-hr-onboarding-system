"""Checkpoint-friendly parent graph state."""

from typing import Any, TypedDict

from zensible.domain.contracts import (
    AgentContext,
    ErrorDetail,
    OnboardingRequest,
    OnboardingStatus,
    OperationRecord,
    ResumeEvent,
    TaskRecord,
)


class OnboardingState(TypedDict, total=False):
    request: OnboardingRequest
    context: AgentContext
    resume_event: ResumeEvent | None
    status: OnboardingStatus
    assessment_results: dict[str, Any]
    tasks: list[TaskRecord]
    operations: list[OperationRecord]
    errors: list[ErrorDetail]
    notifications: list[Any]

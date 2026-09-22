"""Private state shape shared by specialist subgraphs."""

from typing import Any, TypedDict

from zensible.domain.contracts import AgentContext, OnboardingRequest, TaskRecord


class SpecialistState(TypedDict, total=False):
    request: OnboardingRequest
    context: AgentContext
    eligible_tasks: list[TaskRecord]
    result: Any

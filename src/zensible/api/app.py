"""Minimal HTTP boundary over the onboarding graph."""

import asyncio
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from zensible.domain.contracts import (
    ErrorDetail,
    OnboardingRequest,
    OnboardingStatus,
    OperationRecord,
    ResumeEvent,
    TaskRecord,
)
from zensible.orchestration.graph import build_onboarding_graph
from zensible.orchestration.state import OnboardingState
from zensible.simulation import SimulatedCompany
from zensible.tools import OperationExecutor


class OnboardingSnapshot(BaseModel):
    """Stable API response that omits private model/tool messages."""

    model_config = ConfigDict(extra="forbid")

    onboarding_id: str
    status: OnboardingStatus
    state_revision: int = Field(ge=0)
    tasks: list[TaskRecord] = Field(default_factory=list)
    operations: list[OperationRecord] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
    notifications: list[Any] = Field(default_factory=list)


class OnboardingService:
    """Own graph instances and in-memory state for the offline demo server."""

    def __init__(self) -> None:
        self._executor = OperationExecutor(SimulatedCompany())
        self._graph = build_onboarding_graph(executor=self._executor)
        self._states: dict[str, OnboardingState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, onboarding_id: str) -> asyncio.Lock:
        return self._locks.setdefault(onboarding_id, asyncio.Lock())

    async def start(self, request: OnboardingRequest) -> OnboardingSnapshot:
        async with self._lock_for(request.onboarding_id):
            state = await self._graph.ainvoke({"request": request})
            self._states[request.onboarding_id] = state
        return self.snapshot(state)

    async def resume(
        self, onboarding_id: str, event: ResumeEvent
    ) -> OnboardingSnapshot:
        async with self._lock_for(onboarding_id):
            state = self._states.get(onboarding_id)
            if state is None:
                raise KeyError(onboarding_id)
            next_state = await self._graph.ainvoke(
                {
                    "request": state["request"],
                    "context": state["context"],
                    "tasks": state.get("tasks", []),
                    "operations": state.get("operations", []),
                    "resume_event": event,
                }
            )
            self._states[onboarding_id] = next_state
        return self.snapshot(next_state)

    def get(self, onboarding_id: str) -> OnboardingSnapshot | None:
        state = self._states.get(onboarding_id)
        return self.snapshot(state) if state is not None else None

    @staticmethod
    def snapshot(state: OnboardingState) -> OnboardingSnapshot:
        context = state["context"]
        return OnboardingSnapshot(
            onboarding_id=context.onboarding_id,
            status=state["status"],
            state_revision=context.state_revision,
            tasks=state.get("tasks", []),
            operations=state.get("operations", []),
            errors=state.get("errors", []),
            notifications=state.get("notifications", []),
        )


def create_app(service: OnboardingService | None = None) -> FastAPI:
    """Create the app with injectable service state for tests and deployments."""

    app = FastAPI(title="Zensible HR Onboarding", version="0.1.0")
    onboarding_service = service or OnboardingService()

    @app.post(
        "/onboardings",
        response_model=OnboardingSnapshot,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_onboarding(
        request: OnboardingRequest,
        x_hr_actor: str | None = Header(default=None),
    ) -> OnboardingSnapshot:
        # Mock authentication boundary: replace this header check with the real IdP later.
        if x_hr_actor:
            request = request.model_copy(update={"requested_by": x_hr_actor})
        return await onboarding_service.start(request)

    @app.get("/onboardings/{onboarding_id}", response_model=OnboardingSnapshot)
    async def get_onboarding(onboarding_id: str) -> OnboardingSnapshot:
        snapshot = onboarding_service.get(onboarding_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="onboarding not found")
        return snapshot

    @app.post("/onboardings/{onboarding_id}/events", response_model=OnboardingSnapshot)
    async def resume_onboarding(
        onboarding_id: str,
        event: ResumeEvent,
        x_hr_actor: str | None = Header(default=None),
    ) -> OnboardingSnapshot:
        if x_hr_actor:
            event = event.model_copy(update={"source": x_hr_actor})
        try:
            return await onboarding_service.resume(onboarding_id, event)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="onboarding not found"
            ) from error

    return app


app = create_app()

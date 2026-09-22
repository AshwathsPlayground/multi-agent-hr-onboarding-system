"""Reviewer-facing offline and live onboarding demonstration."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime

from zensible.config import Settings
from zensible.domain.contracts import (
    AgentName,
    ModelAssessment,
    OnboardingRequest,
    ResumeEvent,
    ResumeEventKind,
)
from zensible.modeling import (
    LangChainStructuredAgentModel,
    ScriptedStructuredAgentModel,
    StructuredAgentModel,
)
from zensible.observability import ExecutionEvent, RecordingEventSink
from zensible.orchestration.graph import build_onboarding_graph
from zensible.simulation import SimulatedCompany
from zensible.tools import OperationExecutor


def _request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_demo_cli",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


def _offline_model(events: RecordingEventSink) -> StructuredAgentModel:
    return ScriptedStructuredAgentModel(
        {
            agent.value: ModelAssessment(
                summary=f"{agent.value} scripted model output",
                recommendation="continue with deterministic domain policy",
                confidence=0.99,
                evidence=["offline demo fixture"],
            )
            for agent in AgentName
        },
        events=events,
    )


def _print_events(events: list[ExecutionEvent], start: int) -> int:
    for event in events[start:]:
        print(
            json.dumps(
                {
                    "kind": event.kind,
                    "name": event.name,
                    "payload": event.payload,
                },
                sort_keys=True,
            )
        )
    return len(events)


async def _run(mode: str, resume: bool) -> None:
    events = RecordingEventSink()
    company = SimulatedCompany()
    if mode == "live":
        model: StructuredAgentModel = LangChainStructuredAgentModel(
            Settings(), events=events
        )
    else:
        model = _offline_model(events)
    executor = OperationExecutor(company, events=events)
    graph = build_onboarding_graph(
        executor=executor,
        agent_model=model,
        events=events,
    )

    first = await graph.ainvoke({"request": _request()})
    event_index = _print_events(events.events, 0)
    print(json.dumps({"run": "initial", "status": first["status"].value}))

    if not resume:
        return

    resume_event = ResumeEvent(
        kind=ResumeEventKind.TRAINING_EVIDENCE_SUBMITTED,
        payload={"status": "verified", "bank_details_reference": "bank_ref_123"},
        source="hr_user_42",
        submitted_at=datetime(2026, 9, 22, 10, 30, tzinfo=UTC),
    )
    resumed = await graph.ainvoke(
        {
            "request": _request(),
            "context": first["context"],
            "tasks": first["tasks"],
            "operations": first["operations"],
            "resume_event": resume_event,
        }
    )
    _print_events(events.events, event_index)
    print(json.dumps({"run": "resumed", "status": resumed["status"].value}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="show only the first onboarding run",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.mode, resume=not args.no_resume))


if __name__ == "__main__":
    main()

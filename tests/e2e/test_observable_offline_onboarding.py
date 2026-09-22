import asyncio
import json
from datetime import UTC, date, datetime

import pytest

from zensible.domain.contracts import (
    AgentName,
    ModelAssessment,
    OnboardingRequest,
    ResumeEvent,
    ResumeEventKind,
)
from zensible.modeling import ScriptedStructuredAgentModel
from zensible.observability import RecordingEventSink
from zensible.orchestration.graph import build_onboarding_graph
from zensible.simulation import SimulatedCompany
from zensible.tools import OperationExecutor

pytestmark = pytest.mark.assignment


def request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_observable_offline",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


def scripted_model(events: RecordingEventSink) -> ScriptedStructuredAgentModel:
    return ScriptedStructuredAgentModel(
        {
            agent.value: ModelAssessment(
                summary=f"{agent.value} scripted model output",
                recommendation="continue with deterministic policy",
                confidence=0.99,
                evidence=["offline test fixture"],
            )
            for agent in AgentName
        },
        events=events,
    )


def print_transcript(events: RecordingEventSink) -> None:
    for event in events.events:
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


def test_offline_full_flow_prints_model_tool_and_resume_events() -> None:
    events = RecordingEventSink()
    company = SimulatedCompany()
    executor = OperationExecutor(company, events=events)
    model = scripted_model(events)
    graph = build_onboarding_graph(
        executor=executor,
        agent_model=model,
        events=events,
    )

    first = asyncio.run(graph.ainvoke({"request": request()}))
    resume_event = ResumeEvent(
        kind=ResumeEventKind.TRAINING_EVIDENCE_SUBMITTED,
        payload={"status": "verified", "bank_details_reference": "bank_ref_123"},
        source="hr_user_42",
        submitted_at=datetime(2026, 9, 22, 10, 30, tzinfo=UTC),
    )
    second = asyncio.run(
        graph.ainvoke(
            {
                "request": request(),
                "context": first["context"],
                "tasks": first["tasks"],
                "operations": first["operations"],
                "resume_event": resume_event,
            }
        )
    )
    print_transcript(events)

    assert first["status"].value == "waiting_for_input"
    assert second["status"].value == "complete"
    assert {event.kind for event in events.events} == {
        "agent.result",
        "model.request",
        "model.response",
        "tool.request",
        "tool.response",
    }
    assert {
        event.name for event in events.events if event.kind == "model.response"
    } == {
        "hr",
        "it",
        "compliance",
        "payroll",
        "communication",
    }
    assert company.effect_count("create_compliance_case") == 1
    assert company.effect_count("submit_payroll_setup") == 1

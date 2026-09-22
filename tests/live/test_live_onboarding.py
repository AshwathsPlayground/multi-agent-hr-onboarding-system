import asyncio
from datetime import date

import pytest

from zensible.config import Settings
from zensible.domain.contracts import OnboardingRequest
from zensible.modeling import LangChainStructuredAgentModel
from zensible.observability import RecordingEventSink, render_events
from zensible.orchestration.graph import build_onboarding_graph
from zensible.simulation import SimulatedCompany
from zensible.tools import OperationExecutor

pytestmark = pytest.mark.live


def test_live_model_runs_all_specialists_with_simulated_tools() -> None:
    settings = Settings()
    if settings.cliproxy_api_key is None:
        pytest.fail("CLIPROXY_API_KEY is required for the live onboarding test")

    events = RecordingEventSink()
    company = SimulatedCompany()
    model = LangChainStructuredAgentModel(settings, events=events)
    graph = build_onboarding_graph(
        executor=OperationExecutor(company, events=events),
        agent_model=model,
        events=events,
    )
    request = OnboardingRequest(
        onboarding_id="onb_live_demo",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )

    state = asyncio.run(graph.ainvoke({"request": request}))

    print(render_events(events.events))

    model_responses = [
        event for event in events.events if event.kind == "model.response"
    ]
    assert {event.name for event in model_responses} == {
        "hr",
        "it",
        "compliance",
        "payroll",
        "communication",
    }
    assert state["status"].value == "waiting_for_input"
    assert company.effect_count("submit_it_request") == 1
    assert company.effect_count("create_compliance_case") == 1

from datetime import date

import pytest

from zensible.agents import hr, payroll
from zensible.config import Settings
from zensible.domain.contracts import AgentContext, OnboardingRequest, SpecialistOutcome
from zensible.modeling import LangChainStructuredAgentModel
from zensible.observability import RecordingEventSink, render_events

pytestmark = [pytest.mark.live, pytest.mark.asyncio(loop_scope="session")]


def live_model(events: RecordingEventSink) -> LangChainStructuredAgentModel:
    settings = Settings()
    if settings.cliproxy_api_key is None:
        pytest.fail("CLIPROXY_API_KEY is required for live specialist tests")
    return LangChainStructuredAgentModel(settings, events=events)


def ambiguous_request() -> OnboardingRequest:
    return OnboardingRequest(
        onboarding_id="onb_live_ambiguous",
        employee_reference="Ambiguous Person",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_live_hr_preserves_ambiguous_employee_as_resolution() -> None:
    events = RecordingEventSink()
    result = await hr.assess(
        ambiguous_request(),
        state_revision=0,
        model=live_model(events),
    )
    print(render_events(events.events))

    assert result.outcome is SpecialistOutcome.NEEDS_RESOLUTION
    assert result.conflicts
    assert result.model_output is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_live_payroll_preserves_missing_bank_details() -> None:
    events = RecordingEventSink()
    context = AgentContext(
        onboarding_id="onb_live_payroll_missing",
        state_revision=0,
        facts_version=1,
        policy_version="2026-09",
    )
    result = await payroll.assess(
        context,
        state_revision=0,
        model=live_model(events),
    )
    print(render_events(events.events))

    assert result.outcome is SpecialistOutcome.COMPLETED
    assert result.missing_inputs[0].field == "bank_details_reference"
    assert result.proposed_tasks == []
    assert result.model_output is not None

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from zensible.config import Settings
from zensible.domain.contracts import (
    OnboardingRequest,
    ResumeEvent,
    ResumeEventKind,
)
from zensible.orchestration.graph import build_onboarding_graph
from zensible.persistence import postgres_checkpointer


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_postgres_checkpointer_can_initialize_and_write_a_checkpoint() -> None:
    settings = Settings()
    async with postgres_checkpointer(settings.postgres_dsn, setup=True) as checkpointer:
        config = {
            "configurable": {
                "thread_id": "pytest-checkpointer",
                "checkpoint_ns": "integration",
            }
        }
        await checkpointer.aput(
            config,
            checkpoint={
                "v": 1,
                "id": "checkpoint-1",
                "ts": "2026-09-22T00:00:00+00:00",
                "channel_values": {},
                "channel_versions": {},
                "versions_seen": {},
                "updated_channels": None,
            },
            metadata={"source": "input", "step": -1, "writes": None},
            new_versions={},
        )

        saved = await checkpointer.aget_tuple(config)

    assert saved is not None
    assert saved.checkpoint["id"] == "checkpoint-1"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_graph_can_resume_from_postgres_checkpoint() -> None:
    run_id = uuid4().hex
    request = OnboardingRequest(
        onboarding_id=f"onb_checkpoint_graph_{run_id}",
        employee_reference="John Smith",
        requested_role="Engineering Manager",
        requested_location="Bangalore",
        requested_joining_date=date(2026, 10, 1),
        requested_by="hr_user_42",
    )
    event = ResumeEvent(
        kind=ResumeEventKind.BANK_DETAILS_SUBMITTED,
        payload={"bank_details_reference": "bank_ref_123"},
        source="hr_user_42",
        submitted_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    config = {"configurable": {"thread_id": f"pytest-graph-resume-{run_id}"}}

    async with postgres_checkpointer(Settings().postgres_dsn, setup=True) as saver:
        graph = build_onboarding_graph(checkpointer=saver)
        await graph.ainvoke({"request": request}, config)
        resumed = await graph.ainvoke({"resume_event": event}, config)

    assert resumed["context"].state_revision == 1

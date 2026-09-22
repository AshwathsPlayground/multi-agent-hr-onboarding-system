from datetime import UTC, datetime

from fastapi.testclient import TestClient

from zensible.api.app import create_app
from zensible.domain.contracts import ResumeEventKind


def request_body() -> dict[str, str]:
    return {
        "onboarding_id": "onb_api_123",
        "employee_reference": "John Smith",
        "requested_role": "Engineering Manager",
        "requested_location": "Bangalore",
        "requested_joining_date": "2026-10-01",
        "requested_by": "hr_user_42",
    }


def test_api_creates_and_resumes_an_onboarding() -> None:
    with TestClient(create_app()) as client:
        created = client.post("/onboardings", json=request_body())
        assert created.status_code == 201
        assert created.json()["status"] == "waiting_for_input"

        resumed = client.post(
            "/onboardings/onb_api_123/events",
            json={
                "kind": ResumeEventKind.TRAINING_EVIDENCE_SUBMITTED.value,
                "payload": {
                    "status": "verified",
                    "bank_details_reference": "bank_ref_123",
                },
                "source": "hr_user_42",
                "submitted_at": datetime(2026, 9, 22, 10, 30, tzinfo=UTC).isoformat(),
            },
        )

        assert resumed.status_code == 200
        assert resumed.json()["status"] == "complete"


def test_api_returns_not_found_for_unknown_onboarding() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/onboardings/does-not-exist")

    assert response.status_code == 404

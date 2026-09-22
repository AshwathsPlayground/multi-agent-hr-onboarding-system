import pytest

from zensible.config import Settings
from zensible.llm import build_chat_model


@pytest.mark.live
def test_clip_proxy_gpt_5_6_luna_returns_expected_text() -> None:
    settings = Settings()
    if settings.cliproxy_api_key is None:
        pytest.skip("CLIPROXY_API_KEY is not configured")

    response = build_chat_model(settings).invoke(
        "Reply with exactly: repository live model test passed"
    )

    assert response.content.strip() == "repository live model test passed"

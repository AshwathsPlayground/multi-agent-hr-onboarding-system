from zensible.config import Settings
from zensible.llm import build_chat_model


def test_settings_read_cli_proxy_and_langsmith_values(monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXY_BASE_URL", "http://proxy.test/v1")
    monkeypatch.setenv("CLIPROXY_API_KEY", "test-key")
    monkeypatch.setenv("CLIPROXY_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "zensible-tests")

    settings = Settings(_env_file=None)

    assert settings.cliproxy_base_url == "http://proxy.test/v1"
    assert settings.cliproxy_api_key.get_secret_value() == "test-key"
    assert settings.cliproxy_model == "gpt-5.6-luna"
    assert settings.langchain_tracing_v2 is True
    assert settings.langchain_project == "zensible-tests"


def test_model_factory_configures_openai_compatible_proxy(monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXY_BASE_URL", "http://proxy.test/v1")
    monkeypatch.setenv("CLIPROXY_API_KEY", "test-key")

    model = build_chat_model(Settings(_env_file=None))

    assert model.model_name == "gpt-5.6-luna"
    assert model.openai_api_base == "http://proxy.test/v1"


def test_model_factory_fails_clearly_without_proxy_key() -> None:
    settings = Settings(_env_file=None)

    try:
        build_chat_model(settings)
    except ValueError as error:
        assert "CLIPROXY_API_KEY" in str(error)
    else:
        raise AssertionError("Expected a missing API key error")

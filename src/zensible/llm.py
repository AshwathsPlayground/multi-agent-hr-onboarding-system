"""LangChain model construction kept behind one application seam."""

from langchain_openai import ChatOpenAI

from zensible.config import Settings


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """Build the configured OpenAI-compatible chat model.

    CLIProxyAPI is OpenAI-compatible, so the application uses LangChain's native
    ``ChatOpenAI`` adapter while keeping endpoint and credential handling in one
    place. A missing key is rejected before any network request is attempted.
    """

    if settings.cliproxy_api_key is None:
        raise ValueError("CLIPROXY_API_KEY is required for live model execution")

    return ChatOpenAI(
        model=settings.cliproxy_model,
        base_url=settings.cliproxy_base_url,
        api_key=settings.cliproxy_api_key.get_secret_value(),
        temperature=0,
    )

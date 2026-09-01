import os

from .base import Message, Provider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


def default_provider() -> Provider:
    """The one place to change which model the harness uses.

    PROVIDER=ollama runs everything on this machine: no API key, no network.
    Anything else (or unset) keeps the OpenAI default, so existing setups are
    unaffected.
    """
    if os.environ.get("PROVIDER", "").strip().lower() == "ollama":
        p = OllamaProvider()
        # Fail here, with an instruction, rather than inside a request later.
        p.assert_local()
        p.require_model()
        return p
    return OpenAIProvider()


__all__ = [
    "Provider",
    "Message",
    "OpenAIProvider",
    "OllamaProvider",
    "default_provider",
]

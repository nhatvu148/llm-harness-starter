from .base import Message, Provider
from .openai_provider import OpenAIProvider


def default_provider() -> Provider:
    """The one place to change which model the harness uses."""
    return OpenAIProvider()


__all__ = ["Provider", "Message", "OpenAIProvider", "default_provider"]

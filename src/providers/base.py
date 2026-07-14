"""Provider seam — the "model thinks" layer.

A Provider wraps any chat model behind two methods so the rest of the harness
never imports a vendor SDK directly. Swap the default in ``__init__.py`` to
change models without touching retrieval, tools, or procedures.
"""

from typing import Any, Iterable, Protocol

Message = dict[str, Any]  # {"role": ..., "content": ..., ...}


class Provider(Protocol):
    def complete(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> dict:
        """Return a normalized result.

        ``{"content": str | None, "tool_calls": [{"id", "name", "arguments"}]}``
        """
        ...

    def stream(self, messages: list[Message]) -> Iterable[str]:
        """Yield text chunks for a plain (no-tool) answer."""
        ...

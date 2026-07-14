"""Default provider: OpenAI. Swap this class to use a different model."""

import json
import os

from openai import OpenAI

from .base import Message


class OpenAIProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("MODEL", "gpt-4o-mini")
        self._api_key = api_key
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        # Lazy so the server can start (and /health work) without a key set.
        if self._client is None:
            self._client = OpenAI(
                api_key=self._api_key or os.environ.get("OPENAI_API_KEY")
            )
        return self._client

    def complete(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> dict:
        kwargs: dict = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        msg = self.client.chat.completions.create(**kwargs).choices[0].message
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments or "{}"),
            }
            for tc in (msg.tool_calls or [])
        ]
        return {"content": msg.content, "tool_calls": tool_calls}

    def stream(self, messages: list[Message]):
        stream = self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True
        )
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        finally:
            stream.close()

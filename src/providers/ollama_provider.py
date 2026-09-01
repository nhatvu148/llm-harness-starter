"""Local provider: Ollama. Nothing leaves the machine.

Same ``Provider`` protocol as ``OpenAIProvider`` — swap it in
``providers/__init__.py`` (or set ``PROVIDER=ollama``) and retrieval, tools and
procedures are untouched.

    ollama pull qwen3-coder:30b
    PROVIDER=ollama MODEL=qwen3-coder:30b task api

Four things here are NOT stylistic. Each is a measured failure where a perfectly
capable local model looked broken, and the naive reading was "local models can't
do tool calling".

1. NATIVE /api/chat, NOT /v1/chat/completions.
   Ollama's OpenAI-compatibility layer can return the model's raw tool-call
   markup as assistant *content* with ``tool_calls`` empty, while the native
   endpoint parses the same response into a structured array. Measured on
   Ollama 0.33.0 with qwen3-coder:30b: identical request, /api/chat parses it,
   /v1 does not.

2. num_ctx IS SET EXPLICITLY.
   Ollama defaults to 4096 tokens. A system prompt plus a few tool schemas plus
   one retrieved passage exceeds that before the model has room to answer, and
   the output degrades in a way that reads as low model quality. An entire
   "we tried Ollama and it was bad" verdict traced to this single default.

3. TOOL CALLS ARE RECOVERED FROM RAW MARKUP.
   Whether the template parses them is not reliable: with no system prompt at
   all, one question parsed cleanly and another leaked
   ``<function=name><parameter=k>v</parameter></function>`` as content. A loop
   reading only ``tool_calls`` treats that as a final answer and stops on step
   one.

4. NO SYSTEM PROMPT IS ADDED HERE.
   Adding instruction text measurably suppressed structured tool calling for
   qwen3-coder. Put behavioural guidance in tool DESCRIPTIONS, which the
   template injects properly. The procedures layer still works — it goes in the
   user turn, where the harness already puts it.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Iterable

from .base import Message

_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}

# The model's native tool-call markup, for when the template does not parse it.
_XML_CALL = re.compile(r"<function=([a-zA-Z_]\w*)>(.*?)</function>", re.DOTALL)
_XML_PARAM = re.compile(r"<parameter=([a-zA-Z_]\w*)>(.*?)</parameter>", re.DOTALL)


def _recover_tool_calls(content: str) -> list[dict]:
    """Parse tool calls the server left as text. See note 3 above."""
    out = []
    for i, (name, body) in enumerate(_XML_CALL.findall(content or "")):
        args = {k: v.strip() for k, v in _XML_PARAM.findall(body)}
        out.append({"id": f"recovered_{i}", "name": name, "arguments": args})
    return out


def _to_ollama_messages(messages: list[Message]) -> list[Message]:
    """Translate the harness's OpenAI-shaped history into Ollama's wire format.

    api.py rebuilds the assistant turn the way the OpenAI API wants it back:
    ``tool_calls[].function.arguments`` as a JSON STRING, and tool results keyed
    by ``tool_call_id``. Ollama's /api/chat wants ``arguments`` as an OBJECT and
    identifies results by ``tool_name``. Posting one shape to the other endpoint
    returns 400 Bad Request on the SECOND turn only -- the first request carries
    no history, so a single-shot tool call looks fine and the failure appears
    exactly when the tool result is fed back.

    Translating here rather than in api.py keeps the vendor quirk inside the
    vendor adapter, which is the point of the Provider seam: the harness should
    not have to know which model it is talking to.
    """
    names: dict[str, str] = {}  # tool_call_id -> tool name, for the result turns
    out: list[Message] = []
    for m in messages:
        m = dict(m)
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = dict(tc.get("function") or {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args or "{}")
                    except json.JSONDecodeError:
                        args = {}
                fn["arguments"] = args
                if tc.get("id"):
                    names[tc["id"]] = fn.get("name", "")
                calls.append({"function": fn})
            m["tool_calls"] = calls
            # Ollama rejects a null content alongside tool_calls.
            m["content"] = m.get("content") or ""
        elif m.get("role") == "tool":
            cid = m.pop("tool_call_id", None)
            m.setdefault("tool_name", names.get(cid, "") or m.get("name", ""))
            m.pop("name", None)
        out.append(m)
    return out


class OllamaProvider:
    """Chat completion against a local Ollama, normalised to the Provider shape."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or os.environ.get("MODEL", "qwen3-coder:30b")
        self.host = (
            host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        ).rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        self.num_ctx = int(os.environ.get("NUM_CTX", "32768"))
        self.timeout = int(os.environ.get("OLLAMA_TIMEOUT", "1800"))

    # -- guarantees ------------------------------------------------------- #

    def assert_local(self) -> None:
        """Refuse to run if the endpoint is not on this machine.

        Enforcing it beats documenting it: a demo once printed api.openai.com in
        its own banner while claiming to be air-gapped, because a library
        default leaked through a code path nobody re-read.
        """
        host = urllib.parse.urlparse(self.host).hostname or self.host
        if host not in _LOOPBACK:
            raise SystemExit(
                f"OllamaProvider: {self.host} is not local. Set OLLAMA_HOST to a "
                f"loopback address, or use a different provider deliberately."
            )

    def require_model(self) -> None:
        """Fail with an instruction rather than a 404 from inside a client."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=15) as r:
                have = {m["name"] for m in json.loads(r.read())["models"]}
        except OSError as e:
            raise SystemExit(
                f"OllamaProvider: cannot reach Ollama at {self.host} ({e}). "
                f"Start it with: ollama serve"
            ) from None
        if self.model not in have and self.model.split(":")[0] not in {
            n.split(":")[0] for n in have
        }:
            raise SystemExit(
                f"OllamaProvider: model '{self.model}' is not installed.\n"
                f"  ollama pull {self.model}\n"
                f"  installed: {', '.join(sorted(have)) or '(none)'}"
            )

    # -- Provider protocol ------------------------------------------------ #

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.host}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def complete(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": _to_ollama_messages(messages),
            "stream": False,
            "options": {"num_ctx": self.num_ctx, "temperature": 0},
        }
        if tools:
            payload["tools"] = tools
        msg = self._post("/api/chat", payload).get("message", {})

        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            # Native /api/chat gives a dict; the OpenAI shape gives a JSON
            # string. Accept both so swapping the endpoint cannot break this.
            if isinstance(args, str):
                args = json.loads(args or "{}")
            calls.append(
                {
                    "id": tc.get("id") or f"call_{i}",
                    "name": fn.get("name"),
                    "arguments": args,
                }
            )

        content = msg.get("content")
        if not calls:
            calls = _recover_tool_calls(content or "")
            if calls:
                # The markup was the tool call, not an answer. Returning it as
                # content would make the caller treat it as prose.
                content = None
        return {"content": content, "tool_calls": calls}

    def stream(self, messages: list[Message]) -> Iterable[str]:
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(
                {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"num_ctx": self.num_ctx, "temperature": 0},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            for line in r:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                piece = (chunk.get("message") or {}).get("content")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break

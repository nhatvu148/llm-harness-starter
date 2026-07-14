"""LLM Harness Starter — composes the four layers into one endpoint.

model (providers) + tools (act) + retrieval (RAG) + procedures (specialize).
"""

import json
import os
from typing import Dict, Generator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from procedures import load as load_procedures
from providers import default_provider
from retrieval import Retriever
from tools import call as call_tool
from tools import definitions as tool_definitions

load_dotenv()

BASE_SYSTEM = (
    "You are a helpful assistant. Use the retrieved context and the available "
    "tools. When you use retrieved context, cite the source document. If the "
    "answer is not in the context, say so instead of guessing."
)
MAX_TOOL_ROUNDS = 4
# Resolve relative to this file when run normally; when the code is embedded in
# the native binary there is no __file__, so fall back to ./src (cwd = repo root).
_HERE = (
    os.path.dirname(os.path.abspath(__file__))
    if "__file__" in globals()
    else os.path.abspath("src")
)
PROCEDURES_DIR = os.path.join(_HERE, "procedures")

app = FastAPI(title="LLM Harness Starter")
provider = default_provider()
retriever = Retriever()


class MessageRequest(BaseModel):
    message: str


def build_messages(user_message: str) -> list[dict]:
    """Assemble the prompt: base + procedures + retrieved context + question."""
    context = retriever.search(user_message, k=4)
    procedures = load_procedures(PROCEDURES_DIR, user_message)

    system = BASE_SYSTEM
    if procedures:
        system += "\n\n# Procedures\n" + procedures
    if context:
        joined = "\n\n".join(f"[doc {i + 1}]\n{c}" for i, c in enumerate(context))
        system += "\n\n# Retrieved context\n" + joined

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]


def _assistant_tool_message(result: dict) -> dict:
    """Rebuild the assistant turn that requested tool calls (for history)."""
    return {
        "role": "assistant",
        "content": result["content"],
        "tool_calls": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"]),
                },
            }
            for tc in result["tool_calls"]
        ],
    }


def run_turn(user_message: str) -> Generator[str, None, None]:
    """Resolve any tool calls, then return the final answer."""
    messages = build_messages(user_message)
    tools = tool_definitions()

    for _ in range(MAX_TOOL_ROUNDS):
        result = provider.complete(messages, tools=tools)
        if not result["tool_calls"]:
            yield result["content"] or ""
            return
        messages.append(_assistant_tool_message(result))
        for tc in result["tool_calls"]:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": call_tool(tc["name"], tc["arguments"]),
                }
            )

    # Tool budget exhausted — one final answer without tools.
    yield provider.complete(messages)["content"] or ""


@app.post("/api/chat")
def chat_endpoint(request: MessageRequest) -> StreamingResponse:
    def stream():
        try:
            yield from run_turn(request.message)
        except Exception as e:  # keep the demo alive; surface the error
            yield f"ERROR: {e}\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


def main():
    uvicorn.run(app, host="0.0.0.0", port=23239)


if __name__ == "__main__":
    main()

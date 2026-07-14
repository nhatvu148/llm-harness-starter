#include <Python.h>
#include <iostream>
#include <string>
#include <map>
#include <vector>
#include <sstream>
#include <fstream>
#include <algorithm>
#include <filesystem>

// Path to the venv's site-packages, set by CMake to match the *linked* Python
// version so the embedded interpreter and its deps never mismatch ABIs
// (see src/CMakeLists.txt). The fallback keeps a hand-compile working.
#ifndef PY_VENV_SITE_PACKAGES
#define PY_VENV_SITE_PACKAGES ".venv/lib/python3.13/site-packages"
#endif

const char* embedded_python_code = R"python(
import sys as _sys
import types as _types


def _ensure_package(name):
    module = _types.ModuleType(name)
    module.__name__, module.__path__, module.__package__ = name, [], name
    _sys.modules[name] = module
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(_sys.modules[parent], child, module)


def _register_submodule(name, source):
    module = _types.ModuleType(name)
    module.__name__, module.__package__ = name, name.rpartition(".")[0]
    _sys.modules[name] = module
    exec(compile(source, name, "exec"), module.__dict__)
    parent, _, child = name.rpartition(".")
    setattr(_sys.modules[parent], child, module)


def _exec_init(name, source):
    exec(compile(source, name, "exec"), _sys.modules[name].__dict__)


_ensure_package("providers")
_register_submodule("providers.base", "\"\"\"Provider seam \u2014 the \"model thinks\" layer.\n\nA Provider wraps any chat model behind two methods so the rest of the harness\nnever imports a vendor SDK directly. Swap the default in ``__init__.py`` to\nchange models without touching retrieval, tools, or procedures.\n\"\"\"\n\nfrom typing import Any, Iterable, Protocol\n\nMessage = dict[str, Any]  # {\"role\": ..., \"content\": ..., ...}\n\n\nclass Provider(Protocol):\n    def complete(\n        self, messages: list[Message], tools: list[dict] | None = None\n    ) -> dict:\n        \"\"\"Return a normalized result.\n\n        ``{\"content\": str | None, \"tool_calls\": [{\"id\", \"name\", \"arguments\"}]}``\n        \"\"\"\n        ...\n\n    def stream(self, messages: list[Message]) -> Iterable[str]:\n        \"\"\"Yield text chunks for a plain (no-tool) answer.\"\"\"\n        ...\n")
_register_submodule("providers.openai_provider", "\"\"\"Default provider: OpenAI. Swap this class to use a different model.\"\"\"\n\nimport json\nimport os\n\nfrom openai import OpenAI\n\nfrom .base import Message\n\n\nclass OpenAIProvider:\n    def __init__(self, model: str | None = None, api_key: str | None = None):\n        self.model = model or os.environ.get(\"MODEL\", \"gpt-4o-mini\")\n        self._api_key = api_key\n        self._client: OpenAI | None = None\n\n    @property\n    def client(self) -> OpenAI:\n        # Lazy so the server can start (and /health work) without a key set.\n        if self._client is None:\n            self._client = OpenAI(\n                api_key=self._api_key or os.environ.get(\"OPENAI_API_KEY\")\n            )\n        return self._client\n\n    def complete(\n        self, messages: list[Message], tools: list[dict] | None = None\n    ) -> dict:\n        kwargs: dict = {\"model\": self.model, \"messages\": messages}\n        if tools:\n            kwargs[\"tools\"] = tools\n        msg = self.client.chat.completions.create(**kwargs).choices[0].message\n        tool_calls = [\n            {\n                \"id\": tc.id,\n                \"name\": tc.function.name,\n                \"arguments\": json.loads(tc.function.arguments or \"{}\"),\n            }\n            for tc in (msg.tool_calls or [])\n        ]\n        return {\"content\": msg.content, \"tool_calls\": tool_calls}\n\n    def stream(self, messages: list[Message]):\n        stream = self.client.chat.completions.create(\n            model=self.model, messages=messages, stream=True\n        )\n        try:\n            for chunk in stream:\n                delta = chunk.choices[0].delta.content\n                if delta:\n                    yield delta\n        finally:\n            stream.close()\n")
_exec_init("providers", "from .base import Message, Provider\nfrom .openai_provider import OpenAIProvider\n\n\ndef default_provider() -> Provider:\n    \"\"\"The one place to change which model the harness uses.\"\"\"\n    return OpenAIProvider()\n\n\n__all__ = [\"Provider\", \"Message\", \"OpenAIProvider\", \"default_provider\"]\n")

_ensure_package("retrieval")
_register_submodule("retrieval.store", "\"\"\"Retrieval seam \u2014 the RAG layer (\"specialize\" with the right facts).\n\nDefault store: Chroma (persistent, local) with **OpenAI embeddings** \u2014 no large\nlocal model download, so ``task index`` doesn't hang on a slow connection (you\nalready need ``OPENAI_API_KEY`` for the model). For a fully offline setup, pass\na ``SentenceTransformerEmbeddingFunction`` instead. Swap the whole class to use\nQdrant, pgvector, etc. \u2014 only ``index`` and ``search`` are called.\n\"\"\"\n\nimport glob\nimport os\nimport pathlib\nimport re\n\n\ndef _chunk(text: str, size: int = 800) -> list[str]:\n    \"\"\"Group paragraphs into ~``size``-char chunks (keeps context together).\"\"\"\n    paras = [p.strip() for p in re.split(r\"\\n\\s*\\n\", text) if p.strip()]\n    chunks, buf = [], \"\"\n    for p in paras:\n        if buf and len(buf) + len(p) > size:\n            chunks.append(buf)\n            buf = p\n        else:\n            buf = f\"{buf}\\n\\n{p}\" if buf else p\n    if buf:\n        chunks.append(buf)\n    return chunks\n\n\nclass Retriever:\n    def __init__(\n        self,\n        persist_dir: str = \".chroma\",\n        collection: str = \"docs\",\n        embedding_function=None,\n    ):\n        import chromadb  # imported lazily so importing this module stays cheap\n        from chromadb.utils import embedding_functions\n\n        if embedding_function is None:\n            # OpenAI embeddings: no local model download, so indexing never\n            # hangs on a slow connection. For offline use, pass\n            # embedding_functions.SentenceTransformerEmbeddingFunction(...).\n            embedding_function = embedding_functions.OpenAIEmbeddingFunction(\n                api_key=os.environ.get(\"OPENAI_API_KEY\"),\n                model_name=os.environ.get(\"EMBED_MODEL\", \"text-embedding-3-small\"),\n            )\n\n        self.client = chromadb.PersistentClient(path=persist_dir)\n        self.collection = self.client.get_or_create_collection(\n            collection, embedding_function=embedding_function\n        )\n\n    def index(self, docs_dir: str, chunk_size: int = 800) -> int:\n        \"\"\"(Re)index every .md/.txt file under ``docs_dir``. Returns chunk count.\"\"\"\n        paths = glob.glob(os.path.join(docs_dir, \"**\", \"*.md\"), recursive=True)\n        paths += glob.glob(os.path.join(docs_dir, \"**\", \"*.txt\"), recursive=True)\n        ids, docs, metas = [], [], []\n        for p in sorted(paths):\n            text = pathlib.Path(p).read_text(encoding=\"utf-8\")\n            for i, chunk in enumerate(_chunk(text, chunk_size)):\n                ids.append(f\"{p}::{i}\")\n                docs.append(chunk)\n                metas.append({\"source\": os.path.basename(p), \"chunk\": i})\n        if ids:\n            self.collection.upsert(ids=ids, documents=docs, metadatas=metas)\n        return len(ids)\n\n    def search(self, query: str, k: int = 4) -> list[str]:\n        if self.collection.count() == 0:\n            return []\n        res = self.collection.query(query_texts=[query], n_results=k)\n        return res.get(\"documents\", [[]])[0]\n")
_exec_init("retrieval", "from .store import Retriever\n\n__all__ = [\"Retriever\"]\n")

_ensure_package("tools")
_register_submodule("tools.registry", "\"\"\"Tools seam \u2014 the \"act\" layer.\n\nEach tool has a JSON-schema definition (the same shape used by both OpenAI\nfunction-calling and MCP) plus a Python handler. Keeping tools in this shape\nmeans the same definitions can later be served over an MCP server without\nchanging any caller.\n\nThe example below is a safe calculator \u2014 a clear case of \"acting\": the model\ndelegates exact arithmetic instead of guessing it.\n\"\"\"\n\nimport ast\nimport operator\n\n_TOOLS: dict[str, dict] = {}\n\n\ndef tool(name: str, description: str, parameters: dict):\n    \"\"\"Decorator: register a handler as a callable tool.\"\"\"\n\n    def deco(fn):\n        _TOOLS[name] = {\n            \"definition\": {\n                \"type\": \"function\",\n                \"function\": {\n                    \"name\": name,\n                    \"description\": description,\n                    \"parameters\": parameters,\n                },\n            },\n            \"handler\": fn,\n        }\n        return fn\n\n    return deco\n\n\ndef definitions() -> list[dict]:\n    \"\"\"Tool schemas to pass to the model.\"\"\"\n    return [t[\"definition\"] for t in _TOOLS.values()]\n\n\ndef call(name: str, arguments: dict) -> str:\n    \"\"\"Execute a tool by name; always returns a string for the model.\"\"\"\n    if name not in _TOOLS:\n        return f\"Error: unknown tool '{name}'\"\n    try:\n        return str(_TOOLS[name][\"handler\"](**arguments))\n    except Exception as e:  # surface errors to the model so it can recover\n        return f\"Error: {e}\"\n\n\n# --- example tool -----------------------------------------------------------\n\n_OPS = {\n    ast.Add: operator.add,\n    ast.Sub: operator.sub,\n    ast.Mult: operator.mul,\n    ast.Div: operator.truediv,\n    ast.Pow: operator.pow,\n    ast.Mod: operator.mod,\n    ast.USub: operator.neg,\n}\n\n\ndef _safe_eval(node):\n    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):\n        return node.value\n    if isinstance(node, ast.BinOp):\n        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))\n    if isinstance(node, ast.UnaryOp):\n        return _OPS[type(node.op)](_safe_eval(node.operand))\n    raise ValueError(\"only numeric arithmetic is allowed\")\n\n\n@tool(\n    \"calculate\",\n    \"Evaluate an arithmetic expression exactly. Supports + - * / ** %.\",\n    {\n        \"type\": \"object\",\n        \"properties\": {\n            \"expression\": {\n                \"type\": \"string\",\n                \"description\": \"e.g. '2400 * 1.08' or '(5 + 3) ** 2'\",\n            }\n        },\n        \"required\": [\"expression\"],\n    },\n)\ndef calculate(expression: str):\n    return _safe_eval(ast.parse(expression, mode=\"eval\").body)\n")
_exec_init("tools", "# Importing registry runs the @tool registrations for the example tools.\nfrom .registry import call, definitions, tool\n\n__all__ = [\"definitions\", \"call\", \"tool\"]\n")

_ensure_package("procedures")
_register_submodule("procedures.loader", "\"\"\"Procedures seam \u2014 curated \"how-to\" injected into the prompt (\"specialize\").\n\nThe \"skill-like\" layer: your domain's steps and rules. For a small curated set\n(the common case) every procedure is included. Once the set outgrows the\ncharacter budget, procedures are ranked by keyword overlap with the query and\nthe most relevant are kept \u2014 swap in embeddings or an LLM router for smarter\nselection at scale.\n\"\"\"\n\nimport glob\nimport os\nimport pathlib\nimport re\n\n_STOPWORDS = {\n    \"the\",\n    \"a\",\n    \"an\",\n    \"is\",\n    \"are\",\n    \"of\",\n    \"to\",\n    \"for\",\n    \"and\",\n    \"or\",\n    \"in\",\n    \"on\",\n    \"at\",\n    \"it\",\n    \"this\",\n    \"that\",\n    \"what\",\n    \"how\",\n    \"do\",\n    \"does\",\n    \"with\",\n    \"you\",\n    \"your\",\n    \"i\",\n    \"my\",\n    \"can\",\n    \"be\",\n    \"as\",\n    \"by\",\n}\n\n\ndef _keywords(text: str) -> set[str]:\n    return {\n        w\n        for w in re.findall(r\"[a-z0-9]+\", text.lower())\n        if len(w) >= 3 and w not in _STOPWORDS\n    }\n\n\ndef load(procedures_dir: str, query: str, max_chars: int = 4000) -> str:\n    \"\"\"Return curated procedure text to inject into the system prompt.\"\"\"\n    paths = sorted(glob.glob(os.path.join(procedures_dir, \"*.md\")))\n    if not paths:\n        return \"\"\n    texts = [pathlib.Path(p).read_text(encoding=\"utf-8\") for p in paths]\n\n    # Small curated set (the common case): include everything.\n    if sum(len(t) for t in texts) <= max_chars:\n        return \"\\n\\n---\\n\\n\".join(texts)\n\n    # Larger set: rank by keyword overlap and keep the most relevant.\n    q = _keywords(query)\n    ranked = sorted(texts, key=lambda t: len(q & _keywords(t)), reverse=True)\n    out, total = [], 0\n    for t in ranked:\n        if total + len(t) > max_chars:\n            break\n        out.append(t)\n        total += len(t)\n    return \"\\n\\n---\\n\\n\".join(out)\n")
_exec_init("procedures", "from .loader import load\n\n__all__ = [\"load\"]\n")

# ----- api.py (runs as __main__) -----
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
PROCEDURES_DIR = os.path.join(os.path.dirname(__file__), "procedures")

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

)python";

void initialize_embedded_python_code() {
    Py_Initialize();
    if (!Py_IsInitialized()) {
        std::cerr << "Python initialization failed" << std::endl;
        exit(1);
    }
    if (PyRun_SimpleString(embedded_python_code) != 0) {
        PyErr_Print();
        std::cerr << "Failed to execute embedded Python code" << std::endl;
        Py_Finalize();
        exit(1);
    }
}

int main() {
    #ifdef _WIN32
    _putenv_s("PYTHONHOME", "Python313");
    _putenv_s("PYTHONPATH", ".venv\\Lib\\site-packages");
    #else
    setenv("PYTHONPATH", PY_VENV_SITE_PACKAGES, 1);
    #endif

    initialize_embedded_python_code();

    Py_Finalize();
    return 0;
}

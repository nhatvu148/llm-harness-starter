"""Tools seam — the "act" layer.

Each tool has a JSON-schema definition (the same shape used by both OpenAI
function-calling and MCP) plus a Python handler. Keeping tools in this shape
means the same definitions can later be served over an MCP server without
changing any caller.

The example below is a safe calculator — a clear case of "acting": the model
delegates exact arithmetic instead of guessing it.
"""

import ast
import operator

_TOOLS: dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict):
    """Decorator: register a handler as a callable tool."""

    def deco(fn):
        _TOOLS[name] = {
            "definition": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "handler": fn,
        }
        return fn

    return deco


def definitions() -> list[dict]:
    """Tool schemas to pass to the model."""
    return [t["definition"] for t in _TOOLS.values()]


def call(name: str, arguments: dict) -> str:
    """Execute a tool by name; always returns a string for the model."""
    if name not in _TOOLS:
        return f"Error: unknown tool '{name}'"
    try:
        return str(_TOOLS[name]["handler"](**arguments))
    except Exception as e:  # surface errors to the model so it can recover
        return f"Error: {e}"


# --- example tool -----------------------------------------------------------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("only numeric arithmetic is allowed")


@tool(
    "calculate",
    "Evaluate an arithmetic expression exactly. Supports + - * / ** %.",
    {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "e.g. '2400 * 1.08' or '(5 + 3) ** 2'",
            }
        },
        "required": ["expression"],
    },
)
def calculate(expression: str):
    return _safe_eval(ast.parse(expression, mode="eval").body)

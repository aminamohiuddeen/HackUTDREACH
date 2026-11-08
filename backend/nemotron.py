"""NVIDIA Nemotron client (OpenAI-compatible) with a tool-calling loop.

Env:
  NVIDIA_API_KEY  - required for live mode; missing/placeholder => mock mode
  NVIDIA_MODEL    - defaults to nvidia/nemotron-3-super-120b-a12b

chat_with_tools() returns the same shape in live and mock mode:
  {content, messages, tool_calls: [{name, args, result}], iterations, truncated}
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
MOCK_CONTENT = "mock: no tool calls executed"
_PLACEHOLDER_KEYS = {"", "your_key_here"}

_client = None


def mock_mode() -> bool:
    """True when no usable NVIDIA_API_KEY is configured."""
    return os.getenv("NVIDIA_API_KEY", "").strip() in _PLACEHOLDER_KEYS


def model_name() -> str:
    return os.getenv("NVIDIA_MODEL", "").strip() or DEFAULT_MODEL


def get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(base_url=BASE_URL, api_key=os.environ["NVIDIA_API_KEY"].strip())
    return _client


def _run_tool(fn: Callable[..., Any] | None, name: str, raw_args: str | None) -> tuple[dict, Any]:
    """Execute one tool call. Errors are returned to the model, never raised."""
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            raise ValueError("tool arguments must be a JSON object")
    except (json.JSONDecodeError, ValueError) as e:
        return {}, {"error": f"invalid arguments: {e}"}
    if fn is None:
        return args, {"error": f"unknown tool: {name}"}
    try:
        return args, fn(**args)
    except (ValueError, TypeError) as e:
        return args, {"error": str(e)}


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    max_iterations: int = 12,
    tool_functions: Mapping[str, Callable[..., Any]] | None = None,
) -> dict:
    """Run a chat completion loop, executing tool calls until the model stops.

    `tools` are OpenAI-format tool schemas; calls are dispatched through
    `tool_functions` (defaults to tools.TOOL_FUNCTIONS).
    """
    messages = list(messages)
    if mock_mode():
        return {"content": MOCK_CONTENT, "messages": messages, "tool_calls": [],
                "iterations": 0, "truncated": False}

    if tool_functions is None:
        from tools import TOOL_FUNCTIONS as tool_functions

    client = get_client()
    log: list[dict] = []
    content = ""
    for i in range(1, max_iterations + 1):
        kwargs: dict = {"model": model_name(), "messages": messages, "temperature": 0.2}
        if tools:
            kwargs["tools"] = tools
        msg = client.chat.completions.create(**kwargs).choices[0].message
        content = msg.content or ""
        calls = msg.tool_calls or []

        assistant: dict = {"role": "assistant", "content": content}
        if calls:
            assistant["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls
            ]
        messages.append(assistant)
        if not calls:
            return {"content": content, "messages": messages, "tool_calls": log,
                    "iterations": i, "truncated": False}

        for c in calls:
            name = c.function.name
            args, result = _run_tool(tool_functions.get(name), name, c.function.arguments)
            log.append({"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": c.id,
                             "content": json.dumps(result, default=str)})

    return {"content": content, "messages": messages, "tool_calls": log,
            "iterations": max_iterations, "truncated": True}

"""Helpers shared by the classifier and coordinator agents.

Tool-log entries have exactly these keys in live and mock mode:
    {agent, thought, tool, args, observation}
`observation` is always a JSON object built by summarize_observation().
`thought` is the agent's own `reasoning_summary` from the message content,
else the API's `reasoning_content` for that message, truncated to 200 chars,
or None. It is never reconstructed or invented.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

import tools

TOTAL_ITERATION_CAP = 12  # model rounds across BOTH agents
CLASSIFIER_ITERATION_BUDGET = 8  # leaves >= 4 rounds for the coordinator
THOUGHT_MAX_CHARS = 200

_SCHEMAS = {s["function"]["name"]: s for s in tools.TOOL_SCHEMAS}


def tool_schemas(names: Iterable[str]) -> list[dict]:
    return [_SCHEMAS[n] for n in names]


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def call_tool(name: str, db, **args) -> Any:
    """Call a tools.py function with the request's session. Errors become data, as in nemotron."""
    try:
        return getattr(tools, name)(**args, db=db) if name != "search_protocol" \
            else tools.search_protocol(**args)
    except (ValueError, TypeError) as e:
        return {"error": str(e)}


def bound_tool(name: str, db) -> Callable[..., Any]:
    """A tool function for nemotron.chat_with_tools with `db` injected."""
    return partial(call_tool, name, db)


def pick_survey(case) -> Any:
    """The survey classify_case() should see: latest answered, else latest (as main.reclassify)."""
    from agents.classifier import survey_responded  # lazy: classifier.py imports this module

    surveys = list(case.surveys)
    responded = [s for s in surveys if survey_responded(s)]
    return responded[-1] if responded else (surveys[-1] if surveys else None)


def summarize_observation(tool: str, result: Any) -> dict:
    """Short, deterministic JSON-object view of a tool result (identical in live and mock)."""
    if isinstance(result, dict) and set(result) == {"error"}:
        return {"error": str(result["error"])}
    if tool == "get_case_evidence" and isinstance(result, dict):
        return _json_safe({
            "case_id": result.get("case_id"), "robot_id": result.get("robot_id"),
            "sector": result.get("sector"), "classification": result.get("classification"),
            "status": result.get("status"), "signals": result.get("signals"),
            "missing_signals": result.get("missing_signals"),
            "urgent": result.get("urgent"), "urgent_reasons": result.get("urgent_reasons"),
            "has_location": result.get("location") is not None,
            "telemetry_count": len(result.get("telemetry") or []),
            "survey_count": len(result.get("surveys") or []),
            "latest_survey_answers": result.get("latest_survey_answers"),
        })
    if tool == "get_sensor_history" and isinstance(result, dict):
        return _json_safe({k: result.get(k) for k in ("robot_id", "sector", "window_minutes",
                                                      "count")})
    if tool == "get_sector_status" and isinstance(result, dict):
        return _json_safe({
            "sector": result.get("sector"), "name": result.get("name"),
            "zone_type": result.get("zone_type"), "case_counts": result.get("case_counts"),
            "total_cases": result.get("total_cases"), "urgent_cases": result.get("urgent_cases"),
            "robot_count": len(result.get("robots") or []),
            "unit_count": len(result.get("units") or []),
        })
    if tool == "search_protocol" and isinstance(result, list):
        return {"count": len(result),
                "results": [{"section_title": r.get("section_title")} for r in result]}
    if isinstance(result, list):
        return {"count": len(result), "results": _json_safe(result)}
    if isinstance(result, dict):
        return _json_safe(result)
    return {"value": _json_safe(result)}


def filter_args(tool: str, args: Any) -> dict:
    """Keep only arguments declared in the tool's schema (drops anything the model invented)."""
    if not isinstance(args, dict):
        return {}
    allowed = _SCHEMAS.get(tool, {}).get("function", {}).get("parameters", {}).get("properties")
    return _json_safe({k: v for k, v in args.items() if allowed and k in allowed})


def log_entry(agent: str, tool: str, args: dict, result: Any, thought: str | None = None) -> dict:
    return {"agent": agent, "thought": thought, "tool": tool,
            "args": filter_args(tool, args), "observation": summarize_observation(tool, result)}


def parse_json_object(text: Any) -> dict | None:
    """First JSON object in a model message, or None."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def reasoning_summary(content: Any) -> str | None:
    obj = parse_json_object(content)
    s = obj.get("reasoning_summary") if obj else None
    return s.strip() if isinstance(s, str) and s.strip() else None


def thought_for(content: Any, reasoning_content: Any) -> str | None:
    """thought for one tool call, using only text the model actually returned.

    (a) reasoning_summary in the message content, else (b) the API's
    reasoning_content for that message, (c) truncated to THOUGHT_MAX_CHARS.
    None if both are empty. Never fabricated.
    """
    text = reasoning_summary(content)
    if text is None and isinstance(reasoning_content, str) and reasoning_content.strip():
        text = reasoning_content.strip()
    return text[:THOUGHT_MAX_CHARS] if text else None


def entries_from_chat(agent: str, chat: dict, n_seed_messages: int,
                      effective_args: list[tuple[Any, dict]] | None = None) -> list[dict]:
    """Turn a chat_with_tools() result into tool-log entries, in call order.

    thought comes from thought_for(): the content of the assistant message that
    issued the call, plus that message's reasoning_content (carried on each
    tool_calls log entry). `effective_args` maps a tool result object (by
    identity) to the args actually used, for tools whose args our wrappers override.
    """
    contents: list[Any] = []
    for msg in chat.get("messages", [])[n_seed_messages:]:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            contents.extend([msg.get("content")] * len(msg["tool_calls"]))
    out = []
    for i, call in enumerate(chat.get("tool_calls", [])):
        args = call.get("args") or {}
        for result_obj, eff in effective_args or []:
            if result_obj is call.get("result"):
                args = eff
                break
        thought = thought_for(contents[i] if i < len(contents) else None,
                              call.get("reasoning_content"))
        out.append(log_entry(agent, call["name"], args, call.get("result"), thought))
    return out

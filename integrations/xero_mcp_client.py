"""Bridges the Chat page to the official Xero MCP server + an LLM tool-calling loop.

Each chat turn spawns the (patched, see patches/) `@xeroapi/xero-mcp-server`
as a stdio subprocess scoped to one tenant, lists its tools, and runs a
bounded tool-calling loop against the same Azure/OpenAI client construction
used elsewhere in this app (see helpers/batch_analyzer.py). One extra local
tool, `render_artifact`, lets the model emit a chart/table spec that never
touches the MCP server.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from openai import AzureOpenAI, OpenAI

from helpers.openai_config import (
    resolve_azure_openai_api_key,
    resolve_azure_openai_api_version,
    resolve_azure_openai_endpoint,
    resolve_openai_base_url,
    resolve_scan_deployment_name,
)
from helpers.xero_links import ENTITY_TYPES, build_entity_link

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 12  # ranking suppliers/customers by spend genuinely needs several lookups
_ARTIFACT_KINDS = ("bar", "line", "pie", "table")

RENDER_ARTIFACT_TOOL = {
    "type": "function",
    "function": {
        "name": "render_artifact",
        "description": (
            "Render a chart or table for the user, shown inline in the chat and in "
            "the artefact canvas. Use this whenever a comparison, trend, or list of "
            "rows would be clearer visually than in prose."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title for the artefact."},
                "kind": {"type": "string", "enum": list(_ARTIFACT_KINDS)},
                "insight": {
                    "type": "string",
                    "description": "Optional one-sentence caption shown under the artefact.",
                },
                "data": {
                    "description": (
                        "For kind=bar/line/pie: an array of {label, value}. "
                        "For kind=table: {columns: string[], rows: array of row arrays}."
                    ),
                },
                "row_links": {
                    "type": "array",
                    "description": (
                        "Only for kind=table. One entry per row, same order and length as "
                        "data.rows — null for a row with no matching Xero record. Each non-null "
                        "entry is {type, id} where id is the record's real Xero ID exactly as "
                        "returned by the tool call that produced this row (e.g. InvoiceID, "
                        "ContactID) — never invent an id."
                    ),
                    "items": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": list(ENTITY_TYPES)},
                                    "id": {"type": "string"},
                                },
                            },
                        ]
                    },
                },
            },
            "required": ["title", "kind", "data"],
        },
    },
}

REMEMBER_FACT_TOOL = {
    "type": "function",
    "function": {
        "name": "remember_fact",
        "description": (
            "Save one durable fact about this client for future conversations — e.g. how a "
            "recurring vendor should be classified, the fiscal year end, a quirk in how they "
            "record something. Only call this for genuinely durable, reusable facts, not "
            "one-off details from this single question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact, as one self-contained sentence."},
            },
            "required": ["fact"],
        },
    },
}

SYSTEM_PROMPT = """You are an AI assistant embedded in an accounting review portal, \
helping a UK accountant explore one specific Xero client's data (tenant id: {tenant_id}). \
You have live access to that organisation's Xero data through tools. For any question that \
depends on real figures, always call a tool to look them up rather than guessing — but for \
a greeting or small talk with no data question in it, just reply directly in one short \
sentence; do not call any tool just to have something to say. Only use create/update/delete \
tools if the user explicitly asks you to change something in Xero; default to read-only \
lookups.

If answering a question requires combining more than one lookup — e.g. ranking suppliers \
or customers by spend, which needs invoices/bills grouped by contact rather than a report \
that's only broken down by nominal account — do NOT stop and ask the user which method or \
report to use. Pick the most reasonable approach yourself, make the extra tool calls it \
takes (contacts, invoices, bank transactions — whatever's needed), and give a complete \
answer. State the assumption you made in one short line (e.g. "ranked by total spend over \
the last 12 months") so the user can redirect you if that's not what they meant — but do the \
work first. Only ask a genuine clarifying question when the request itself is ambiguous \
about WHAT the user wants (not HOW to compute it), or before a create/update/delete action.

Keep answers concise and precise, in British English, using \
£ for currency. Format your written answers in markdown (headings, bold, bullet lists, \
tables) where it aids readability. When a comparison, trend, or breakdown would be clearer \
as a chart or table, call render_artifact in addition to your written answer. Whenever a \
table lists Xero records (invoices, bills, contacts, bank transactions, credit notes, \
purchase orders), always pass row_links using each record's real ID from the tool results, \
so the user can jump straight to it in Xero. When you learn something durable and reusable \
about this client (not just an answer to this one question), call remember_fact.{memory_section}"""


def _server_path() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    return str(repo_root / "node_modules" / "@xeroapi" / "xero-mcp-server" / "dist" / "index.js")


def _llm_client():
    # Explicit timeout/max_retries (matching helpers/cash_flow_insights.py) —
    # the openai SDK's own defaults are minutes-long, which combined with up
    # to MAX_TOOL_ITERATIONS calls per turn could badly overrun whatever
    # timeout sits in front of this app, leaving the browser hanging on a
    # request that never comes back instead of a clean error.
    base_url = resolve_openai_base_url()
    if base_url:
        return OpenAI(
            base_url=base_url.rstrip("/") + "/",
            api_key=resolve_azure_openai_api_key(),
            timeout=30,
            max_retries=1,
        )
    return AzureOpenAI(
        api_key=resolve_azure_openai_api_key(),
        api_version=resolve_azure_openai_api_version(),
        azure_endpoint=resolve_azure_openai_endpoint(),
        timeout=30,
        max_retries=1,
    )


def _mcp_tool_to_openai(tool: Any) -> dict:
    schema = tool.inputSchema or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "")[:1024],
            "parameters": schema,
        },
    }


def _stringify_tool_result(result: Any) -> str:
    parts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    combined = "\n".join(parts) if parts else "(no content)"
    if getattr(result, "isError", False):
        combined = f"Error: {combined}"
    # Guard against a huge tool payload blowing the context window on the next turn.
    return combined[:8000]


def _describe_tool_call(name: str, args: dict) -> str:
    """Human-readable one-liner for the chat page's processing-log strip."""
    label = name.replace("-", " ").replace("_", " ")
    bits = []
    for key, value in list(args.items())[:2]:
        sval = str(value)
        if len(sval) > 40:
            sval = sval[:37] + "..."
        bits.append(f"{key}={sval}")
    return f"{label} ({', '.join(bits)})" if bits else label


def _sanitize_artifact(raw: dict, short_code: str | None) -> dict:
    """Never trust the model's tool-call args verbatim — clamp size/shape before storing."""
    kind = str(raw.get("kind", "table"))
    if kind not in _ARTIFACT_KINDS:
        kind = "table"
    out = {
        "kind": kind,
        "title": str(raw.get("title", "Untitled"))[:200],
        "insight": (str(raw.get("insight"))[:400] if raw.get("insight") else None),
    }
    data = raw.get("data")
    if kind == "table":
        data = data if isinstance(data, dict) else {}
        columns = data.get("columns") or []
        rows = data.get("rows") or []
        out["columns"] = [str(c)[:60] for c in columns[:20]]
        out["rows"] = [[str(cell)[:120] for cell in row[:20]] for row in rows[:200]]

        # Deep links are always rebuilt server-side from the org's real short
        # code — never trust a URL string from the model, only the {type, id}.
        row_links = raw.get("row_links") or []
        row_urls = []
        for i in range(len(out["rows"])):
            link = row_links[i] if i < len(row_links) else None
            row_urls.append(
                build_entity_link(short_code, link.get("type"), link.get("id"))
                if isinstance(link, dict)
                else None
            )
        out["row_urls"] = row_urls
    else:
        points = data if isinstance(data, list) else (data or {}).get("points", [])
        clean_points = []
        for point in points[:200]:
            if not isinstance(point, dict):
                continue
            try:
                value = float(point.get("value", 0))
            except (TypeError, ValueError):
                value = 0.0
            clean_points.append({"label": str(point.get("label", ""))[:80], "value": value})
        out["points"] = clean_points
    return out


async def _run_chat_turn_async(
    tenant_id: str,
    access_token: str,
    history: list[dict],
    short_code: str | None = None,
    memory_facts: list[str] | None = None,
) -> dict:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js runtime not found on PATH; required for the Xero MCP integration.")

    server_path = _server_path()
    if not os.path.exists(server_path):
        raise RuntimeError(
            "Xero MCP server is not installed. Run `npm install` in the project root."
        )

    params = StdioServerParameters(
        command=node,
        args=[server_path],
        env={
            **os.environ,
            "XERO_CLIENT_BEARER_TOKEN": access_token,
            "XERO_TENANT_ID": tenant_id,
        },
    )

    tool_log: list[str] = []
    artifact: dict | None = None
    remembered_facts: list[str] = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools = [_mcp_tool_to_openai(t) for t in mcp_tools] + [
                RENDER_ARTIFACT_TOOL,
                REMEMBER_FACT_TOOL,
            ]

            client = _llm_client()
            deployment_name = resolve_scan_deployment_name()

            memory_section = ""
            if memory_facts:
                bullet_list = "\n".join(f"- {fact}" for fact in memory_facts[:50])
                memory_section = f"\n\nKnown facts about this client:\n{bullet_list}"

            messages: list[dict] = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(tenant_id=tenant_id, memory_section=memory_section),
                },
                *history,
            ]

            final_text = ""
            for _ in range(MAX_TOOL_ITERATIONS):
                response = client.chat.completions.create(
                    model=deployment_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                message = response.choices[0].message

                if not message.tool_calls:
                    final_text = message.content or ""
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in message.tool_calls
                        ],
                    }
                )

                for tool_call in message.tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    if name == "render_artifact":
                        artifact = _sanitize_artifact(args, short_code)
                        result_text = f"Artefact '{artifact['title']}' rendered for the user."
                    elif name == "remember_fact":
                        fact = str(args.get("fact", "")).strip()[:500]
                        if fact:
                            remembered_facts.append(fact)
                        result_text = "Noted for future conversations." if fact else "No fact provided."
                    else:
                        tool_log.append(_describe_tool_call(name, args))
                        try:
                            mcp_result = await session.call_tool(name, args)
                            result_text = _stringify_tool_result(mcp_result)
                        except Exception as exc:
                            logger.warning("MCP tool call %s failed: %s", name, exc)
                            result_text = f"Tool call failed: {exc}"

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_text,
                        }
                    )
            else:
                final_text = (
                    final_text
                    or "I ran out of steps working through that — could you narrow the question?"
                )

    return {
        "reply": final_text,
        "artifact": artifact,
        "tool_log": tool_log,
        "remembered_facts": remembered_facts,
    }


CHAT_TURN_TIMEOUT_SECONDS = 90  # headroom for MAX_TOOL_ITERATIONS=12 worth of round trips


def run_chat_turn(
    tenant_id: str,
    access_token: str,
    history: list[dict],
    short_code: str | None = None,
    memory_facts: list[str] | None = None,
) -> dict:
    """Sync entry point for Flask routes: runs one full chat turn end to end.

    Bounded by an overall wall-clock timeout: each LLM call already has its
    own timeout, but a slow/rate-limited Xero call inside a tool round-trip
    (awaited, so this can actually cancel it) or several iterations adding up
    could otherwise run past whatever timeout sits in front of this app —
    turning into a raw dropped connection ("network error" in the browser)
    instead of the clean JSON error this raises into.
    """
    try:
        return asyncio.run(
            asyncio.wait_for(
                _run_chat_turn_async(tenant_id, access_token, history, short_code, memory_facts),
                timeout=CHAT_TURN_TIMEOUT_SECONDS,
            )
        )
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"That took longer than {CHAT_TURN_TIMEOUT_SECONDS}s to answer — try a narrower question."
        )

"""Anthropic-backed agent runner.

Uses Claude's server-side `web_search` tool for discovery, plus the local
`fetch_url` MCP tool (mcp_server/scraper_server.py) for reading the full text
of a discovered page before citing it. `web_search_ddg` (also served by the
same MCP server) is NOT exposed here: Claude already has a built-in search
tool, so it isn't needed on this path.
"""

import asyncio
import sys

import anthropic
from mcp import ClientSession

from config import ANTHROPIC_API_KEY, MAX_TOKENS, MODEL_NAME
from providers.base import RunResult

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

# Safety cap on the agentic loop so a misbehaving run can't spin forever.
MAX_ITERATIONS = 40


def _mcp_tools_to_anthropic(mcp_tools) -> list[dict]:
    """Convert MCP tool descriptors into Anthropic custom-tool definitions."""
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }
        for tool in mcp_tools
    ]


def _tool_result_text(result) -> str:
    """Flatten an MCP call_tool result into plain text for a tool_result block."""
    parts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no textual content returned)"


async def run_agent(
    session: ClientSession | None,
    system_prompt: str,
    company_input: str,
    *,
    model: str | None = None,
    enable_tools: bool = True,
) -> RunResult:
    """Drive the agentic loop until the model finishes; return the final text."""
    model_name = model or MODEL_NAME

    tools: list[dict] = []
    if enable_tools:
        if session is None:
            raise ValueError("enable_tools=True requires an MCP session.")
        await session.initialize()
        all_mcp_tools = (await session.list_tools()).tools
        # Only expose fetch_url here — discovery already comes from web_search.
        fetch_tools = [t for t in all_mcp_tools if t.name == "fetch_url"]
        tools = [WEB_SEARCH_TOOL, *_mcp_tools_to_anthropic(fetch_tools)]

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict] = [{"role": "user", "content": company_input}]

    response = None
    try:
        for _ in range(MAX_ITERATIONS):
            response = await client.messages.create(
                model=model_name,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )

            if response.stop_reason == "tool_use":
                # Client-side tool calls (the MCP fetch_url tool). Server-side
                # web_search results are already inline in response.content.
                messages.append({"role": "assistant", "content": response.content})
                assert session is not None  # tool_use only happens when enable_tools=True

                async def _run(block):
                    print(f"  → fetch tool: {block.name}({block.input})", file=sys.stderr)
                    result = await session.call_tool(block.name, dict(block.input))
                    return {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _tool_result_text(result),
                        "is_error": bool(result.isError),
                    }

                # Claude often issues several fetch_url calls in the same turn
                # (e.g. reading multiple sources to triangulate) — run them
                # concurrently instead of awaiting one at a time.
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                tool_results = await asyncio.gather(*(_run(block) for block in tool_use_blocks))
                messages.append({"role": "user", "content": list(tool_results)})
                continue

            if response.stop_reason == "pause_turn":
                # A long server-side web_search turn paused; re-send to resume it.
                messages.append({"role": "assistant", "content": response.content})
                continue

            # end_turn, max_tokens, refusal, ... — stop looping.
            break
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Cannot reach Anthropic. Check your network connection and ANTHROPIC_API_KEY.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic request failed ({exc.status_code}): {exc.message}") from exc

    text = "".join(b.text for b in response.content if b.type == "text") if response else ""
    return RunResult(
        text=text,
        model=model_name,
        stop_reason=response.stop_reason if response else None,
        truncated=bool(response and response.stop_reason == "max_tokens"),
    )

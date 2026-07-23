"""Anthropic-backed agent runner.

Uses Claude's server-side `web_search` tool for discovery, plus the local
`fetch_url` MCP tool (mcp_server/scraper_server.py) for reading the full text
of a discovered page before citing it. `web_search_ddg` (also served by the
same MCP server) is NOT exposed here: Claude already has a built-in search
tool, so it isn't needed on this path.
"""

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


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Drive the agentic loop until the model finishes; return the final text."""
    await session.initialize()
    all_mcp_tools = (await session.list_tools()).tools
    # Only expose fetch_url here — discovery already comes from web_search.
    fetch_tools = [t for t in all_mcp_tools if t.name == "fetch_url"]
    tools = [WEB_SEARCH_TOOL, *_mcp_tools_to_anthropic(fetch_tools)]

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict] = [{"role": "user", "content": company_input}]

    response = None
    for _ in range(MAX_ITERATIONS):
        response = await client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        if response.stop_reason == "tool_use":
            # Client-side tool calls (the MCP fetch_url tool). Server-side
            # web_search results are already inline in response.content.
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  → fetch tool: {block.name}({block.input})", file=sys.stderr)
                    result = await session.call_tool(block.name, dict(block.input))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _tool_result_text(result),
                            "is_error": bool(result.isError),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "pause_turn":
            # A long server-side web_search turn paused; re-send to resume it.
            messages.append({"role": "assistant", "content": response.content})
            continue

        # end_turn, max_tokens, refusal, ... — stop looping.
        break

    text = "".join(b.text for b in response.content if b.type == "text") if response else ""
    return RunResult(
        text=text,
        model=MODEL_NAME,
        stop_reason=response.stop_reason if response else None,
        truncated=bool(response and response.stop_reason == "max_tokens"),
    )

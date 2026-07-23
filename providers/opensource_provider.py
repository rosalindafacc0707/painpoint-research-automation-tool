"""Open-source / self-hosted model runner (e.g. GPT-OSS via Ollama, or any
OpenAI-compatible endpoint: vLLM, LM Studio, Groq, Together, ...).

Unlike the Anthropic path, these runtimes have no built-in server-side web
search. So this provider exposes TWO local MCP tools instead of one:
  - web_search_ddg — discovery (DuckDuckGo, no API key required)
  - fetch_url      — reading the full text of a discovered page

Requires an OpenAI-compatible /v1/chat/completions endpoint with tool-calling
support. For local Ollama with GPT-OSS:
    ollama pull gpt-oss:20b
    ollama serve
(OPENSOURCE_BASE_URL defaults to http://localhost:11434/v1 — see config.py)
"""

import json
import sys

from mcp import ClientSession
from openai import AsyncOpenAI

from config import MAX_TOKENS, OPENSOURCE_API_KEY, OPENSOURCE_BASE_URL, OPENSOURCE_MODEL
from providers.base import RunResult

MAX_ITERATIONS = 40


def _mcp_tools_to_openai(mcp_tools) -> list[dict]:
    """Convert MCP tool descriptors into OpenAI function-calling definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _tool_result_text(result) -> str:
    """Flatten an MCP call_tool result into plain text for a tool message."""
    parts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no textual content returned)"


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Drive the agentic loop until the model finishes; return the final text."""
    await session.initialize()
    mcp_tools = (await session.list_tools()).tools  # web_search_ddg + fetch_url
    tools = _mcp_tools_to_openai(mcp_tools)

    client = AsyncOpenAI(base_url=OPENSOURCE_BASE_URL, api_key=OPENSOURCE_API_KEY)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": company_input},
    ]

    response = None
    for _ in range(MAX_ITERATIONS):
        response = await client.chat.completions.create(
            model=OPENSOURCE_MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
            tools=tools,
        )
        choice = response.choices[0]
        message = choice.message

        if choice.finish_reason == "tool_calls" and message.tool_calls:
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                print(f"  → tool: {call.function.name}({args})", file=sys.stderr)
                result = await session.call_tool(call.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": _tool_result_text(result),
                    }
                )
            continue

        # stop / length / content_filter, ... — stop looping.
        break

    if response is None:
        return RunResult(text="", model=OPENSOURCE_MODEL, stop_reason=None)

    final_message = response.choices[0].message
    finish_reason = response.choices[0].finish_reason
    return RunResult(
        text=final_message.content or "",
        model=OPENSOURCE_MODEL,
        stop_reason=finish_reason,
        truncated=(finish_reason == "length"),
    )

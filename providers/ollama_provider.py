"""Local open-weight agent runner backed by Ollama's native chat API."""

import asyncio
import json
import sys

import httpx
from mcp import ClientSession

from config import (
    MAX_TOKENS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT_SECONDS,
)
from providers.base import RunResult

MAX_ITERATIONS = 40

# The shared system prompt (prompts/system_prompt_v6.md) tells the model to
# call a discovery tool named "web_search" — matching Claude's built-in tool
# name, since that's the provider the prompt was originally written for.
# Ollama has no built-in web search: discovery is served locally by the MCP
# tool `web_search_ddg` (mcp_server/scraper_server.py). Present it to the
# model under the name the prompt actually uses, and map back to the real
# MCP tool name when dispatching the call — without this, the model calls
# "web_search" (as instructed) but that name isn't in its tool list, so the
# MCP session logs "Tool 'web_search' not listed" and the call never reaches
# the actual search tool.
_PROMPT_NAME_TO_MCP_NAME = {"web_search": "web_search_ddg"}


def _mcp_tools_to_ollama(mcp_tools) -> list[dict]:
    """Convert MCP tool descriptors into Ollama's native tool schema."""
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search" if tool.name == "web_search_ddg" else tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _tool_result_text(result) -> str:
    parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no textual content returned)"


def _tool_arguments(arguments) -> dict:
    """Accept either the normal JSON object or a string from a faulty model."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        parsed = json.loads(arguments or "{}")
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Tool arguments must be a JSON object.")


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Run the local model and execute any requested local MCP tools."""
    await session.initialize()
    mcp_tools = (await session.list_tools()).tools
    tools = _mcp_tools_to_ollama(mcp_tools)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": company_input},
    ]
    request_options = {
        "num_ctx": OLLAMA_NUM_CTX,
        "num_predict": MAX_TOKENS,
        "temperature": OLLAMA_TEMPERATURE,
    }

    response: dict | None = None
    endpoint = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            for _ in range(MAX_ITERATIONS):
                http_response = await client.post(
                    endpoint,
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": messages,
                        "tools": tools,
                        "stream": False,
                        "keep_alive": "10m",
                        "options": request_options,
                    },
                )
                http_response.raise_for_status()
                response = http_response.json()
                assistant_message = response.get("message") or {}
                tool_calls = assistant_message.get("tool_calls") or []
                if not tool_calls:
                    break

                # The exact assistant tool-call message must appear in history
                # before the tool-role responses.
                messages.append(assistant_message)

                async def _run(call):
                    function = call.get("function") or {}
                    name = function.get("name")
                    if not name:
                        raise ValueError("Ollama returned a tool call without a function name.")
                    args = _tool_arguments(function.get("arguments", {}))
                    print(f"  → tool: {name}({args})", file=sys.stderr)
                    mcp_name = _PROMPT_NAME_TO_MCP_NAME.get(name, name)
                    result = await session.call_tool(mcp_name, args)
                    return {
                        "role": "tool",
                        "tool_name": name,
                        "content": _tool_result_text(result),
                    }

                messages.extend(await asyncio.gather(*(_run(call) for call in tool_calls)))
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. Start Ollama and pull {OLLAMA_MODEL}."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise RuntimeError(f"Ollama chat request failed ({exc.response.status_code}): {detail}") from exc

    if response is None:
        return RunResult(text="", model=OLLAMA_MODEL, stop_reason=None)

    message = response.get("message") or {}
    stop_reason = response.get("done_reason")
    return RunResult(
        text=message.get("content") or "",
        model=response.get("model") or OLLAMA_MODEL,
        stop_reason=stop_reason,
        truncated=stop_reason in {"length", "max_tokens"},
    )

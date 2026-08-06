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
    OLLAMA_THINK,
    OLLAMA_TIMEOUT_SECONDS,
)
from providers.base import RunResult

MAX_ITERATIONS = 40


def _mcp_tools_to_ollama(mcp_tools) -> list[dict]:
    """Convert MCP tool descriptors into Ollama's native tool schema."""
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


async def run_agent(
    session: ClientSession | None,
    system_prompt: str,
    company_input: str,
    *,
    model: str | None = None,
    enable_tools: bool = True,
) -> RunResult:
    """Run the local model and execute any requested local MCP tools."""
    model_name = model or OLLAMA_MODEL

    tools: list[dict] = []
    if enable_tools:
        if session is None:
            raise ValueError("enable_tools=True requires an MCP session.")
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
                        "model": model_name,
                        "messages": messages,
                        "tools": tools,
                        "think": OLLAMA_THINK,
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
                assert session is not None  # tool_calls is non-empty only when enable_tools=True

                async def _run(call):
                    function = call.get("function") or {}
                    name = function.get("name")
                    if not name:
                        raise ValueError("Ollama returned a tool call without a function name.")
                    args = _tool_arguments(function.get("arguments", {}))
                    print(f"  → tool: {name}({args})", file=sys.stderr)
                    result = await session.call_tool(name, args)
                    return {
                        "role": "tool",
                        "tool_name": name,
                        "content": _tool_result_text(result),
                    }

                messages.extend(await asyncio.gather(*(_run(call) for call in tool_calls)))
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. Start Ollama and pull {model_name}."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise RuntimeError(f"Ollama chat request failed ({exc.response.status_code}): {detail}") from exc

    if response is None:
        return RunResult(text="", model=model_name, stop_reason=None)

    message = response.get("message") or {}
    stop_reason = response.get("done_reason")
    return RunResult(
        text=message.get("content") or "",
        model=response.get("model") or model_name,
        stop_reason=stop_reason,
        truncated=stop_reason in {"length", "max_tokens"},
    )

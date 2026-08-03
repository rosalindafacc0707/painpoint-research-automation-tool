"""High-speed Groq runner for hosted open-weight models.

The default, openai/gpt-oss-120b, is an open-weight 120B model served by
Groq's OpenAI-compatible API. It retains the project's local MCP research
tools while avoiding the latency of local inference on a 16 GB laptop.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MAX_COMPLETION_TOKENS,
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
    GROQ_TOOL_RESULT_MAX_CHARS,
    GROQ_TPM_LIMIT,
)
from providers.base import RunResult

MAX_ITERATIONS = 40


def _mcp_tools_to_chat_completions(mcp_tools) -> list[dict]:
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
    text = "\n".join(parts) if parts else "(no textual content returned)"
    if len(text) <= GROQ_TOOL_RESULT_MAX_CHARS:
        return text
    return (
        text[:GROQ_TOOL_RESULT_MAX_CHARS]
        + f"\n\n[Tool result truncated to {GROQ_TOOL_RESULT_MAX_CHARS} characters for Groq TPM limits.]"
    )


def _max_completion_tokens(messages: list[dict], tools: list[dict]) -> int:
    """Reserve an output budget that stays inside the configured Groq TPM cap.

    Groq rejects a request when prompt tokens plus requested completion tokens
    exceed the account's current TPM allowance.  We use a conservative
    character estimate because exact tokenization is provider-side.
    """
    payload_chars = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False))
    estimated_input_tokens = payload_chars // 3
    available = GROQ_TPM_LIMIT - estimated_input_tokens - 250
    max_tokens = min(GROQ_MAX_COMPLETION_TOKENS, available)
    if max_tokens < 512:
        raise RuntimeError(
            "Groq's TPM limit is too small for the accumulated research context. "
            "Upgrade the Groq tier, raise GROQ_TPM_LIMIT to match it, or start a new run."
        )
    return max_tokens


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Run the Groq model and execute MCP tool calls until it completes."""
    if not GROQ_API_KEY:
        raise RuntimeError("Groq is not configured. Set GROQ_API_KEY in the .env file.")

    await session.initialize()
    tools = _mcp_tools_to_chat_completions((await session.list_tools()).tools)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": company_input},
    ]
    client = AsyncOpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY)

    response = None
    try:
        for _ in range(MAX_ITERATIONS):
            max_completion_tokens = _max_completion_tokens(messages, tools)
            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=False,
                max_completion_tokens=max_completion_tokens,
                reasoning_effort=GROQ_REASONING_EFFORT,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                break

            messages.append(message.model_dump(exclude_none=True))

            async def _run(call):
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Groq returned invalid arguments for tool {call.function.name}: {exc}"
                    ) from exc
                print(f"  → tool: {call.function.name}({args})", file=sys.stderr)
                result = await session.call_tool(call.function.name, args)
                return {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": _tool_result_text(result),
                }

            messages.extend(await asyncio.gather(*(_run(call) for call in tool_calls)))
    except APIConnectionError as exc:
        raise RuntimeError("Cannot reach Groq. Check your network connection and GROQ_API_KEY.") from exc
    except APIStatusError as exc:
        raise RuntimeError(f"Groq request failed ({exc.status_code}): {exc.message}") from exc

    if response is None:
        return RunResult(text="", model=GROQ_MODEL, stop_reason=None)

    choice = response.choices[0]
    return RunResult(
        text=choice.message.content or "",
        model=response.model or GROQ_MODEL,
        stop_reason=choice.finish_reason,
        truncated=choice.finish_reason == "length",
    )

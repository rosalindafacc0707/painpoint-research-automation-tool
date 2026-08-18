"""Mistral La Plateforme agent runner (OpenAI-compatible chat completions).

Mistral's `/v1/chat/completions` endpoint mirrors the OpenAI chat
completions shape closely enough that the plain `openai.AsyncOpenAI`
client works against it directly — same approach already used by
providers/azure_provider.py and providers/groq_provider.py — no need for
the dedicated `mistralai` SDK.

Mistral has no built-in server-side web search (unlike Claude), so this
provider uses the same two local MCP tools as Azure/Gemini/Groq:
  - web_search_ddg — discovery
  - fetch_url      — reading a known URL's full text
Exposed under their real MCP names (no renaming to "web_search"), matching
the Azure/Gemini providers — both already verified live to work fine even
though the shared research prompt refers to the tool conceptually as
"web_search".

Required config (see config.py / .env):
  - MISTRAL_API_KEY (secret — .env)
Optional (see .env.development):
  - MISTRAL_MODEL (default: mistral-small-latest)

Mistral's "Experiment" free tier needs no credit card (phone verification
only) and has a large monthly token allowance, but its per-minute request
rate is not clearly documented and conflicts across sources — verify live
before relying on it under this project's 3-way concurrent research load.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from config import MISTRAL_API_KEY, MISTRAL_BASE_URL, MISTRAL_MODEL
from providers.base import RunResult

MAX_ITERATIONS = 40

MAX_MODEL_RETRIES = 3
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def _create_completion(client: AsyncOpenAI, create_kwargs: dict):
    """Create a completion, retrying transient errors (429/5xx)."""
    for attempt in range(MAX_MODEL_RETRIES):
        is_last_attempt = attempt == MAX_MODEL_RETRIES - 1
        try:
            return await client.chat.completions.create(**create_kwargs)
        except APIStatusError as exc:
            if exc.status_code not in _RETRYABLE_STATUS_CODES or is_last_attempt:
                raise
            print(
                f"  ⟲ retrying Mistral request after {exc.status_code} ({attempt + 1}/{MAX_MODEL_RETRIES})",
                file=sys.stderr,
            )
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable: the last retry attempt always returns or raises")


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
    return "\n".join(parts) if parts else "(no textual content returned)"


async def run_agent(
    session: ClientSession | None,
    system_prompt: str,
    company_input: str,
    *,
    model: str | None = None,
    enable_tools: bool = True,
) -> RunResult:
    """Run the Mistral model and execute MCP tool calls until it completes."""
    if not MISTRAL_API_KEY:
        raise RuntimeError("Mistral is not configured. Set MISTRAL_API_KEY in the .env file.")
    model_name = model or MISTRAL_MODEL

    tools: list[dict] = []
    if enable_tools:
        if session is None:
            raise ValueError("enable_tools=True requires an MCP session.")
        await session.initialize()
        tools = _mcp_tools_to_chat_completions((await session.list_tools()).tools)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": company_input},
    ]
    client = AsyncOpenAI(base_url=MISTRAL_BASE_URL, api_key=MISTRAL_API_KEY)

    response = None
    try:
        for _ in range(MAX_ITERATIONS):
            create_kwargs = {"model": model_name, "messages": messages}
            if tools:
                create_kwargs.update(tools=tools, tool_choice="auto")
            response = await _create_completion(client, create_kwargs)
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                break

            messages.append(message.model_dump(exclude_none=True))
            assert session is not None  # tool_calls is non-empty only when enable_tools=True

            async def _run(call):
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Mistral returned invalid arguments for tool {call.function.name}: {exc}"
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
        raise RuntimeError("Cannot reach Mistral. Check your network connection and MISTRAL_API_KEY.") from exc
    except APIStatusError as exc:
        raise RuntimeError(f"Mistral request failed ({exc.status_code}): {exc.message}") from exc

    if response is None:
        return RunResult(text="", model=model_name, stop_reason=None)

    choice = response.choices[0]
    return RunResult(
        text=choice.message.content or "",
        model=response.model or model_name,
        stop_reason=choice.finish_reason,
        truncated=choice.finish_reason == "length",
    )

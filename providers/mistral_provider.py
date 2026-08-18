"""Mistral La Plateforme agent runner.

Mistral's `/v1/chat/completions` endpoint follows the same request/response
shape as OpenAI's Chat Completions API (including the "tools" /
"tool_choice" function-calling schema), so this provider reuses the
`openai.AsyncOpenAI` client with a custom `base_url`, the same approach used
for Groq (providers/groq_provider.py) and Azure (providers/azure_provider.py)
instead of installing the separate `mistralai` SDK.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from config import (
    MAX_TOKENS,
    MISTRAL_API_KEY,
    MISTRAL_BASE_URL,
    MISTRAL_MAX_RETRIES,
    MISTRAL_MODEL,
    MISTRAL_RETRY_BASE_SECONDS,
)
from providers.base import RunResult

MAX_ITERATIONS = 40

# The shared system prompt (prompts/system_prompt_v6.md) tells the model to
# call a discovery tool named "web_search" — matching Claude's built-in tool
# name, since that's the provider the prompt was originally written for.
# Mistral has no built-in web search: discovery is served locally by the MCP
# tool `web_search_ddg` (mcp_server/scraper_server.py). Present it to Mistral
# under the name the prompt actually uses, and map back to the real MCP tool
# name when dispatching the call.
_PROMPT_NAME_TO_MCP_NAME = {"web_search": "web_search_ddg"}


def _mcp_tools_to_chat_completions(mcp_tools) -> list[dict]:
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


def _retry_after_seconds(exc: RateLimitError) -> float | None:
    """Read Mistral's own Retry-After header, if it sent one."""
    header = exc.response.headers.get("retry-after")
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


async def _create_completion_with_retry(client: AsyncOpenAI, **kwargs):
    """Call chat.completions.create, retrying on HTTP 429 with backoff.

    Mistral's rate limit under this agent's bursty tool-call pattern
    (several parallel web_search calls per turn, back-to-back completions)
    was observed to trigger 429s within seconds of starting a run — without
    a retry, that aborts the whole report. Prefers Mistral's own
    Retry-After header when present; otherwise doubles the wait each
    attempt (2s, 4s, 8s, ...).
    """
    for attempt in range(1, MISTRAL_MAX_RETRIES + 1):
        try:
            return await client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            if attempt == MISTRAL_MAX_RETRIES:
                raise
            delay = _retry_after_seconds(exc) or MISTRAL_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            print(
                f"  ⚠ Mistral rate limited (429) — retrying in {delay:.1f}s "
                f"(attempt {attempt}/{MISTRAL_MAX_RETRIES})",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Run the Mistral model and execute MCP tool calls until it completes."""
    if not MISTRAL_API_KEY:
        raise RuntimeError("Mistral is not configured. Set MISTRAL_API_KEY in the .env file.")

    print(f"▶ Using model: {MISTRAL_MODEL}", file=sys.stderr)
    await session.initialize()
    tools = _mcp_tools_to_chat_completions((await session.list_tools()).tools)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": company_input},
    ]
    # max_retries=0: retries are handled explicitly by
    # _create_completion_with_retry below, so a 429 doesn't get retried
    # twice (once silently by the SDK, once by us) with two different,
    # confusing backoff schedules.
    client = AsyncOpenAI(base_url=MISTRAL_BASE_URL, api_key=MISTRAL_API_KEY, max_retries=0)

    response = None
    try:
        for _ in range(MAX_ITERATIONS):
            response = await _create_completion_with_retry(
                client,
                model=MISTRAL_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
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
                        f"Mistral returned invalid arguments for tool {call.function.name}: {exc}"
                    ) from exc
                tool_name = call.function.name
                print(f"  → tool: {tool_name}({args})", file=sys.stderr)
                mcp_name = _PROMPT_NAME_TO_MCP_NAME.get(tool_name, tool_name)
                result = await session.call_tool(mcp_name, args)
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
        return RunResult(text="", model=MISTRAL_MODEL, stop_reason=None)

    choice = response.choices[0]
    return RunResult(
        text=choice.message.content or "",
        model=response.model or MISTRAL_MODEL,
        stop_reason=choice.finish_reason,
        truncated=choice.finish_reason == "length",
    )

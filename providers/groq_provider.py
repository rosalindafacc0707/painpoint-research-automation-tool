"""High-speed Groq runner for hosted open-weight models.

Groq's LPU inference hardware is much faster than local Ollama inference on
this 16 GB laptop, and its free tier needs no payment method (unlike
Cerebras). Two tradeoffs, both confirmed live against this account (this is
also the exact reason a Groq provider was removed once already — see
prompts/CHANGELOG.md v8):

1. llama-3.3-70b-versatile's tool-calling is unreliable on Groq — it
   intermittently (~1 in 6 tool-enabled requests in local testing,
   unaffected by temperature or tool name/count/system prompt) emits its
   own pythonic `<function=name>{...}</function>` tag instead of a real
   OpenAI-style tool call: sometimes as a loud 400 `tool_use_failed` error,
   sometimes silently inside `message.content` with `tool_calls` empty,
   which would otherwise pass through as if it were a genuine final answer.
   `_create_completion` retries on both failure shapes since resampling
   usually recovers, but even 3 retries still failed on ~2/3 of adversarial
   test calls — nowhere near reliable enough for the research role, which
   needs a tool call to succeed on every turn. `openai/gpt-oss-120b` is
   Groq's own recommended model for reliable tool use and is the default
   here for that reason; llama-3.3-70b-versatile remains available (set
   GROQ_MODEL explicitly) but is best reserved for the synthesis role,
   which never calls a tool at all (enable_tools=False) and so is
   unaffected by this bug.
2. The free tier's RPM cap (~30 RPM for either model above) is easy to blow
   through instantly: 8 parallel research agents all firing their first
   request within the same second immediately exceeds it, independent of
   the TPM budget below. `_RateLimiter` paces every request from this
   process (shared module-level state, since all 8 agents run as asyncio
   tasks in one process — see services/multiagent_service.py) so the
   aggregate request rate stays under GROQ_RPM_LIMIT regardless of how many
   agents are calling concurrently.

The TPM-budget guard and tool-result compaction below (`_max_completion_tokens`,
`_compact_oldest_tool_result`) exist to survive GROQ_TPM_LIMIT (8000, the
allowance actually observed on this account) within a single long
multi-tool-call research run. If a run still fails after all of the above,
the option is ollama (no external limit of any kind) or a paid Groq tier.
"""

import asyncio
import json
import re
import sys
import time

from mcp import ClientSession
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MAX_COMPLETION_TOKENS,
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
    GROQ_RPM_LIMIT,
    GROQ_TOOL_RESULT_MAX_CHARS,
    GROQ_TPM_LIMIT,
)
from providers.base import RunResult

MAX_ITERATIONS = 40

MAX_MODEL_RETRIES = 3
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MALFORMED_TOOL_CALL_RE = re.compile(r"<function[=(]")


class _RateLimiter:
    """Paces requests to at most `rpm` per rolling minute across every
    concurrent caller in this process, via a single shared next-slot
    timestamp. Needed because 8 parallel research agents each start their
    own first request within the same second — without this, all 8 hit
    Groq's RPM cap immediately (confirmed live) regardless of the TPM guard,
    which only limits the size of each request, not how often they fire.
    """

    def __init__(self, rpm: int):
        self._min_interval = 60.0 / rpm
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._min_interval
        delay = start - now
        if delay > 0:
            await asyncio.sleep(delay)


_rate_limiter = _RateLimiter(GROQ_RPM_LIMIT)


def _is_tool_use_failed(exc: APIStatusError) -> bool:
    body = exc.body
    return (
        exc.status_code == 400
        and isinstance(body, dict)
        and body.get("error", {}).get("code") == "tool_use_failed"
    )


async def _create_completion(client: AsyncOpenAI, create_kwargs: dict):
    """Create a completion, retrying transient errors and the malformed
    pythonic-tag quirk described in the module docstring. `tools_requested`
    gates the content check: that quirk only matters when tools were
    actually offered, since plain-text answers never populate tool_calls.
    """
    tools_requested = bool(create_kwargs.get("tools"))
    for attempt in range(MAX_MODEL_RETRIES):
        is_last_attempt = attempt == MAX_MODEL_RETRIES - 1
        await _rate_limiter.wait()
        try:
            response = await client.chat.completions.create(**create_kwargs)
        except APIStatusError as exc:
            if not (_is_tool_use_failed(exc) or exc.status_code in _RETRYABLE_STATUS_CODES) or is_last_attempt:
                raise
            print(
                f"  ⟲ retrying Groq request after {exc.status_code} ({attempt + 1}/{MAX_MODEL_RETRIES})",
                file=sys.stderr,
            )
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        message = response.choices[0].message
        malformed = (
            tools_requested
            and not message.tool_calls
            and message.content
            and _MALFORMED_TOOL_CALL_RE.search(message.content)
        )
        if malformed and is_last_attempt:
            raise RuntimeError(
                f"Groq ({create_kwargs.get('model')}) repeatedly emitted a malformed pythonic "
                f"tool-call tag instead of a real tool call: {message.content!r}"
            )
        if malformed:
            print(
                f"  ⟲ retrying Groq request: malformed tool-call tag in content "
                f"({attempt + 1}/{MAX_MODEL_RETRIES})",
                file=sys.stderr,
            )
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        return response
    raise RuntimeError("unreachable: the last retry attempt always returns or raises")


# The shared research prompt (prompts/multiagent_research_prompt.md) calls a
# discovery tool named "web_search" (matching Claude's built-in tool name).
# Groq has no built-in web search, so discovery is served locally by the MCP
# tool `web_search_ddg`/Tavily (see mcp_server/scraper_server.py). Expose it
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
    text = "\n".join(parts) if parts else "(no textual content returned)"
    if len(text) <= GROQ_TOOL_RESULT_MAX_CHARS:
        return text
    return text[:GROQ_TOOL_RESULT_MAX_CHARS] + (
        f"\n\n[Tool result truncated to {GROQ_TOOL_RESULT_MAX_CHARS} characters for Groq TPM limits.]"
    )


GROQ_MIN_COMPLETION_TOKENS = 512
_COMPACTED_TOOL_RESULT = (
    "[compacted to stay within the Groq TPM budget — already used earlier in this research]"
)


def _compact_oldest_tool_result(messages: list[dict], name: str) -> bool:
    """Shrink the oldest not-yet-compacted tool message with the given name.

    Returns False if there is nothing left of that kind to compact.
    """
    for msg in messages:
        if (
            msg.get("role") == "tool"
            and msg.get("name") == name
            and len(msg.get("content", "")) > len(_COMPACTED_TOOL_RESULT)
        ):
            msg["content"] = _COMPACTED_TOOL_RESULT
            print(f"  → compacting an older {name} result to free up TPM budget", file=sys.stderr)
            return True
    return False


def _max_completion_tokens(messages: list[dict], tools: list[dict]) -> int:
    """Reserve an output budget that stays inside the configured Groq TPM cap.

    Groq rejects a request when prompt tokens plus requested completion tokens
    exceed the account's current TPM allowance. We use a conservative
    character estimate because exact tokenization is provider-side.

    Research runs accumulate tool results across many iterations, so the
    payload can grow past the budget well before the run is done. Rather
    than aborting immediately, shrink older tool results in place (mutating
    `messages`) until the request fits. `web_search` snippets are only
    needed for discovery and become redundant once their URLs have been read
    via `fetch_url`, so those are compacted first; `fetch_url` results are
    the actual cited evidence, so they're only compacted as a last resort.
    """
    while True:
        payload_chars = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False))
        estimated_input_tokens = payload_chars // 3
        available = GROQ_TPM_LIMIT - estimated_input_tokens - 250
        max_tokens = min(GROQ_MAX_COMPLETION_TOKENS, available)
        if max_tokens >= GROQ_MIN_COMPLETION_TOKENS:
            return max_tokens
        if _compact_oldest_tool_result(messages, "web_search"):
            continue
        if _compact_oldest_tool_result(messages, "fetch_url"):
            continue
        raise RuntimeError(
            "Groq's TPM limit is too small for the accumulated research context, "
            "even after compacting earlier tool results. Upgrade the Groq tier, "
            "raise GROQ_TPM_LIMIT to match it, or start a new run."
        )


async def run_agent(
    session: ClientSession | None,
    system_prompt: str,
    company_input: str,
    *,
    model: str | None = None,
    enable_tools: bool = True,
) -> RunResult:
    """Run the Groq model and execute MCP tool calls until it completes."""
    if not GROQ_API_KEY:
        raise RuntimeError("Groq is not configured. Set GROQ_API_KEY in the .env file.")
    model_name = model or GROQ_MODEL

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
    client = AsyncOpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY)

    response = None
    try:
        for _ in range(MAX_ITERATIONS):
            create_kwargs = {
                "model": model_name,
                "messages": messages,
                "max_completion_tokens": _max_completion_tokens(messages, tools),
            }
            if "gpt-oss" in model_name:
                # GPT-OSS is a hybrid reasoning model; Llama models don't
                # accept this param at all, so it's only sent conditionally.
                create_kwargs["reasoning_effort"] = GROQ_REASONING_EFFORT
            if tools:
                create_kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
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
                        f"Groq returned invalid arguments for tool {call.function.name}: {exc}"
                    ) from exc
                if not call.function.name:
                    raise RuntimeError("Groq returned a tool call without a function name.")
                tool_name = str(call.function.name)
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
        raise RuntimeError("Cannot reach Groq. Check your network connection and GROQ_API_KEY.") from exc
    except APIStatusError as exc:
        raise RuntimeError(f"Groq request failed ({exc.status_code}): {exc.message}") from exc

    if response is None:
        return RunResult(text="", model=model_name, stop_reason=None)

    choice = response.choices[0]
    return RunResult(
        text=choice.message.content or "",
        model=response.model or model_name,
        stop_reason=choice.finish_reason,
        truncated=choice.finish_reason == "length",
    )

"""Mistral La Plateforme agent runner — two models, two phases.

Mistral's `/v1/chat/completions` endpoint follows the same request/response
shape as OpenAI's Chat Completions API (including the "tools" /
"tool_choice" function-calling schema), so this provider reuses the
`openai.AsyncOpenAI` client with a custom `base_url`, the same approach used
for Azure (providers/azure_provider.py) instead of installing the separate
`mistralai` SDK.

La Plateforme's per-model rate limits differ by two orders of magnitude
(checked live in the account console): mistral-large-2512 allows only
~0.07 requests/second (about 1 every 14s), while ministral-8b-2512 allows
~3.13 req/s. This agent's research loop fires several back-to-back
completions — one per tool-call turn, batched web_search/fetch_url calls
in between — which exhausted Large's budget within seconds (HTTP 429 even
after 30s of retry/backoff). So the work is split across two phases with
two different models (config.py):
  1. Research phase (MISTRAL_RESEARCH_MODEL, ministral-8b-2512 by default):
     runs the normal tool-calling loop against the given system prompt and
     produces a draft report.
  2. Finalization phase (MISTRAL_SYNTHESIS_MODEL, mistral-large-2512 by
     default): one single, tool-less completion that reviews the draft
     against the same system prompt's rules and rewrites it into the final
     report. One call is well within Large's tight rate limit regardless
     of how bursty phase 1 was.
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
    MISTRAL_RESEARCH_MODEL,
    MISTRAL_RETRY_BASE_SECONDS,
    MISTRAL_SYNTHESIS_MODEL,
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


# Appended to the same system prompt for the finalization phase (phase 2).
# Deliberately reuses the original prompt's own rules rather than a separate
# prompt file, so there is exactly one place (the shared system prompt) that
# defines what a correct report looks like — nothing to keep in sync.
_FINALIZATION_INSTRUCTION = (
    "\n\n## Finalization pass (this phase only)\n"
    "You are given a DRAFT of this report below, already researched and "
    "written by a smaller, faster model following every rule above. You "
    "have NO tools in this phase and must not invent, assume, or claim to "
    "have searched for any new fact beyond what the draft already "
    "contains — your job is to review and rewrite, not research.\n"
    "Review the draft against every rule above and rewrite it into the "
    "final, corrected version:\n"
    "- Fix any violation of the full-source-list / inline-citation "
    "matching rule (Evidence discipline): drop any source from the list "
    "that is never cited inline in the text, and add a source-list entry "
    "for any inline citation missing one.\n"
    "- Remove any preamble or meta-commentary before the title "
    "(Non-negotiable constraints) — your response must start directly "
    "with the H1 title line.\n"
    "- Fix markdown formatting issues (sub-bullet indentation, a literal "
    "`|` inside a table cell, a numbered list that restarts at 1).\n"
    "- Merge any near-duplicate pain points the draft left separate.\n"
    "- Preserve every genuine, evidence-backed finding from the draft — "
    "do not shorten the report just to make this pass easier.\n\n"
    "## Draft to finalize\n"
)


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


async def _run_research_phase(
    client: AsyncOpenAI, session: ClientSession, system_prompt: str, company_input: str
):
    """Tool-calling loop (unchanged from the single-phase design) using the
    high-throughput research model. Returns the raw chat.completions
    response of the turn that stopped calling tools (or None if the loop
    never got a response)."""
    tools = _mcp_tools_to_chat_completions((await session.list_tools()).tools)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": company_input},
    ]

    response = None
    for _ in range(MAX_ITERATIONS):
        response = await _create_completion_with_retry(
            client,
            model=MISTRAL_RESEARCH_MODEL,
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

    return response


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Research with a high-throughput model, then finalize with a stronger,
    low-throughput one (see module docstring for why)."""
    if not MISTRAL_API_KEY:
        raise RuntimeError("Mistral is not configured. Set MISTRAL_API_KEY in the .env file.")

    await session.initialize()
    # max_retries=0: retries are handled explicitly by
    # _create_completion_with_retry below, so a 429 doesn't get retried
    # twice (once silently by the SDK, once by us) with two different,
    # confusing backoff schedules.
    client = AsyncOpenAI(base_url=MISTRAL_BASE_URL, api_key=MISTRAL_API_KEY, max_retries=0)

    print(f"▶ Research phase — using model: {MISTRAL_RESEARCH_MODEL}", file=sys.stderr)
    try:
        draft_response = await _run_research_phase(client, session, system_prompt, company_input)
    except APIConnectionError as exc:
        raise RuntimeError("Cannot reach Mistral. Check your network connection and MISTRAL_API_KEY.") from exc
    except APIStatusError as exc:
        raise RuntimeError(
            f"Mistral request failed ({exc.status_code}): {exc.message} "
            f"(research phase, model={MISTRAL_RESEARCH_MODEL})"
        ) from exc

    if draft_response is None:
        return RunResult(text="", model=MISTRAL_RESEARCH_MODEL, stop_reason=None)

    draft_choice = draft_response.choices[0]
    draft_text = draft_choice.message.content or ""
    if not draft_text:
        return RunResult(
            text="",
            model=MISTRAL_RESEARCH_MODEL,
            stop_reason=draft_choice.finish_reason,
            truncated=draft_choice.finish_reason == "length",
        )

    print(
        f"▶ Finalization phase — using model: {MISTRAL_SYNTHESIS_MODEL} "
        f"(draft: {len(draft_text)} chars)",
        file=sys.stderr,
    )
    try:
        final_response = await _create_completion_with_retry(
            client,
            model=MISTRAL_SYNTHESIS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt + _FINALIZATION_INSTRUCTION},
                {"role": "user", "content": draft_text},
            ],
            max_tokens=MAX_TOKENS,
        )
    except APIConnectionError as exc:
        raise RuntimeError("Cannot reach Mistral. Check your network connection and MISTRAL_API_KEY.") from exc
    except APIStatusError as exc:
        raise RuntimeError(
            f"Mistral request failed ({exc.status_code}): {exc.message} "
            f"(finalization phase, model={MISTRAL_SYNTHESIS_MODEL})"
        ) from exc

    final_choice = final_response.choices[0]
    return RunResult(
        text=final_choice.message.content or "",
        model=final_response.model or MISTRAL_SYNTHESIS_MODEL,
        stop_reason=final_choice.finish_reason,
        truncated=final_choice.finish_reason == "length",
    )

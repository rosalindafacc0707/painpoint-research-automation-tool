"""Google Gemini-backed agent runner with local MCP research tools."""

import asyncio
import sys

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from mcp import ClientSession

from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_TOKENS
from providers.base import RunResult

MAX_ITERATIONS = 40

# Transient 429/5xx from Google's backend are common enough under concurrent
# multi-agent load that a bare retry (same request) resolves most of them.
MAX_MODEL_RETRIES = 3
_RETRYABLE_CODES = {429, 500, 502, 503, 504}


async def _generate_with_retry(client, **kwargs):
    for attempt in range(MAX_MODEL_RETRIES):
        try:
            return await client.aio.models.generate_content(**kwargs)
        except genai_errors.APIError as exc:
            if exc.code not in _RETRYABLE_CODES or attempt == MAX_MODEL_RETRIES - 1:
                raise
            print(
                f"  ⟲ retrying Gemini request after {exc.code} ({attempt + 1}/{MAX_MODEL_RETRIES})",
                file=sys.stderr,
            )
            await asyncio.sleep(1.5 * (attempt + 1))


def _mcp_tools_to_gemini(mcp_tools) -> list[types.FunctionDeclaration]:
    """Convert MCP JSON schemas into Gemini function declarations."""
    return [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description or "",
            parameters=tool.inputSchema,
        )
        for tool in mcp_tools
    ]


def _tool_result_text(result) -> str:
    """Flatten an MCP result into text for a Gemini function response."""
    parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no textual content returned)"


def _function_calls(response) -> list:
    """Return every function call from the Gemini response in call order."""
    calls = []
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            call = getattr(part, "function_call", None)
            if call:
                calls.append(call)
    return calls


def _response_content(response):
    candidates = getattr(response, "candidates", None) or []
    return candidates[0].content if candidates else None


async def run_agent(
    session: ClientSession | None,
    system_prompt: str,
    company_input: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    enable_tools: bool = True,
) -> RunResult:
    """Run a Google-hosted model and the local MCP tools until completion."""
    api_key = api_key or GEMINI_API_KEY
    model = model or GEMINI_MODEL
    if not api_key:
        raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY in the .env file.")

    tools = None
    if enable_tools:
        if session is None:
            raise ValueError("enable_tools=True requires an MCP session.")
        await session.initialize()
        mcp_tools = (await session.list_tools()).tools
        tools = [types.Tool(function_declarations=_mcp_tools_to_gemini(mcp_tools))]
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        max_output_tokens=MAX_TOKENS,
    )
    client = genai.Client(api_key=api_key)
    contents = [types.Content(role="user", parts=[types.Part(text=company_input)])]

    response = None
    for _ in range(MAX_ITERATIONS):
        try:
            response = await _generate_with_retry(
                client,
                model=model,
                contents=contents,
                config=config,
            )
        except genai_errors.APIError as exc:
            raise RuntimeError(f"Gemini request failed ({exc.code}): {exc.message}") from exc
        calls = _function_calls(response)
        if not calls:
            break

        model_content = _response_content(response)
        if model_content is None:
            break
        contents.append(model_content)

        async def _run(call):
            args = dict(getattr(call, "args", None) or {})
            print(f"  → tool: {call.name}({args})", file=sys.stderr)
            result = await session.call_tool(call.name, args)
            # FunctionResponse carries the call id.  We build the part
            # directly because ``Part.from_function_response`` does not
            # accept an id in every supported google-genai release.
            function_response = types.FunctionResponse(
                name=call.name,
                response={
                    "result": _tool_result_text(result),
                    "is_error": bool(result.isError),
                },
            )
            if getattr(call, "id", None):
                function_response.id = call.id
            return types.Part(function_response=function_response)

        function_responses = await asyncio.gather(*(_run(call) for call in calls))
        contents.append(types.Content(role="user", parts=function_responses))

    if response is None:
        return RunResult(text="", model=model, stop_reason=None)

    candidates = getattr(response, "candidates", None) or []
    finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    finish_reason_text = str(finish_reason).lower() if finish_reason is not None else None
    return RunResult(
        text=getattr(response, "text", "") or "",
        model=model,
        stop_reason=finish_reason_text,
        truncated=bool(finish_reason_text and "max_tokens" in finish_reason_text),
    )

"""Azure AI Foundry agent runner — Responses API.

Talks to the OpenAI-compatible v1 surface exposed by the Foundry resource
(base URL ending in `/openai/v1`), using the plain `openai.OpenAI` client
(NOT `AzureOpenAI` — no api_version needed on this surface) and the
**Responses API** (`client.responses.create`), confirmed working against the
actual deployed resource:

    from openai import OpenAI
    client = OpenAI(base_url="https://<resource>.services.ai.azure.com/openai/v1",
                     api_key=api_key)
    response = client.responses.create(model=deployment_name, input="...")

The Responses API has a different shape than Chat Completions:
  - system-level guidance goes in the top-level `instructions` param, not an
    input item.
  - tool schemas are flat: {"type": "function", "name": ..., "description":
    ..., "parameters": ...} — NOT nested under a "function" key.
  - output is `response.output`, a list of items (type "message",
    "function_call", ...); `response.output_text` conveniently concatenates
    any assistant text.
  - to answer a function call you append a {"type": "function_call_output",
    "call_id": ..., "output": ...} item to `input` and call again.

Azure AI Foundry deployments have no built-in server-side web search (unlike
Claude), so this provider is given TWO local MCP tools instead of one:
  - web_search_ddg — discovery (DuckDuckGo, no API key required)
  - fetch_url      — reading the full text of a discovered page

Required config (see config.py / .env / .env.development):
  - AZURE_OPENAI_API_KEY     (secret — .env)
  - AZURE_OPENAI_ENDPOINT    e.g. https://<resource>.services.ai.azure.com/openai/v1
  - AZURE_OPENAI_DEPLOYMENT  the deployment name configured in Azure AI
                              Foundry (NOT the base model name)
"""

import json
import sys

from mcp import ClientSession
from openai import AsyncOpenAI

from config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_ENDPOINT, MAX_TOKENS
from providers.base import RunResult

MAX_ITERATIONS = 40


def _mcp_tools_to_responses(mcp_tools) -> list[dict]:
    """Convert MCP tool descriptors into Responses-API function tool definitions.

    Flat shape — unlike Chat Completions, there is no nested "function" key.
    """
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        }
        for tool in mcp_tools
    ]


def _tool_result_text(result) -> str:
    """Flatten an MCP call_tool result into plain text for a function_call_output."""
    parts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no textual content returned)"


def _extract_text(response) -> str:
    """Pull the assistant's text out of a Responses API result."""
    text = getattr(response, "output_text", None)
    if text:
        return text
    parts = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for content in item.content:
                if getattr(content, "type", None) == "output_text":
                    parts.append(content.text)
    return "".join(parts)


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Drive the agentic loop until the model finishes; return the final text."""
    if not (AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT):
        raise RuntimeError(
            "Azure AI Foundry is not configured. Set AZURE_OPENAI_API_KEY (.env), "
            "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT (.env.development)."
        )

    await session.initialize()
    mcp_tools = (await session.list_tools()).tools  # web_search_ddg + fetch_url
    tools = _mcp_tools_to_responses(mcp_tools)

    client = AsyncOpenAI(base_url=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY)

    # Responses API: system-level guidance is a top-level param, not an input
    # item. `input` accumulates the turn-by-turn conversation, including
    # function_call / function_call_output items for tool use.
    input_items: list[dict] = [{"role": "user", "content": company_input}]

    response = None
    for _ in range(MAX_ITERATIONS):
        response = await client.responses.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            instructions=system_prompt,
            input=input_items,
            tools=tools,
            max_output_tokens=MAX_TOKENS,
        )

        if response.status == "failed":
            raise RuntimeError(f"Azure Responses API call failed: {response.error}")

        function_calls = [
            item for item in response.output if getattr(item, "type", None) == "function_call"
        ]

        if function_calls:
            # Keep the full turn (including any message/reasoning items) in
            # the conversation before appending our tool results.
            input_items.extend(item.model_dump(exclude_none=True) for item in response.output)
            for call in function_calls:
                args = json.loads(call.arguments or "{}")
                print(f"  → tool: {call.name}({args})", file=sys.stderr)
                result = await session.call_tool(call.name, args)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": _tool_result_text(result),
                    }
                )
            continue

        # completed / incomplete — stop looping.
        break

    if response is None:
        return RunResult(text="", model=AZURE_OPENAI_DEPLOYMENT, stop_reason=None)

    truncated = (
        response.status == "incomplete"
        and getattr(response.incomplete_details, "reason", None) == "max_output_tokens"
    )
    return RunResult(
        text=_extract_text(response),
        model=AZURE_OPENAI_DEPLOYMENT,
        stop_reason=response.status,
        truncated=truncated,
    )

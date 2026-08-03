"""Google-hosted Gemma agent runner using the project's local MCP tools."""

from mcp import ClientSession

from config import GEMMA_API_KEY, GEMMA_MODEL
from providers.base import RunResult
from providers.gemini_provider import run_agent as run_google_agent


async def run_agent(session: ClientSession, system_prompt: str, company_input: str) -> RunResult:
    """Run the configured Google-hosted Gemma model."""
    if not GEMMA_API_KEY:
        raise RuntimeError(
            "Gemma is not configured. Set GEMMA_API_KEY or GEMINI_API_KEY in the .env file."
        )
    return await run_google_agent(
        session,
        system_prompt,
        company_input,
        api_key=GEMMA_API_KEY,
        model=GEMMA_MODEL,
    )

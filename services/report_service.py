"""Business logic behind the /generate-pain-point-md endpoint.

Same agentic-loop flow as scripts/run_prompt_test.py (spin up the MCP
scraper server, pick a provider, run the system prompt against the company
intake), wrapped so it can be called from a FastAPI request instead of the
CLI. One company per call — no batch, mirroring the Phase 1 rules in
README.md.
"""

from datetime import datetime
from pathlib import Path

import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import ANTHROPIC_API_KEY, PROMPT_VERSION, PROVIDER, SYSTEM_PROMPT_PATH
from schemas.requests import GenerateMdDocRequest

ROOT = Path(__file__).resolve().parent.parent
SCRAPER_SERVER = ROOT / "mcp_server" / "scraper_server.py"
OUTPUTS_DIR = ROOT / "outputs"


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.strip().lower()).strip("_")


def _build_company_input(request: GenerateMdDocRequest) -> str:
    return "\n".join(
        [
            f"# Prospect Intake — {request.company_name}",
            "",
            "## Mandatory Field",
            f"- **Company name**: {request.company_name}",
            "",
            "## Optional Field",
            f"- Website: {request.website or ''}",
            f"- Country / region: {request.country_region or ''}",
            f"- Department / business unit: {request.department or ''}",
            f"- Industry: {request.industry or ''}",
            f"- Specific search criteria (only if differs from the default CVC): {request.research_lens or ''}",
        ]
    )


async def generate_pain_point_report(request: GenerateMdDocRequest) -> dict:
    provider = request.provider or PROVIDER

    if provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set. Check the .env file.")
        from providers.anthropic_provider import run_agent
    elif provider == "azure":
        from providers.azure_provider import run_agent
    else:
        raise ValueError(f"Unknown provider: {provider!r}. Use 'anthropic' or 'azure'.")

    system_prompt = (ROOT / SYSTEM_PROMPT_PATH).read_text(encoding="utf-8")
    run_metadata = (
        "\n\n## Run metadata (report this exactly in the report header)\n"
        f"- Prompt version: {PROMPT_VERSION}\n"
        f"- Agent version: {PROMPT_VERSION}\n"
        f"- Provider: {provider}\n"
        f"- Date of run: {datetime.now().strftime('%Y-%m-%d')}\n"
    )
    system_prompt += run_metadata

    company_input = _build_company_input(request)

    server_params = StdioServerParameters(command=sys.executable, args=[str(SCRAPER_SERVER)])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await run_agent(session, system_prompt, company_input)

    if not result.text:
        raise RuntimeError("No response produced by the model.")
    if result.stop_reason == "refusal":
        raise RuntimeError("The model refused the request (stop_reason=refusal).")

    company_slug = _slugify(request.company_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUTS_DIR.mkdir(exist_ok=True)
    filename = f"{company_slug}_{PROMPT_VERSION}_{provider}_{timestamp}.md"
    (OUTPUTS_DIR / filename).write_text(result.text, encoding="utf-8")

    return {
        "filename": filename,
        "company": request.company_name,
        "provider": provider,
        "model": result.model,
        "prompt_version": PROMPT_VERSION,
        "stop_reason": result.stop_reason,
        "truncated": result.truncated,
    }

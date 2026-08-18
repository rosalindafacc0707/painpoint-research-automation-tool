"""Business logic behind the /generate-pain-point-md endpoint.

Same agentic-loop flow as scripts/run_prompt_test.py (spin up the MCP
scraper server, pick a provider, run the system prompt against the company
intake), wrapped so it can be called from a FastAPI request instead of the
CLI. One company per call — no batch, mirroring the Phase 1 rules in
README.md.
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path

import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import (
    GEMINI_API_KEY,
    MISTRAL_API_KEY,
    PROMPT_VERSION,
    PROVIDER,
    SYSTEM_PROMPT_PATH,
)
from schemas.requests import GenerateMdDocRequest
from services import storage_service
from services.docx_export import markdown_to_docx

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

    if provider == "azure":
        from providers.azure_provider import run_agent
    elif provider == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set. Check the .env file.")
        from providers.gemini_provider import run_agent
    elif provider == "ollama":
        from providers.ollama_provider import run_agent
    elif provider == "mistral":
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set. Check the .env file.")
        from providers.mistral_provider import run_agent
    else:
        raise ValueError(f"Unknown provider: {provider!r}. Use azure, gemini, ollama, or mistral.")

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
    base_name = f"{company_slug}_{PROMPT_VERSION}_{provider}_{timestamp}"

    filename = f"{base_name}.md"
    (OUTPUTS_DIR / filename).write_text(result.text, encoding="utf-8")

    docx_filename = f"{base_name}.docx"
    docx_document = markdown_to_docx(result.text)
    docx_document.save(OUTPUTS_DIR / docx_filename)

    download_url = f"/painpoint-researcher/download/{filename}"
    docx_download_url = f"/painpoint-researcher/download/{docx_filename}"

    # Persist to Supabase (Storage + Postgres index) when configured, so the
    # report survives Render's ephemeral disk and is visible/downloadable
    # from any browser via GET /reports — not just this same request's
    # local-disk copy. No-ops locally when Supabase isn't set up.
    if storage_service.is_configured():
        docx_buffer = BytesIO()
        docx_document.save(docx_buffer)
        report_id = storage_service.save_report(
            company_name=request.company_name,
            filename=filename,
            docx_filename=docx_filename,
            md_text=result.text,
            docx_bytes=docx_buffer.getvalue(),
            provider=provider,
            model=result.model,
            prompt_version=PROMPT_VERSION,
            stop_reason=result.stop_reason,
            truncated=result.truncated,
        )
        download_url = f"/painpoint-researcher/reports/{report_id}/download?kind=md"
        docx_download_url = f"/painpoint-researcher/reports/{report_id}/download?kind=docx"

    return {
        "filename": filename,
        "docx_filename": docx_filename,
        "company": request.company_name,
        "provider": provider,
        "model": result.model,
        "prompt_version": PROMPT_VERSION,
        "stop_reason": result.stop_reason,
        "truncated": result.truncated,
        "download_url": download_url,
        "docx_download_url": docx_download_url,
    }

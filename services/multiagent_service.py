"""Business logic behind the /generate-pain-point-md-multiagent endpoint.

Splits the research phase into N parallel per-topic research agents, each
running its own MCP scraper subprocess and bounded to a single topic's
search+fetch loop (see prompts/multiagent_research_prompt.md). Their
findings are then handed — as plain evidence, with no further tool access
— to a single synthesis agent (prompts/multiagent_synthesis_prompt.md) that
merges, deduplicates, and writes the final deliverable.

It trades a fixed per-request overhead (N+1 model calls and N MCP
subprocesses) for bounded per-agent context and real topic-level
parallelism, and lets the research and synthesis roles each use a
different, independently configured provider/model.
"""

import asyncio
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import (
    PROMPT_VERSION,
    RESEARCH_AGENT_CONCURRENCY,
    RESEARCH_AGENT_MODEL,
    RESEARCH_AGENT_PROVIDER,
    SYNTHESIS_AGENT_MODEL,
    SYNTHESIS_AGENT_PROVIDER,
)
from providers.base import RunResult, resolve_run_agent
from schemas.requests import GenerateMdDocRequestMultiAgent
from services import storage_service
from services.docx_export import markdown_to_docx

ROOT = Path(__file__).resolve().parent.parent
SCRAPER_SERVER = ROOT / "mcp_server" / "scraper_server.py"
OUTPUTS_DIR = ROOT / "outputs"


def slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.strip().lower()).strip("_")


def build_company_input(request) -> str:
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

# The canonical list of research topics — each is handed to one parallel
# research agent via prompts/multiagent_research_prompt.md's {topic}
# placeholder. Mirrors frontend/index.html's RESEARCH_TOPICS (a cosmetic
# progress-bar list) — kept in sync by hand since the two live in different
# layers (this orchestrator vs. the UI) and neither imports from the other.
RESEARCH_TOPICS = [
    "Marketing transformation programs",
    "Content workflow and operating model",
    "Governance and brand control",
    "Global rollout / global-to-local model",
    "Embedded teams and organisation structure",
    "Data ownership",
    "Brand integrity",
    "AI in marketing",
]

RESEARCH_PROMPT_TEMPLATE = (ROOT / "prompts" / "multiagent_research_prompt.md").read_text(encoding="utf-8")
SYNTHESIS_PROMPT = (ROOT / "prompts" / "multiagent_synthesis_prompt.md").read_text(encoding="utf-8")

# Caps how many of the 8 per-topic MCP subprocesses are alive at once — see
# config.RESEARCH_AGENT_CONCURRENCY for why this exists (Render free tier
# OOM under full 8-way parallelism).
_topic_semaphore = asyncio.Semaphore(RESEARCH_AGENT_CONCURRENCY)


async def _run_topic_agent(topic: str, provider: str, model: str | None, company_input: str) -> str:
    """Research exactly one topic in its own MCP subprocess; return its findings."""
    run_agent = resolve_run_agent(provider)
    system_prompt = RESEARCH_PROMPT_TEMPLATE.format(topic=topic)
    server_params = StdioServerParameters(command=sys.executable, args=[str(SCRAPER_SERVER)])

    print(f"  ▷ research agent starting: {topic!r} via {provider}", file=sys.stderr)
    try:
        async with _topic_semaphore, stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                result = await run_agent(session, system_prompt, company_input, model=model)
    except Exception as exc:  # noqa: BLE001 - one topic's failure (rate limit, transient
        # network error, etc.) must not sink the other 7 parallel agents; the
        # synthesis agent is already instructed to treat thin/no evidence for
        # a topic as a valid, expected outcome, so a failure just becomes an
        # extreme case of that.
        print(f"  ✗ research agent failed: {topic!r}: {exc}", file=sys.stderr)
        return f"## {topic}\n\nResearch agent failed and produced no findings ({exc}).\n"
    print(f"  ✓ research agent done: {topic!r}", file=sys.stderr)

    return result.text or f"## {topic}\n\nNo findings produced by the research agent.\n"


async def _run_synthesis_agent(
    provider: str,
    model: str | None,
    company_input: str,
    topic_findings: list[str],
    run_metadata: str,
) -> RunResult:
    """Write the final report from the combined topic findings — no tools, no new evidence."""
    run_agent = resolve_run_agent(provider)
    dossier = "\n\n---\n\n".join(topic_findings)
    synthesis_input = (
        f"{company_input}\n\n"
        "## Combined research findings (one section per topic, from independent research agents)\n\n"
        f"{dossier}"
        f"{run_metadata}"
    )
    return await run_agent(None, SYNTHESIS_PROMPT, synthesis_input, model=model, enable_tools=False)


async def generate_pain_point_report_multiagent(request: GenerateMdDocRequestMultiAgent) -> dict:
    research_provider = request.research_provider or RESEARCH_AGENT_PROVIDER
    research_model = request.research_model or RESEARCH_AGENT_MODEL
    synthesis_provider = request.synthesis_provider or SYNTHESIS_AGENT_PROVIDER
    synthesis_model = request.synthesis_model or SYNTHESIS_AGENT_MODEL

    company_input = build_company_input(request)

    topic_findings = await asyncio.gather(
        *(
            _run_topic_agent(topic, research_provider, research_model, company_input)
            for topic in RESEARCH_TOPICS
        )
    )

    run_metadata = (
        "\n\n## Run metadata (report this exactly in the report header)\n"
        f"- Prompt version: {PROMPT_VERSION}-multiagent\n"
        f"- Agent version: {PROMPT_VERSION}-multiagent\n"
        f"- Research provider/model: {research_provider}/{research_model or '(provider default)'}\n"
        f"- Synthesis provider/model: {synthesis_provider}/{synthesis_model or '(provider default)'}\n"
        f"- Date of run: {datetime.now().strftime('%Y-%m-%d')}\n"
    )

    result = await _run_synthesis_agent(
        synthesis_provider, synthesis_model, company_input, list(topic_findings), run_metadata
    )

    if not result.text:
        raise RuntimeError("No response produced by the synthesis agent.")
    if result.stop_reason == "refusal":
        raise RuntimeError("The synthesis model refused the request (stop_reason=refusal).")

    company_slug = slugify(request.company_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUTS_DIR.mkdir(exist_ok=True)
    base_name = f"{company_slug}_{PROMPT_VERSION}_multiagent_{timestamp}"

    filename = f"{base_name}.md"
    (OUTPUTS_DIR / filename).write_text(result.text, encoding="utf-8")

    docx_filename = f"{base_name}.docx"
    docx_document = markdown_to_docx(result.text)
    docx_document.save(OUTPUTS_DIR / docx_filename)

    provider_label = f"multiagent(research={research_provider}, synthesis={synthesis_provider})"

    download_url = f"/painpoint-researcher/download/{filename}"
    docx_download_url = f"/painpoint-researcher/download/{docx_filename}"

    # Persist to Supabase (Storage + Postgres index) when configured, so the
    # report survives Render's ephemeral disk and is visible/downloadable
    # from any browser via GET /reports — not just this same request's
    # local-disk preview. No-ops locally when Supabase isn't set up.
    if storage_service.is_configured():
        docx_buffer = BytesIO()
        docx_document.save(docx_buffer)
        report_id = storage_service.save_report(
            company_name=request.company_name,
            filename=filename,
            docx_filename=docx_filename,
            md_text=result.text,
            docx_bytes=docx_buffer.getvalue(),
            provider=provider_label,
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
        "provider": provider_label,
        "model": result.model,
        "prompt_version": PROMPT_VERSION,
        "stop_reason": result.stop_reason,
        "truncated": result.truncated,
        "download_url": download_url,
        "docx_download_url": docx_download_url,
    }

#!/usr/bin/env python3
"""
Manual test script for the multi-agent pipeline (Phase 1 — Prompt Prototyping).

This project has only one agent architecture: N parallel per-topic research
agents + one synthesis agent (services/multiagent_service.py). There used to
be a separate single-agent script that loaded prompts/system_prompt_vN.md
directly — it has been removed; those prompt files now live under
prompts/_deprecated/ for historical reference only, and the CHANGELOG entry
at the top of prompts/CHANGELOG.md explains why.

Usage:
    python scripts/run_prompt_test.py --company "Acme Corp"
    python scripts/run_prompt_test.py --company "Acme Corp" --website acme.com --region EMEA
    python scripts/run_prompt_test.py --company "Acme Corp" --research-provider gemini --synthesis-provider ollama

It's not an automatic pipeline: useful just to validate the two multi-agent
prompts on single real companies, one company each execution. The result
always requires human review before every commercial use.

Provider switch (RESEARCH_AGENT_PROVIDER / SYNTHESIS_AGENT_PROVIDER in
.env.development, or --research-provider / --synthesis-provider on the CLI):
  - "ollama" (default for both roles) — local open-weight model (default:
    qwen3.5:9b). No API key required, and no external rate limit at all
    since nothing leaves this machine — the 8 parallel research agents just
    queue locally instead of failing.
  - "gemini" — Google-hosted model, free tier; its requests-per-minute cap
    can still be tight under 8-way parallel load.
  - "anthropic" — Claude, with its server-side web_search tool for discovery
    plus the local fetch_url MCP tool for reading pages.
  - "azure" — an Azure OpenAI / Azure AI Foundry deployment.
  - "groq" — openai/gpt-oss-120b on Groq's LPU hardware, free tier, no
    payment method required. Much faster than ollama, but the tightest free
    budget of any provider here (~30 RPM / 8k TPM / 1k RPD for this model);
    providers/groq_provider.py paces requests to stay under the RPM cap and
    compacts older tool results to stay under the TPM one. Not
    llama-3.3-70b-versatile: verified live, that model's tool-calling on
    Groq is unreliable (~1 in 6 tool-enabled requests emits a malformed tag
    instead of a real tool call) — see the module docstring for the full
    writeup; it remains available via GROQ_MODEL but is only safe for the
    synthesis role (no tools).

gemma and cerebras were removed (2026-08-06): gemma kept tripping its
free-tier rate limits under this project's 8-parallel-agents load — see
prompts/CHANGELOG.md v8. cerebras' "free" plan requires a payment method at
signup, so it was never actually free. groq was removed for the same reason
as gemma and re-added the same day, initially pointed at
llama-3.3-70b-versatile with a TPM budget guard, then moved to
openai/gpt-oss-120b once that model's tool-calling proved unreliable.

Each of the 8 parallel research-agent subprocesses and the synthesis agent
launch their own MCP server (mcp_server/scraper_server.py) as a stdio
subprocess — see services/multiagent_service.py for the orchestration.
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import PROMPT_VERSION  # noqa: E402
from schemas.requests import GenerateMdDocRequestMultiAgent  # noqa: E402
from services.multiagent_service import generate_pain_point_report_multiagent  # noqa: E402


async def main_async(args) -> None:
    request = GenerateMdDocRequestMultiAgent(
        company_name=args.company,
        website=args.website,
        country_region=args.region,
        department=args.department,
        industry=args.industry,
        research_lens=args.lens,
        research_provider=args.research_provider,
        research_model=args.research_model,
        synthesis_provider=args.synthesis_provider,
        synthesis_model=args.synthesis_model,
    )

    result = await generate_pain_point_report_multiagent(request)

    report_path = ROOT / "outputs" / result["filename"]
    docx_path = ROOT / "outputs" / result["docx_filename"]

    print(report_path.read_text(encoding="utf-8"))
    print(f"\n---\nOutput salvato in: {report_path} e {docx_path}")
    print(f"Provider: {result['provider']} | Model: {result['model']} | Prompt version: {PROMPT_VERSION}")
    print("Note: mandatory human review before every commercial use.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual test of the multi-agent pipeline on a single company (Phase 1)."
    )
    parser.add_argument("--company", required=True, help="Company name (mandatory field).")
    parser.add_argument("--website", default=None, help="Company website (optional).")
    parser.add_argument("--region", default=None, help="Country / region (optional).")
    parser.add_argument("--department", default=None, help="Department / business unit (optional).")
    parser.add_argument("--industry", default=None, help="Industry (optional).")
    parser.add_argument(
        "--lens",
        default=None,
        help="Specific research lens, only if it differs from the default CVC (optional).",
    )
    parser.add_argument(
        "--research-provider",
        choices=["anthropic", "azure", "gemini", "ollama", "groq"],
        default=None,
        help="Override RESEARCH_AGENT_PROVIDER for this run.",
    )
    parser.add_argument("--research-model", default=None, help="Model override for the research agents.")
    parser.add_argument(
        "--synthesis-provider",
        choices=["anthropic", "azure", "gemini", "ollama", "groq"],
        default=None,
        help="Override SYNTHESIS_AGENT_PROVIDER for this run.",
    )
    parser.add_argument("--synthesis-model", default=None, help="Model override for the synthesis agent.")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Script for the manual test of Phase 1 (Prompt Prototyping).

Usage:
    python scripts/run_prompt_test.py inputs/sample_company_input.md
    python scripts/run_prompt_test.py inputs/sample_company_input.md --company "Acme Corp"
    python scripts/run_prompt_test.py inputs/sample_company_input.md --provider opensource

It's not an automatic pipeline: useful just to validate the system prompt on
single real companies, one company each execution. The result always requires
human review before every commercial use.

Provider switch (PROVIDER in .env.development, or --provider on the CLI):
  - "anthropic"  (default) — Claude, with its server-side web_search tool for
    discovery plus the local fetch_url MCP tool for reading pages.
  - "opensource" — any OpenAI-compatible endpoint (e.g. GPT-OSS via Ollama).
    Since these runtimes have no built-in web search, this path uses TWO
    local MCP tools instead: web_search_ddg (discovery) and fetch_url
    (reading). See providers/opensource_provider.py for setup notes.

Either way, the MCP server (mcp_server/scraper_server.py) is launched once as
a stdio subprocess and its tools are handed to whichever provider is active.
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import ANTHROPIC_API_KEY, PROMPT_VERSION, PROVIDER, SYSTEM_PROMPT_PATH  # noqa: E402

SCRAPER_SERVER = ROOT / "mcp_server" / "scraper_server.py"


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")
    return path.read_text(encoding="utf-8")


def slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.strip().lower()).strip("_")


async def main_async(args) -> None:
    provider = args.provider or PROVIDER

    if provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            sys.exit("ANTHROPIC_API_KEY not set. Check for it in the .env file")
        from providers.anthropic_provider import run_agent
    elif provider == "opensource":
        from providers.opensource_provider import run_agent
    else:
        sys.exit(f"Unknown provider: {provider!r}. Use 'anthropic' or 'opensource'.")

    system_prompt = load_text(ROOT / SYSTEM_PROMPT_PATH)
    company_input = load_text(Path(args.input_file))

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SCRAPER_SERVER)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await run_agent(session, system_prompt, company_input)

    if not result.text:
        sys.exit("No response produced.")

    if result.truncated:
        print(
            "WARNING: output hit max_tokens/length and may be truncated. "
            "Consider raising MAX_TOKENS in .env.development.",
            file=sys.stderr,
        )
    if result.stop_reason == "refusal":
        sys.exit("The model refused the request (stop_reason=refusal).")

    company_slug = slugify(args.company) if args.company else "company"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outputs_dir = ROOT / "outputs"
    outputs_dir.mkdir(exist_ok=True)
    output_path = outputs_dir / f"{company_slug}_{PROMPT_VERSION}_{provider}_{timestamp}.md"
    output_path.write_text(result.text, encoding="utf-8")

    print(result.text)
    print(f"\n---\nOutput salvato in: {output_path}")
    print(f"Provider: {provider} | Model: {result.model} | Prompt version: {PROMPT_VERSION}")
    print("Note: mandatory human review before every commercial use.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual test of the system prompt on a single company (Phase 1)."
    )
    parser.add_argument(
        "input_file",
        help="File path with the company's intake information.",
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Company name (used to rename the output file).",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "opensource"],
        default=None,
        help="Override PROVIDER from .env.development for this run.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

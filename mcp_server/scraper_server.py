#!/usr/bin/env python3
"""
MCP server (stdio) — Research tools for the FFD Pain-Point Research Agent.

Exposes two tools:
  - fetch_url        — reads the full text of a known URL (httpx + trafilatura).
  - web_search_ddg    — discovers candidate source URLs via DuckDuckGo, no API
                        key required.

Which tools a given run actually uses depends on the provider (see
providers/anthropic_provider.py and providers/azure_provider.py):
  - Anthropic provider: uses Claude's own server-side `web_search` tool for
    discovery, and only calls `fetch_url` here to read the full page.
  - Azure provider (Azure OpenAI / Azure AI Foundry): has no built-in web
    search, so it uses BOTH `web_search_ddg` (discovery) and `fetch_url`
    (reading) from this server.

Run standalone for a manual check:
    python mcp_server/scraper_server.py        # starts the stdio server (waits)

Normally it is launched as a subprocess by scripts/run_prompt_test.py.
"""

import json

import httpx
import trafilatura
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

# Cap the extracted text so a single page cannot blow up the token budget.
# ~20k chars is plenty for a press release / careers page / case study.
MAX_CHARS = 20_000

REQUEST_TIMEOUT = 20.0

# A realistic User-Agent avoids trivial bot blocks on many corporate sites.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "FFD-PainPoint-Research/1.0"
)

mcp = FastMCP("web-scraper")


@mcp.tool()
def web_search_ddg(query: str, max_results: int = 8) -> str:
    """Search the web and return candidate result titles, URLs, and snippets.

    Only needed for providers without a built-in web search tool (e.g. Azure
    OpenAI). Use this to DISCOVER sources; after finding a promising URL
    here, use fetch_url to read its full content before you quote or cite
    it — never cite a page you have only seen as a snippet.

    Args:
        query: The search query.
        max_results: Maximum number of results to return (default 8).
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:  # noqa: BLE001 - surface any backend error to the model
        return f"ERROR: web search failed for query {query!r}: {exc}"

    if not results:
        return f"No results found for query: {query!r}"

    lines = []
    for i, r in enumerate(results, start=1):
        title = r.get("title", "")
        url = r.get("href") or r.get("url", "")
        snippet = r.get("body", "")
        lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")
    return "\n\n".join(lines)


@mcp.tool()
def fetch_url(url: str) -> str:
    """Fetch a single web page and return its main readable text.

    Use this AFTER web_search has surfaced a promising source URL, to read the
    full content of that page (press releases, investor/annual reports, case
    studies, job postings, news articles) so you can quote and cite it. Returns
    the page title and publication date when detectable — use them for the
    inline citation format required by the system prompt.

    Args:
        url: The absolute URL of the page to fetch (must start with http/https).
    """
    if not url.lower().startswith(("http://", "https://")):
        return f"ERROR: not a valid absolute URL: {url!r}"

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)
    except httpx.HTTPStatusError as exc:
        return f"ERROR: HTTP {exc.response.status_code} while fetching {url}"
    except httpx.HTTPError as exc:
        return f"ERROR: could not fetch {url}: {exc}"

    extracted = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )

    title = ""
    date = ""
    text = ""
    if extracted:
        data = json.loads(extracted)
        title = data.get("title") or ""
        date = data.get("date") or ""
        text = data.get("text") or ""

    if not text:
        return (
            f"WARNING: fetched {final_url} but could not extract readable "
            "main-text content (the page may be JavaScript-rendered or empty). "
            "Do not cite this URL as evidence."
        )

    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]

    header = [f"URL: {final_url}"]
    if title:
        header.append(f"Title: {title}")
    if date:
        header.append(f"Date: {date}")
    if truncated:
        header.append(f"[Content truncated to {MAX_CHARS} characters]")

    return "\n".join(header) + "\n\n" + text


if __name__ == "__main__":
    mcp.run()

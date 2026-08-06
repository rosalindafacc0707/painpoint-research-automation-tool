#!/usr/bin/env python3
"""
MCP server (stdio) — Research tools for the FFD Pain-Point Research Agent.

Exposes two tools:
  - fetch_url        — reads the full text of a known URL (httpx + trafilatura
                        for HTML, pypdf for PDF documents). Deliberately NOT an
                        LLM-based extractor (e.g. ScrapeGraphAI): trafilatura's
                        rule-based extraction is near-instant and free, whereas
                        routing every fetched page through an LLM would add a
                        model call (latency + cost) per source and, per public
                        comparisons, less consistent structured output than
                        this approach already gets from a precision-tuned
                        extractor.
  - web_search_ddg    — discovers candidate source URLs. Uses the Tavily
                        Search API (built for AI agents, free tier) when
                        TAVILY_API_KEY is set; otherwise falls back to a
                        metasearch aggregator, no API key required.

Which tools a given run actually uses depends on the provider (see
providers/anthropic_provider.py and providers/azure_provider.py):
  - Anthropic provider: uses Claude's own server-side `web_search` tool for
    discovery, and only calls `fetch_url` here to read the full page.
  - Azure provider (Azure OpenAI / Azure AI Foundry): has no built-in web
    search, so it uses BOTH `web_search_ddg` (discovery) and `fetch_url`
    (reading) from this server.

Both tools are `async def`, offloading their actual blocking work (network
I/O, PDF/HTML parsing) onto a worker thread via `asyncio.to_thread`. FastMCP
calls a *sync* `def` tool directly on the server's single event loop, which
blocks it for the tool's whole duration — so with sync tools, even a client
that fires several tool calls concurrently (see providers/*.py) ends up
waiting on them one at a time server-side anyway. Making them `async def`
and delegating the blocking part to a thread is what lets multiple in-flight
calls actually overlap.

Both tools also cache successful results in memory for the life of this
process (one process per research run — see providers/*.py, which launch a
fresh subprocess per run), and fetch_url reuses a single httpx.Client so
repeated requests to the same host share a pooled connection. The agent
occasionally re-searches or re-fetches something it already has (e.g. the
same URL surfaced by two different queries); replaying identical content
from cache is free and cannot go stale within a single run.

Run standalone for a manual check:
    python mcp_server/scraper_server.py        # starts the stdio server (waits)

Normally it is launched as a subprocess by scripts/run_prompt_test.py.
"""

import asyncio
import io
import json
import sys
from pathlib import Path

import httpx
import trafilatura
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

# Launched as a bare `python mcp_server/scraper_server.py` subprocess (see
# providers/*.py), so Python only puts this file's own directory on
# sys.path[0] — the project root (and config.py in it) is not importable
# without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import TAVILY_API_KEY  # noqa: E402

# Cap the extracted text so a single page cannot blow up the token budget.
# ~20k chars is plenty for a press release / careers page / case study.
MAX_CHARS = 20_000

# Annual reports and investor decks can run to hundreds of pages; stop
# reading pages once we're comfortably past MAX_CHARS rather than parsing
# the whole document just to truncate it afterwards.
MAX_PDF_PAGES = 60

REQUEST_TIMEOUT = 20.0

# ddgs (metasearch) tries every backend in this list per call. duckduckgo,
# mojeek, and grokipedia were observed to fail 100% of the time in this
# environment (self-signed-cert SSL error, HTTP 403, HTTP 502 respectively) —
# excluding them cuts wasted round trips per search without losing coverage:
# duckduckgo's own results come from the same underlying provider as yahoo,
# which is kept. google was later observed doing the same (100% HTTP 429 —
# bot-detection CAPTCHA, likely IP-based) and was dropped for the same reason.
SEARCH_BACKENDS = "yandex,startpage,yahoo,wikipedia"

# A realistic User-Agent avoids trivial bot blocks on many corporate sites.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "FFD-PainPoint-Research/1.0"
)

mcp = FastMCP("web-scraper")

# One httpx.Client for the whole server process (one process per research
# run — see module docstring). Reusing it lets httpx pool/reuse TCP+TLS
# connections across calls to the same host, which is common: a single run
# typically fetches several pages from the same company domain. httpx.Client
# is documented as safe to share across threads, which matters here since
# _download_sync runs via asyncio.to_thread and may execute concurrently.
_http_client = httpx.Client(
    follow_redirects=True,
    timeout=REQUEST_TIMEOUT,
    headers={"User-Agent": USER_AGENT},
)

# Keyed by the exact (query, max_results) or url the model requested. Scoped
# to this process's lifetime (one research run) — the agent sometimes
# re-issues an identical search or re-fetches a URL it already read (e.g.
# rediscovered via a second query), and the content can't have changed
# within one run, so repeating the network round trip is pure waste. Only
# successful results are cached: an ERROR/WARNING is deliberately not
# cached, so a transient failure can still succeed on retry.
_search_cache: dict[tuple[str, int], str] = {}
_fetch_cache: dict[str, str] = {}


def _search_sync(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results, backend=SEARCH_BACKENDS))


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _tavily_search_sync(query: str, max_results: int) -> list[dict]:
    """Query the Tavily Search API — purpose-built for AI agents.

    Returns already-cleaned, deduped results (title/url/snippet), which is
    both faster and more reliable than scraping general-purpose metasearch
    backends: no CAPTCHA/bot-detection failures, and no per-backend retry
    loop. Normalizes to the same {title, href, body} shape _search_sync
    returns so the caller doesn't need to know which backend served it.
    """
    response = _http_client.post(
        TAVILY_SEARCH_URL,
        json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()
    return [
        {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("content", "")}
        for r in data.get("results", [])
    ]


@mcp.tool()
async def web_search_ddg(query: str, max_results: int = 8) -> str:
    """Search the web and return candidate result titles, URLs, and snippets.

    Only needed for providers without a built-in web search tool (e.g. Azure
    OpenAI). Use this to DISCOVER sources; after finding a promising URL
    here, use fetch_url to read its full content before you quote or cite
    it — never cite a page you have only seen as a snippet.

    Args:
        query: The search query.
        max_results: Maximum number of results to return (default 8).
    """
    cache_key = (query, max_results)
    if cache_key in _search_cache:
        return _search_cache[cache_key]

    results: list[dict] = []
    if TAVILY_API_KEY:
        try:
            results = await asyncio.to_thread(_tavily_search_sync, query, max_results)
        except Exception as exc:  # noqa: BLE001 - fall back to ddgs rather than failing the run
            print(f"  ⚠ Tavily search failed for {query!r}, falling back to ddgs: {exc}", file=sys.stderr)
            results = []

    if not results:
        try:
            results = await asyncio.to_thread(_search_sync, query, max_results)
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
    output = "\n\n".join(lines)
    _search_cache[cache_key] = output
    return output


def _download_sync(url: str) -> httpx.Response:
    response = _http_client.get(url)
    response.raise_for_status()
    return response


def _is_pdf(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return "application/pdf" in content_type or str(response.url).lower().split("?")[0].endswith(".pdf")


def _extract_pdf_sync(data: bytes) -> tuple[str, str]:
    """Returns (title, text). Stops early once well past MAX_CHARS worth of text."""
    reader = PdfReader(io.BytesIO(data))
    title = (reader.metadata and reader.metadata.title) or ""
    chunks = []
    total_len = 0
    for page in reader.pages[:MAX_PDF_PAGES]:
        page_text = page.extract_text() or ""
        chunks.append(page_text)
        total_len += len(page_text)
        if total_len > MAX_CHARS * 1.2:
            break
    return title, "\n\n".join(chunks)


def _extract_html_sync(html: str) -> tuple[str, str, str]:
    """Returns (title, date, text)."""
    extracted = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not extracted:
        return "", "", ""
    data = json.loads(extracted)
    return data.get("title") or "", data.get("date") or "", data.get("text") or ""


@mcp.tool()
async def fetch_url(url: str) -> str:
    """Fetch a single web page or PDF and return its main readable text.

    Use this AFTER web_search has surfaced a promising source URL, to read the
    full content of that page (press releases, investor/annual reports, case
    studies, job postings, news articles — HTML or PDF) so you can quote and
    cite it. Returns the page title and publication date when detectable — use
    them for the inline citation format required by the system prompt.

    Args:
        url: The absolute URL of the page to fetch (must start with http/https).
    """
    if not url.lower().startswith(("http://", "https://")):
        return f"ERROR: not a valid absolute URL: {url!r}"

    if url in _fetch_cache:
        return _fetch_cache[url]

    try:
        response = await asyncio.to_thread(_download_sync, url)
    except httpx.HTTPStatusError as exc:
        return f"ERROR: HTTP {exc.response.status_code} while fetching {url}"
    except httpx.HTTPError as exc:
        return f"ERROR: could not fetch {url}: {exc}"

    final_url = str(response.url)
    date = ""

    if _is_pdf(response):
        try:
            title, text = await asyncio.to_thread(_extract_pdf_sync, response.content)
        except Exception as exc:  # noqa: BLE001 - a malformed/scanned-image PDF shouldn't crash the run
            return (
                f"WARNING: fetched {final_url} but could not parse it as a PDF ({exc}). "
                "Do not cite this URL as evidence."
            )
    else:
        title, date, text = await asyncio.to_thread(_extract_html_sync, response.text)

    if not text:
        return (
            f"WARNING: fetched {final_url} but could not extract readable "
            "main-text content (the page may be JavaScript-rendered, a scanned-image "
            "PDF, or empty). Do not cite this URL as evidence."
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
        header.append(
            f"[Content truncated to {MAX_CHARS} characters. This tool takes no "
            "pagination/offset arguments — cite what's shown here, or call "
            "fetch_url again with a different URL for more evidence.]"
        )

    output = "\n".join(header) + "\n\n" + text
    _fetch_cache[url] = output
    return output


if __name__ == "__main__":
    mcp.run()

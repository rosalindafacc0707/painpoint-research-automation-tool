import os
from dotenv import load_dotenv

# Secrets live in .env; non-secret app config lives in .env.development.
# Load both; .env values take precedence (loaded last, override=True).
load_dotenv(".env.development")
load_dotenv(".env", override=True)

# --- Provider registry -------------------------------------------------------
# This project runs ONLY the multi-agent pipeline (services/multiagent_service.py)
# — there is no single-agent path anymore. RESEARCH_AGENT_PROVIDER and
# SYNTHESIS_AGENT_PROVIDER below pick the provider for each of the two agent
# roles independently. Available providers (providers/base.py):
# "anthropic" -> Claude via the Anthropic API (paid)
# "azure"     -> Azure OpenAI / Azure AI Foundry deployment (paid)
# "gemini"    -> Google Gemini API (free tier, but its RPM cap can still be
#                too tight for 8 simultaneous research agents — see below)
# "ollama"    -> local open-weight model served by Ollama (fully free, local,
#                NO external rate limit at all since nothing leaves this
#                machine — default for both agent roles, see below)
# "groq"      -> llama-3.3-70b-versatile on Groq's LPU hardware (free tier,
#                no payment method — but a tight TPM/RPM budget; see
#                providers/groq_provider.py)
#
# gemma and cerebras were removed (2026-08-06): gemma kept tripping its
# free-tier rate limits under this project's load (8 parallel research
# agents + 1 synthesis agent per report) — see prompts/CHANGELOG.md v8.
# cerebras' signup asks for a payment method even on its "free" plan, so it
# was never actually free. groq was removed for the same reason as gemma and
# re-added on 2026-08-06 pointed at llama-3.3-70b-versatile instead, with a
# TPM budget guard (see providers/groq_provider.py) to survive 8-way
# parallel load — it remains the riskiest of the free options here; ollama
# is the only one structurally immune to rate limits since nothing leaves
# this machine.

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-5")

# --- Azure OpenAI / Azure AI Foundry ---------------------------------------
# Uses the OpenAI-compatible v1 surface exposed by the Foundry resource
# (base URL ending in /openai/v1), via the plain `openai.OpenAI` client and
# the Responses API (client.responses.create) — confirmed working against
# the actual deployed resource. No api_version needed on this surface.
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv(
    "AZURE_OPENAI_ENDPOINT", "https://your-resource.services.ai.azure.com/openai/v1"
)
# The deployment name configured in Azure AI Foundry (NOT the base model name).
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4")

# --- Google Gemini ----------------------------------------------------------
# The API key is a secret and belongs in .env. The model can be changed in
# .env.development without changing application code.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

# qwen3.5:9b is the quality / memory balance for this Mac's 16 GB unified
# memory. It supports tool calling and a 32k context is useful for research.
# No external rate limit applies to this provider at all — everything runs
# on this machine — which makes it the fallback when a hosted free tier
# can't keep up with 8 parallel research agents.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
# qwen3.5 (like deepseek-r1) is a hybrid reasoning model: by default it emits
# a hidden chain-of-thought before every answer, which measured ~17 tok/s on
# this machine — a "say hello" turned into 1000+ reasoning tokens and over a
# minute of wall time. Setting think=false (Ollama's native switch for
# hybrid-reasoning models) skips that and cut the same request to ~1s while
# leaving tool-calling accuracy unaffected (verified locally). Set
# OLLAMA_THINK=true only if a role's output quality noticeably needs the
# extra reasoning and the slowdown is acceptable for that role.
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() == "true"
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "900"))

# --- Groq: high-speed hosted open-weight models -----------------------------
# Groq's LPU inference hardware is much faster than local Ollama inference,
# and its free tier needs no payment method (unlike Cerebras). Two tradeoffs,
# both confirmed live against this account:
# 1. llama-3.3-70b-versatile's tool-calling is unreliable on Groq — it
#    intermittently (~1 in 6 requests, unaffected by temperature) emits its
#    own pythonic `<function=...>` tag instead of a real tool call, which
#    breaks the research role (needs a tool call to succeed every turn).
#    openai/gpt-oss-120b is Groq's own recommended model for reliable tool
#    use and is the default here for that reason; llama-3.3-70b-versatile
#    remains available (set GROQ_MODEL explicitly) but is best reserved for
#    the synthesis role, which never calls a tool at all
#    (enable_tools=False) and so is unaffected by this bug.
# 2. The free tier's RPM cap (~30 RPM for either model above) is easy to
#    blow through the instant 8 parallel research agents all fire their
#    first request in the same second — confirmed live: every agent hit 429
#    immediately. GROQ_RPM_LIMIT paces every request from this process
#    through a shared rate limiter (providers/groq_provider.py) so the
#    aggregate stays under budget regardless of how many agents are calling
#    concurrently; GROQ_TPM_LIMIT (8000, the allowance actually observed on
#    this account — see prompts/CHANGELOG.md v8) does the same for the
#    per-minute token budget, compacting older tool results in place rather
#    than failing outright when a single long research run would exceed it.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "3500"))
GROQ_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "8000"))
GROQ_RPM_LIMIT = int(os.getenv("GROQ_RPM_LIMIT", "28"))
GROQ_TOOL_RESULT_MAX_CHARS = int(os.getenv("GROQ_TOOL_RESULT_MAX_CHARS", "1800"))
# GPT-OSS models (unlike Llama) are hybrid reasoning models with a
# reasoning_effort knob — the same class of hidden-token burn OLLAMA_THINK
# works around for qwen3.5 above. Left at "low" by default: this account's
# GROQ_TPM_LIMIT (8000) is tight enough that "medium"/"high" reasoning could
# burn most of a request's token budget on hidden thinking before ever
# reaching a tool call. providers/groq_provider.py only sends this param
# when GROQ_MODEL contains "gpt-oss" — Llama models don't support it.
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")

# --- Tavily: web search built for AI agents ---------------------------------
# Optional. If set, mcp_server/scraper_server.py's web_search_ddg tool calls
# the Tavily Search API instead of scraping DuckDuckGo/metasearch backends
# via `ddgs` — Tavily is purpose-built for LLM agents (clean, already-deduped
# results, no bot-detection flakiness) and has a free tier (1,000 searches/
# month, no credit card). When unset, the tool falls back to the free,
# no-key `ddgs` path so the project still runs with zero configuration.
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# --- Multi-agent mode: N parallel per-topic research agents + one synthesis agent ---
# Each role can use a different provider/model — e.g. a fast/cheap model for
# the parallel research agents and a stronger reasoning model for the final
# synthesis/writer agent. Defaults to Ollama for both roles: no external API,
# so no rate limit to hit no matter how many of the 8 research agents fire
# at once — the 8 calls just queue locally instead of failing. Falls back to
# that provider's own configured model when the *_MODEL var is unset. If you
# have a paid/higher-tier Gemini account, "gemini" is a faster alternative;
# under the free tier's default RPM cap, 8 parallel calls are likely to hit
# the same rate-limit problem groq and gemma did.
RESEARCH_AGENT_PROVIDER = os.getenv("RESEARCH_AGENT_PROVIDER", "ollama")
RESEARCH_AGENT_MODEL = os.getenv("RESEARCH_AGENT_MODEL") or None
SYNTHESIS_AGENT_PROVIDER = os.getenv("SYNTHESIS_AGENT_PROVIDER", "ollama")
SYNTHESIS_AGENT_MODEL = os.getenv("SYNTHESIS_AGENT_MODEL") or None

# Increment version at every deep change of either multi-agent prompt (see
# prompts/multiagent_research_prompt.md and prompts/multiagent_synthesis_prompt.md)
# and log the change in prompts/CHANGELOG.md.
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v8")

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8000"))

# --- Supabase: persistent storage for generated reports ---------------------
# Optional. When unset, services/storage_service.py no-ops and the app keeps
# behaving exactly like the local-only prototype (files only in outputs/,
# history only in the browser's localStorage). Set these to make every
# generated report durable across restarts/redeploys (Render's disk is
# ephemeral) and visible to every user of the deployed UI, not just the
# browser that generated it. Use the Supabase project's SERVICE ROLE key
# here, never the anon key — this is server-side only, the frontend never
# talks to Supabase directly.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "reports")

# --- HTTP Basic Auth: gate for the deployed UI -------------------------------
# Optional. When BASIC_AUTH_USER is unset, main.py's BasicAuthMiddleware
# no-ops (local dev stays open). Set both when deploying somewhere reachable
# by anyone other than you, e.g. Render.
BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USER")
BASIC_AUTH_PASSWORD = os.getenv("BASIC_AUTH_PASSWORD")

"""Shared result type and provider registry for every provider's run_agent().

Every provider module exposes the same shape:

    async def run_agent(
        session: ClientSession | None,
        system_prompt: str,
        company_input: str,
        *,
        model: str | None = None,
        enable_tools: bool = True,
    ) -> RunResult

`model` overrides that provider's configured default model (config.py),
letting a caller pick a specific model per agent instance instead of only
per provider. `enable_tools=False` runs a single tool-free turn (no MCP
session required) — used by the multi-agent synthesis agent, which only
writes from evidence it's given and must never go search or fetch on its
own.
"""

import importlib
from dataclasses import dataclass

from config import ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY


@dataclass
class RunResult:
    text: str
    model: str
    stop_reason: str | None = None
    truncated: bool = False


PROVIDER_MODULES = {
    "anthropic": "providers.anthropic_provider",
    "azure": "providers.azure_provider",
    "gemini": "providers.gemini_provider",
    "ollama": "providers.ollama_provider",
    "groq": "providers.groq_provider",
    "mistral": "providers.mistral_provider",
}

# Providers whose API key lives directly in config.py and is worth checking
# before import, so a missing key raises a clear message instead of a raw
# import-time or first-request failure. azure checks its own key inside
# run_agent already; ollama needs none (local, no key).
_REQUIRED_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
    "gemini": ("GEMINI_API_KEY", GEMINI_API_KEY),
    "groq": ("GROQ_API_KEY", GROQ_API_KEY),
    "mistral": ("MISTRAL_API_KEY", MISTRAL_API_KEY),
}


def require_provider_configured(provider: str) -> None:
    """Raise a friendly RuntimeError if a provider is missing its API key."""
    check = _REQUIRED_KEYS.get(provider)
    if check and not check[1]:
        name, _ = check
        raise RuntimeError(f"{name} not set. Check the .env file.")


def resolve_run_agent(provider: str):
    """Look up and import the run_agent() coroutine function for a provider name."""
    module_name = PROVIDER_MODULES.get(provider)
    if module_name is None:
        raise ValueError(f"Unknown provider: {provider!r}. Use one of: {', '.join(PROVIDER_MODULES)}.")
    require_provider_configured(provider)
    module = importlib.import_module(module_name)
    return module.run_agent

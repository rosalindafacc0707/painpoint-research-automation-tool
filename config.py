import os
from dotenv import load_dotenv

# Secrets live in .env; non-secret app config lives in .env.development.
# Load both; .env values take precedence (loaded last, override=True).
load_dotenv(".env.development")
load_dotenv(".env", override=True)

# --- Provider switch ------------------------------------------------------
# "anthropic" -> Claude via the Anthropic API (default)
# "azure"     -> Azure OpenAI / Azure AI Foundry deployment
# "gemini"    -> Google Gemini API
# "gemma"     -> Google-hosted Gemma API
# "ollama"    -> local open-weight model served by Ollama
# "groq"      -> high-speed hosted open-weight model
# "mistral"   -> Mistral La Plateforme API
PROVIDER = os.getenv("PROVIDER", "anthropic")

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

# Gemma is served through the Gemini API and can reuse the same AI Studio key.
# GEMMA_API_KEY is optional when GEMINI_API_KEY is already configured.
GEMMA_API_KEY = os.getenv("GEMMA_API_KEY") or GEMINI_API_KEY
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")

# qwen3.5:9b is the quality / memory balance for this Mac's 16 GB unified
# memory. It supports tool calling and a 32k context is useful for research.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "900"))

# --- Groq: high-speed hosted open-weight models -----------------------------
# GPT-OSS 120B is the quality-first choice for this research/report workflow.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "medium")
# Keep the default below the current 8k TPM allowance of a new on-demand
# account. The provider reduces it further as tool-result history grows.
GROQ_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "3500"))
GROQ_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "8000"))
GROQ_TOOL_RESULT_MAX_CHARS = int(os.getenv("GROQ_TOOL_RESULT_MAX_CHARS", "1800"))

# --- Mistral La Plateforme --------------------------------------------------
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")

# Increment version at every deep change of the system prompt and create a new file prompts/system_prompt_vN.md
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v6")

SYSTEM_PROMPT_PATH = f"prompts/system_prompt_{PROMPT_VERSION}.md"

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8000"))

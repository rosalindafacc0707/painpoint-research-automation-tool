import os
from dotenv import load_dotenv

# Secrets live in .env; non-secret app config lives in .env.development.
# Load both; .env values take precedence (loaded last, override=True).
load_dotenv(".env.development")
load_dotenv(".env", override=True)

# --- Provider switch ------------------------------------------------------
# "anthropic"  -> Claude via the Anthropic API (default)
# "opensource" -> any OpenAI-compatible endpoint (e.g. GPT-OSS via Ollama,
#                 vLLM, LM Studio, or a hosted provider like Groq/Together)
PROVIDER = os.getenv("PROVIDER", "anthropic")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-5")

# --- Open-source / self-hosted backend -------------------------------------
# Defaults target a local Ollama instance running GPT-OSS
# (`ollama pull gpt-oss:20b && ollama serve`). Point OPENSOURCE_BASE_URL at
# any other OpenAI-compatible endpoint to use a different runtime/provider.
OPENSOURCE_BASE_URL = os.getenv("OPENSOURCE_BASE_URL", "http://localhost:11434/v1")
OPENSOURCE_MODEL = os.getenv("OPENSOURCE_MODEL", "gpt-oss:20b")
# Local runtimes (Ollama, LM Studio) ignore this but the OpenAI SDK requires
# a non-empty string. Set a real key here if OPENSOURCE_BASE_URL points to a
# hosted provider (Groq, Together, ...).
OPENSOURCE_API_KEY = os.getenv("OPENSOURCE_API_KEY", "not-needed")

# Increment version at every deep change of the system prompt and create a new file prompts/system_prompt_vN.md
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1")

SYSTEM_PROMPT_PATH = f"prompts/system_prompt_{PROMPT_VERSION}.md"

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8000"))

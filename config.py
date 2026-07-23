import os
from dotenv import load_dotenv

# Secrets live in .env; non-secret app config lives in .env.development.
# Load both; .env values take precedence (loaded last, override=True).
load_dotenv(".env.development")
load_dotenv(".env", override=True)

# --- Provider switch ------------------------------------------------------
# "anthropic" -> Claude via the Anthropic API (default)
# "azure"     -> Azure OpenAI / Azure AI Foundry deployment
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

# Increment version at every deep change of the system prompt and create a new file prompts/system_prompt_vN.md
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v4")

SYSTEM_PROMPT_PATH = f"prompts/system_prompt_{PROMPT_VERSION}.md"

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8000"))

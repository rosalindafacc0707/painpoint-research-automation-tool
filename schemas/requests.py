from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProviderName = Literal["anthropic", "azure", "gemini", "ollama", "groq"]


class CompanyIntake(BaseModel):
    """Intake fields mirroring inputs/sample_company_input.md."""

    company_name: str = Field(..., min_length=1, description="Nome dell'azienda prospect (campo obbligatorio).")
    website: str | None = Field(default=None, description="Sito web dell'azienda.")
    country_region: str | None = Field(default=None, description="Paese o area geografica di riferimento.")
    department: str | None = Field(default=None, description="Divisione o business unit target.")
    industry: str | None = Field(default=None, description="Settore di appartenenza.")
    research_lens: str | None = Field(
        default=None,
        description="Lente di ricerca specifica, se diversa dal default CVC / Marketing Operations.",
    )


class GenerateMdDocRequestMultiAgent(CompanyIntake):
    """Multi-agent variant: several parallel per-topic research agents feed
    one synthesis agent that writes the final report. Each role's
    provider/model is independently overridable so the right model can be
    picked for each agent.
    """

    research_provider: ProviderName | None = Field(
        default=None, description="Provider used by each parallel per-topic research agent."
    )
    research_model: str | None = Field(
        default=None,
        description="Model override for the research agents (defaults to the provider's configured model).",
    )
    synthesis_provider: ProviderName | None = Field(
        default=None, description="Provider used by the final synthesis/writer agent."
    )
    synthesis_model: str | None = Field(
        default=None,
        description="Model override for the synthesis agent (defaults to the provider's configured model).",
    )

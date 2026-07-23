from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GenerateMdDocRequest(BaseModel):
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
    provider: Literal["anthropic", "azure"] | None = Field(
        default=None, description="Override del PROVIDER configurato in .env.development."
    )

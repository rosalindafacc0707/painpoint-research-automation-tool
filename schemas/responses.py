from __future__ import annotations

from pydantic import BaseModel


class GenerateMdDocResponse(BaseModel):
    filename: str
    company: str
    provider: str
    model: str
    prompt_version: str
    stop_reason: str | None
    truncated: bool
    download_url: str

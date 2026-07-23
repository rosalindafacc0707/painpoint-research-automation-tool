"""Shared result type returned by every provider's run_agent()."""

from dataclasses import dataclass


@dataclass
class RunResult:
    text: str
    model: str
    stop_reason: str | None = None
    truncated: bool = False

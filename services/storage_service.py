"""Persistent, cross-device storage for generated reports (Supabase).

Render's disk is ephemeral (wiped on every restart/redeploy) and the old UI
history lived only in the browser's localStorage — invisible across
devices/browsers. This module uploads every generated .md/.docx to a
Supabase Storage bucket and indexes it in a Postgres table, so any user of
the deployed UI can list and re-download every report ever generated.

No-ops safely when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY aren't set, so
local dev (and the CLI script) keep working exactly as before with zero
configuration. Uses the service-role key — this module is called only from
the backend, never exposed to the frontend.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from config import SUPABASE_BUCKET, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

TABLE = "reports"


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


@lru_cache(maxsize=1)
def _client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def save_report(
    *,
    company_name: str,
    filename: str,
    docx_filename: str,
    md_text: str,
    docx_bytes: bytes,
    provider: str,
    model: str,
    prompt_version: str,
    stop_reason: str | None,
    truncated: bool,
) -> str:
    """Upload both files and insert the index row. Returns the new report id."""
    client = _client()
    bucket = client.storage.from_(SUPABASE_BUCKET)

    bucket.upload(
        filename,
        md_text.encode("utf-8"),
        {"content-type": "text/markdown; charset=utf-8", "upsert": "true"},
    )
    bucket.upload(
        docx_filename,
        docx_bytes,
        {
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "upsert": "true",
        },
    )

    row = {
        "company_name": company_name,
        "md_path": filename,
        "docx_path": docx_filename,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "stop_reason": stop_reason,
        "truncated": truncated,
    }
    result = client.table(TABLE).insert(row).execute()
    return result.data[0]["id"]


def list_reports() -> list[dict]:
    if not is_configured():
        return []
    result = _client().table(TABLE).select("*").order("created_at", desc=True).execute()
    return result.data


def get_report(report_id: str) -> dict | None:
    result = _client().table(TABLE).select("*").eq("id", report_id).limit(1).execute()
    return result.data[0] if result.data else None


def signed_url(path: str, expires_in: int = 3600) -> str:
    bucket = _client().storage.from_(SUPABASE_BUCKET)
    return bucket.create_signed_url(path, expires_in)["signedURL"]

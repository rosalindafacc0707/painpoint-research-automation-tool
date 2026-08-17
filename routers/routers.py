from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from schemas.requests import GenerateMdDocRequestMultiAgent
from schemas.responses import GenerateMdDocResponse
from services import storage_service
from services.multiagent_service import OUTPUTS_DIR, generate_pain_point_report_multiagent

router = APIRouter(prefix="/painpoint-researcher", tags=["research"])

MEDIA_TYPES = {
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _report_error_from_group(exc: ExceptionGroup) -> str | None:
    """Extract the actionable provider error wrapped by MCP/anyio task groups."""
    for child in exc.exceptions:
        if isinstance(child, ExceptionGroup):
            detail = _report_error_from_group(child)
            if detail:
                return detail
        elif isinstance(child, (RuntimeError, ValueError)):
            return str(child)
    return None


@router.post("/generate-pain-point-md-multiagent", response_model=GenerateMdDocResponse)
async def generate_multiagent(body: GenerateMdDocRequestMultiAgent):
    """Multi-agent variant: parallel per-topic research agents + one synthesis agent."""
    try:
        result = await generate_pain_point_report_multiagent(body)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ExceptionGroup as exc:
        detail = _report_error_from_group(exc)
        if detail:
            raise HTTPException(status_code=502, detail=detail) from exc
        raise

    return GenerateMdDocResponse(**result)


@router.get("/download/{filename}")
async def download(filename: str):
    file_path = (OUTPUTS_DIR / filename).resolve()
    if file_path.parent != OUTPUTS_DIR.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )


@router.get("/reports")
async def list_reports():
    """Every report ever generated, from Supabase — shared across all users/
    devices, unlike the browser-local history it replaces. Empty list when
    Supabase isn't configured (local dev, no persistence set up)."""
    return storage_service.list_reports()


def _get_report_or_404(report_id: str) -> dict:
    report = storage_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.get("/reports/{report_id}/content")
async def report_content(report_id: str):
    """Raw markdown text of a past report, for the same in-page preview
    rendering used right after generation."""
    report = _get_report_or_404(report_id)
    url = storage_service.signed_url(report["md_path"])
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    response.raise_for_status()
    return PlainTextResponse(response.text)


@router.get("/reports/{report_id}/download")
async def report_download(report_id: str, kind: Literal["md", "docx"] = "docx"):
    """Redirect to a time-limited Supabase signed URL — binary files are
    streamed straight from Storage, never proxied through this process."""
    report = _get_report_or_404(report_id)
    path = report["md_path"] if kind == "md" else report["docx_path"]
    return RedirectResponse(storage_service.signed_url(path))

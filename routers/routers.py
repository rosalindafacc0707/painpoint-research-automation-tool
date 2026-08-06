from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas.requests import GenerateMdDocRequestMultiAgent
from schemas.responses import GenerateMdDocResponse
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

    return GenerateMdDocResponse(
        **result,
        download_url=f"/painpoint-researcher/download/{result['filename']}",
        docx_download_url=f"/painpoint-researcher/download/{result['docx_filename']}",
    )


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

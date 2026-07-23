from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas.requests import GenerateMdDocRequest
from schemas.responses import GenerateMdDocResponse
from services.report_service import OUTPUTS_DIR, generate_pain_point_report

router = APIRouter(prefix="/painpoint-researcher", tags=["research"])


@router.post("/generate-pain-point-md", response_model=GenerateMdDocResponse)
async def generate(body: GenerateMdDocRequest):
    try:
        result = await generate_pain_point_report(body)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GenerateMdDocResponse(
        **result,
        download_url=f"/painpoint-researcher/download/{result['filename']}",
    )


@router.get("/download/{filename}")
async def download(filename: str):
    file_path = (OUTPUTS_DIR / filename).resolve()
    if file_path.parent != OUTPUTS_DIR.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(
        path=file_path,
        media_type="text/markdown",
        filename=filename,
    )

"""Same-origin, local-only web entry point; no job creation on GET."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC = Path(__file__).resolve().parents[1] / "static"
router = APIRouter()


@router.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@router.get("/recommendations", include_in_schema=False)
def recommendations():
    return FileResponse(STATIC / "recommendations.html", headers={"Cache-Control": "no-store"})

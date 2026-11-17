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


@router.get("/sns", include_in_schema=False)
def sns():
    return FileResponse(STATIC / "sns.html", headers={"Cache-Control": "no-store"})


@router.get("/verification", include_in_schema=False)
def verification_page():
    return FileResponse(STATIC / "verification.html", headers={"Cache-Control": "no-store"})


@router.get("/editor", include_in_schema=False)
def caption_editor():
    return FileResponse(STATIC / "editor.html", headers={"Cache-Control": "no-store"})


@router.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(STATIC / "login.html")


@router.get("/my-data", include_in_schema=False)
def data_page():
    return FileResponse(STATIC / "my-data.html")

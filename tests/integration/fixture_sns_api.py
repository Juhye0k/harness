"""Only this test entrypoint replaces OAuth; production always uses real adapter."""

import os
from pathlib import Path

from fastapi.responses import FileResponse

from app.api import analyses, editor
from app.main import app  # noqa: F401
from app.services import sns
from tests.integration.faults import fixture_publish, fixture_video_publish
from tests.integration.fixture_sns_provider import FixtureYouTube

sns.YouTubeProvider = FixtureYouTube
app.dependency_overrides[analyses.publisher] = lambda: fixture_publish
editor.publish_video_job = fixture_video_publish


@app.middleware("http")
async def local_demo_frame(request, call_next):
    response = await call_next(request)
    # The fixture-only walkthrough keeps its warning above a same-origin iframe.
    # Production never imports this module; the ordinary fixture suite keeps none.
    if os.getenv("SHORTFORM_DEMO") == "1" and request.url.path == "/sns":
        response.headers["Content-Security-Policy"] = response.headers[
            "Content-Security-Policy"
        ].replace("frame-ancestors 'none'", "frame-ancestors 'self'")
    return response


@app.get("/demo", include_in_schema=False)
def demo_walkthrough():
    return FileResponse(
        Path(__file__).with_name("demo.html"), headers={"Cache-Control": "no-store"}
    )


@app.get("/demo.js", include_in_schema=False)
def demo_script():
    return FileResponse(Path(__file__).with_name("demo.js"), headers={"Cache-Control": "no-store"})

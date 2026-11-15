import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize(
    "path,media",
    [("/", "text/html"), ("/static/app.js", "javascript"), ("/static/app.css", "text/css")],
)
def test_web_assets_without_infrastructure(path, media):
    response = TestClient(app).get(path)
    assert response.status_code == 200
    assert media in response.headers["content-type"]


def test_job_query_renders_page_without_creating_job():
    response = TestClient(app).get("/?job=invalid")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

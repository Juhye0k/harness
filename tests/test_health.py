import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_liveness_does_not_access_infrastructure(monkeypatch):
    def unexpected():
        raise AssertionError("Liveness must not access dependencies")

    monkeypatch.setattr(main, "check_database", unexpected)
    monkeypatch.setattr(main, "check_redis", unexpected)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("failed", [None, "postgresql", "redis", "both"])
def test_readiness_reports_dependency_failure_without_leaking_details(monkeypatch, failed):
    def probe(name):
        def run():
            if failed in (name, "both"):
                raise RuntimeError("password=do-not-expose-this")

        return run

    monkeypatch.setattr(main, "check_database", probe("postgresql"))
    monkeypatch.setattr(main, "check_redis", probe("redis"))
    response = client.get("/health/ready")
    assert response.status_code == (503 if failed else 200)
    assert "do-not-expose" not in response.text
    for name, state in response.json()["checks"].items():
        assert state == ("unavailable" if failed in (name, "both") else "ok")

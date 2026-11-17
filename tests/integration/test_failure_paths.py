"""Scoped faults: assert business state, user-facing behavior and actual effect counts."""

import hashlib
import os
from uuid import UUID, uuid4

import httpx
import pytest
from playwright.sync_api import expect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.analysis_repository import AnalysisRepository
from app.config import get_settings
from app.models import ProviderCall
from tests.integration.failure_artifacts import observed_browser
from tests.integration.faults import Faults
from tests.integration.test_analysis_flow import BASE, submit, wait

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required"
    ),
]


@pytest.mark.parametrize(
    "stage,code",
    [
        ("transcription", "PROVIDER_ACCESS_DENIED"),
        ("proposal", "RATE_LIMITED"),
        ("scoring", "TIMEOUT"),
        ("publish", "DISPATCH_FAILED"),
    ],
)
def test_analysis_failure_is_terminal_without_duplicate_provider_calls(stage, code):
    rid = uuid4()
    fault = Faults(rid)
    with fault.connection() as redis:
        redis.hset(f"failure-request:{rid}", mapping={"fail_at": stage, "code": code})
    body = {"request_id": str(rid), "url": "https://fixture.example/analysis.mp4"}
    with httpx.Client(base_url=BASE, timeout=20) as client:
        response = client.post("/analyses", json=body)
        assert response.status_code == 202, response.text
        aid = response.json()["analysis_id"]
        result = wait(client, f"/analyses/{aid}")
        assert result["status"] == "failed" and result["error"]["code"] == code
        assert result["candidates"] == [] and "private-fixture-sentinel" not in str(result)
        assert client.get(f"/analyses/{aid}/subtitles.srt").status_code == 409
        assert client.post("/analyses", json=body).json()["analysis_id"] == aid
        with Session(AnalysisRepository().engine) as session:
            calls = list(
                session.scalars(select(ProviderCall).where(ProviderCall.analysis_id == UUID(aid)))
            )
            assert len({c.stage for c in calls}) == len(calls)
            if stage == "publish":
                assert not calls
            else:
                assert next(c for c in calls if c.stage == stage).state == "failed"
    with observed_browser("test_failure_paths") as page:
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page.goto(BASE + f"/recommendations?analysis={aid}")
        expect(page.locator("#analysis-state")).to_contain_text(code)
        page.reload()
        expect(page.locator("#analysis-state")).to_contain_text(code)
        assert not posts and page.locator(".edit-candidate").count() == 0
    with Faults(aid).connection() as redis:
        events = redis.hgetall(f"failure:{aid}:events")
        assert events["publish"] == "1"
        if stage != "publish":
            assert events[stage] == "1" and events["analysis-claim"] == "1"


@pytest.fixture(scope="module")
def selected():
    with httpx.Client(base_url=BASE, timeout=20) as client:
        result = submit(client)
        aid = result["analysis_id"]
        cid = result["candidates"][0]["id"]
        data = client.get(f"/analyses/{aid}/candidates/{cid}/editor").json()
        before = client.get(f"/analyses/{aid}/source-video").content
        return aid, cid, data, hashlib.sha256(before).hexdigest()


@pytest.mark.parametrize("code", ["TOOL_FAILED", "TIMEOUT", "OUTPUT_INVALID", "FONT_MISSING"])
def test_failed_render_has_no_download_or_upload_and_preserves_source(selected, code):
    aid, cid, data, before = selected
    base = f"/analyses/{aid}/candidates/{cid}"
    cues = [
        {k: c[k] for k in ("source_segment_id", "start_ms", "end_ms", "lines")}
        for c in data["suggested"]["cues"]
    ]
    cues[0]["lines"] = [code]
    with httpx.Client(base_url=BASE, timeout=20) as client:
        saved = client.post(
            base + "/caption-revisions",
            json={"source_version": data["source_version"], "cues": cues, "reviewed": True},
        )
        assert saved.status_code == 201, saved.text
        rid = saved.json()["revision_id"]
        with Faults(rid).connection() as redis:
            redis.hset(f"failure-revision:{rid}", mapping={"fail_at": "render", "code": code})
        job = client.post(base + f"/caption-revisions/{rid}/exports", json={}).json()
        jid = job["job_id"]
        result = wait(client, f"/jobs/{jid}")
        assert result["status"] == "failed" and result["error"]["code"] == code
        assert result["download_url"] is None
        assert client.get(f"/jobs/{jid}/download").status_code == 409
        assert client.get(f"/jobs/{jid}/subtitles.srt").status_code == 409
        assert (
            hashlib.sha256(client.get(f"/analyses/{aid}/source-video").content).hexdigest()
            == before
        )
        assert (
            client.post(base + f"/caption-revisions/{rid}/exports", json={}).json()["job_id"] == jid
        )
        # A duplicate broker delivery must not enter rendering a second time.
        from app.adapters.job_publisher import publish_video_job

        publish_video_job(UUID(jid), uuid4())
    with observed_browser("test_failure_paths") as page:
        page.goto(BASE + f"/editor?analysis={aid}&candidate={cid}&revision={rid}")
        expect(page.locator("#render-state")).to_contain_text("출력 실패")
        expect(page.locator("#final-result")).to_be_hidden()
        expect(page.locator("#render-final")).to_be_disabled()
    with Faults(jid).connection() as redis:
        assert redis.hget(f"failure:{jid}:events", "render") == "1"


def test_save_render_and_sns_confirmation_responses_can_be_lost(selected):
    aid, cid, _, _ = selected
    with observed_browser("test_failure_paths") as page:
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page.goto(BASE + f"/editor?analysis={aid}&candidate={cid}")
        expect(page.locator("#caption-rows textarea").first).to_be_visible()
        page.locator("#caption-rows textarea").first.fill("응답 유실 확인")
        page.locator("#caption-reviewed").check()

        def lose(route):
            response = route.fetch()
            assert response.ok
            route.abort()

        page.route("**/caption-revisions", lose)
        page.locator("#save-captions").click()
        expect(page.locator("#editor-message")).to_contain_text("저장 결과를 확인하지 못했습니다")
        page.reload()
        expect(page.locator("#render-final")).to_be_enabled()
        expect(page.locator("#caption-rows textarea").first).to_have_value("응답 유실 확인")
        assert len([url for url in posts if url.endswith("/caption-revisions")]) == 1
        page.route("**/caption-revisions/*/exports", lose)
        page.locator("#render-final").click()
        expect(page.locator("#render-state")).to_contain_text("접수 결과를 확인하지 못했습니다")
        page.reload()
        expect(page.locator("#final-result")).to_be_visible(timeout=90000)
        assert len([url for url in posts if url.endswith("/exports")]) == 1
        page.locator("#final-sns").click()
        # Prepare only a fixture OAuth account in this same browser session.
        session = page.request.get(BASE + "/sns/session").json()
        from urllib.parse import parse_qs, urlsplit

        auth = page.request.post(
            BASE + "/sns/youtube/connect", headers={"X-SNS-CSRF": session["csrf"]}
        ).json()
        state = parse_qs(urlsplit(auth["authorization_url"]).query)["state"][0]
        page.request.get(BASE + f"/sns/youtube/callback?state={state}&code=fixture-code")
        page.reload()
        expect(page.locator("#upload-form")).to_be_visible()
        page.locator("#title").fill("응답 유실 테스트")
        page.locator("#kids").select_option("false")
        page.locator("#prepare").click()
        expect(page.locator("#review-panel")).to_be_visible()
        page.locator("#approved").check()
        page.route("**/sns/uploads/*/confirm", lose)
        page.locator("#confirm").click()
        expect(page.locator("#notice")).to_contain_text("접수 결과를 확인하지 못했어요")
        page.reload()
        expect(page.locator("#upload-state")).to_contain_text("업로드가 완료됐어요", timeout=30000)
        uid = parse_qs(urlsplit(page.url).query)["upload"][0]
        with Faults(uid).connection() as redis:
            assert redis.hget(f"sns-fixture:{uid}", "sent") == "1"
        assert len([url for url in posts if url.endswith("/confirm")]) == 1


def test_duplicate_delivery_during_running_renders_once(selected):
    from celery import Celery

    from app.adapters.job_publisher import publish_video_job

    aid, cid, data, _ = selected
    base = f"/analyses/{aid}/candidates/{cid}"
    cues = [
        {k: c[k] for k in ("source_segment_id", "start_ms", "end_ms", "lines")}
        for c in data["suggested"]["cues"]
    ]
    cues[0]["lines"] = ["중복 전달 확인"]
    with httpx.Client(base_url=BASE, timeout=20) as client:
        revision = client.post(
            base + "/caption-revisions",
            json={"source_version": data["source_version"], "cues": cues, "reviewed": True},
        ).json()["revision_id"]
        with Faults(revision).connection() as redis:
            redis.hset(f"failure-revision:{revision}", mapping={"pause_at": "video-claim"})
        job = client.post(base + f"/caption-revisions/{revision}/exports", json={}).json()["job_id"]
        fault = Faults(job)
        try:
            with fault.connection() as redis:
                assert redis.blpop(fault.key + ":ready", timeout=30)[1] == "video-claim"
            assert client.get(f"/jobs/{job}").json()["status"] == "running"
            for _ in range(2):
                publish_video_job(UUID(job), uuid4())
        finally:
            with fault.connection() as redis:
                redis.lpush(fault.key + ":release", "continue")
        assert wait(client, f"/jobs/{job}")["status"] == "succeeded"
        # A FIFO sentinel confirms the worker consumed both duplicate messages.
        with Celery(
            "failure-sentinel", broker=get_settings().redis_url, backend=get_settings().redis_url
        ) as celery:
            assert celery.send_task("shortform.diagnostics.ping", queue="video").get(
                timeout=30
            ) == {"status": "ok"}
        with fault.connection() as redis:
            assert redis.hget(fault.key + ":events", "video-claim") == "1"
            assert redis.hget(fault.key + ":events", "render") == "1"

"""Real PostgreSQL locks and uniqueness; no provider networking."""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.adapters.sns_repository import SnsRepository
from app.domain.sns import SnsError, approval_values, digest
from app.models import SnsAccount, SnsOAuthState, SnsUpload, VideoJob, utcnow

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Isolated DB required"),
]


@pytest.fixture
def stored():
    repo = SnsRepository()
    owner = digest(str(uuid4()))
    account = repo.connect(owner, {"id": str(uuid4()), "title": "테스트"}, "ciphertext")
    with Session(repo.engine, expire_on_commit=False) as session, session.begin():
        job = VideoJob(
            source_url="https://fixture.example/sample.mp4",
            start_seconds=0,
            status="succeeded",
            output_path="fixture.mp4",
        )
        session.add(job)
        session.flush()

    def draft(title="테스트"):
        return repo.prepare(
            owner, uuid4(), account.id, job.id, "a" * 64, 42, title, "private", False
        )

    yield repo, owner, account, draft
    with repo.engine.begin() as conn:
        conn.execute(delete(SnsUpload).where(SnsUpload.owner == owner))
        conn.execute(delete(SnsAccount).where(SnsAccount.owner == owner))
        conn.execute(delete(VideoJob).where(VideoJob.id == job.id))
        conn.execute(delete(SnsOAuthState).where(SnsOAuthState.owner == owner))


def test_concurrent_confirmation_reuses_one_upload(stored):
    repo, owner, account, draft = stored
    first, second = draft(), draft()
    barrier, sent = Barrier(2), []

    def confirm(upload):
        barrier.wait(timeout=5)
        return repo.confirm(upload.id, owner, approval_values(upload), lambda *a: sent.append(a))

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(confirm, value) for value in (first, second)]
        results = [f.result(timeout=15) for f in futures]
    assert results[0].id == results[1].id
    assert len(sent) == 1
    assert repo.claim(results[0].id) is not None
    assert repo.claim(results[0].id) is None


@pytest.mark.parametrize("fails", [False, True])
def test_sns_claim_waits_for_confirmation_dispatch_commit(stored, fails):
    repo, owner, _, draft = stored
    upload = draft()
    entered, futures = Event(), []
    with ThreadPoolExecutor(1) as pool:

        def claim():
            entered.set()
            return repo.claim(upload.id)

        def publish(*ids):
            future = pool.submit(claim)
            futures.append(future)
            assert entered.wait(timeout=5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
            if fails:
                raise ConnectionError("possibly already delivered")

        result = repo.confirm(upload.id, owner, approval_values(upload), publish)
        claimed = futures[0].result(timeout=15)
    assert result.status == ("failed" if fails else "queued")
    assert (claimed is None) == fails


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "변경된 제목"),
        ("privacy", "public"),
        ("account_version", 999),
        ("output_version", "b" * 64),
        ("made_for_kids", True),
        ("account_id", str(uuid4())),
    ],
)
def test_approval_is_bound_to_exact_fields(stored, field, value):
    repo, owner, _, draft = stored
    upload = draft()
    values = {**approval_values(upload), field: value}
    with pytest.raises(SnsError, match="변경"):
        repo.confirm(upload.id, owner, values, lambda *a: pytest.fail("dispatched"))
    assert repo.get(upload.id).status == "draft"


@pytest.mark.parametrize("change", ["expiry", "reconnect", "disconnect"])
def test_stale_approval_is_rejected(stored, change):
    repo, owner, account, draft = stored
    upload = draft()
    if change == "expiry":
        with repo.engine.begin() as conn:
            conn.execute(
                update(SnsUpload)
                .where(SnsUpload.id == upload.id)
                .values(
                    expires_at=utcnow() - timedelta(seconds=1),
                )
            )
    elif change == "reconnect":
        repo.connect(owner, {"id": account.channel_id, "title": "다시 연결"}, "new-ciphertext")
    else:
        repo.disconnect(account.id, owner)
    with pytest.raises(SnsError):
        repo.confirm(upload.id, owner, approval_values(upload), lambda *a: pytest.fail("dispatch"))


def test_duplicate_new_title_is_not_a_new_upload_and_interruption_is_unknown(stored):
    repo, owner, _, draft = stored
    first = draft()
    repo.confirm(first.id, owner, approval_values(first), lambda *a: None)
    repo.claim(first.id)
    assert repo.mark_unknown(first.id)
    assert not repo.finish(first.id, "succeeded", remote_id="late")
    assert repo.get(first.id).status == "unknown"
    second = draft("새 제목")
    with pytest.raises(SnsError) as exc:
        repo.confirm(second.id, owner, approval_values(second), lambda *a: pytest.fail("dispatch"))
    assert exc.value.code == "DUPLICATE_OUTPUT"


def test_state_is_owner_bound_expiring_and_single_use(stored):
    repo, owner, _, _ = stored
    key = digest(str(uuid4()))
    repo.save_state(key, owner, "encrypted-verifier")
    with pytest.raises(SnsError):
        repo.consume_state(key, "other-owner")
    assert repo.consume_state(key, owner) == "encrypted-verifier"
    with pytest.raises(SnsError):
        repo.consume_state(key, owner)
    repo.save_state(key, owner, "expired")
    with repo.engine.begin() as conn:
        conn.execute(
            update(SnsOAuthState)
            .where(SnsOAuthState.state_hash == key)
            .values(
                expires_at=utcnow() - timedelta(seconds=1),
            )
        )
    with pytest.raises(SnsError):
        repo.consume_state(key, owner)


def test_unrelated_browser_cannot_read_or_confirm_upload(stored):
    repo, owner, account, draft = stored
    upload = draft()
    for action in (
        lambda: repo.get(upload.id, "other"),
        lambda: repo.confirm(upload.id, "other", approval_values(upload), lambda *a: None),
        lambda: repo.disconnect(account.id, "other"),
    ):
        with pytest.raises(SnsError) as exc:
            action()
        assert exc.value.status_code == 404


def test_probe_dispatch_claim_is_single_use_and_cannot_resend(stored):
    repo, owner, _, draft = stored
    upload = draft()
    repo.confirm(upload.id, owner, approval_values(upload), lambda *a: None)
    repo.claim(upload.id)
    repo.record_session(upload.id, "encrypted-session")
    repo.mark_unknown(upload.id)
    sent = []
    repo.request_probe(upload.id, owner, lambda *ids: sent.append(ids))
    repo.request_probe(upload.id, owner, lambda *ids: sent.append(ids))
    assert len(sent) == 1
    task_id = sent[0][1]
    assert repo.claim_probe(upload.id, task_id) is not None
    assert repo.claim_probe(upload.id, task_id) is None
    assert repo.claim(upload.id) is None


def test_lost_prepare_response_reuses_request_id_and_rejects_changed_content(stored):
    repo, owner, account, draft = stored
    first = draft()
    same = repo.prepare(
        owner,
        first.request_id,
        account.id,
        first.job_id,
        "a" * 64,
        42,
        first.title,
        "private",
        False,
    )
    assert same.id == first.id and same.status == "draft"
    with pytest.raises(SnsError) as exc:
        repo.prepare(
            owner,
            first.request_id,
            account.id,
            first.job_id,
            "a" * 64,
            42,
            "다른 제목",
            "private",
            False,
        )
    assert exc.value.code == "REQUEST_CONFLICT"

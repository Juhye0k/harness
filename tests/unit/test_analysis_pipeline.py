from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from app.config import Settings
from app.domain.video import VideoError
from app.services import analysis


class Repository:
    def __init__(self, root, *, audio=True, segments=None):
        self.job = SimpleNamespace(
            id=uuid4(),
            asset_id=uuid4(),
            genre="unknown",
            purpose="balanced",
            config={"model": "fixture"},
        )
        (root / "source.mp4").write_bytes(b"source")
        self.original = SimpleNamespace(
            id=self.job.asset_id,
            path="source.mp4",
            state="ready",
            sha256=analysis.video.checksum(root / "source.mp4"),
            has_audio=audio,
            duration_ms=90000,
        )
        self.saved_segments = segments
        self.calls, self.finishes = [], []

    def claim(self, job_id):
        return self.job

    def asset(self, asset_id):
        return self.original

    def stage(self, *args):
        pass

    def transcript(self, *args):
        return SimpleNamespace(
            id=uuid4(), segments=self.saved_segments
        ), self.saved_segments is None

    def save_transcript(self, transcript_id, segments=None, failed=False):
        self.saved_segments = segments

    def call_start(self, job_id, stage):
        self.calls.append(stage)

    def call_finish(self, *args):
        pass

    def finish(self, job_id, *args, **kwargs):
        self.finishes.append(kwargs)


class Providers:
    def __init__(self, raw=None, error=None):
        self.raw = raw if raw is not None else {"phrases": []}
        self.error = error

    def transcribe(self, audio):
        if self.error:
            raise self.error
        return self.raw, {}

    def recommend(self, *args):
        return {"candidates": []}, {}


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("noaudio", "NO_AUDIO"),
        ("nospeech", "NO_SPEECH"),
        ("disabled", "AI_DISABLED"),
        ("timeout", "TIMEOUT"),
        ("provider", "PROVIDER_RATE_LIMIT"),
        ("missing", "RESULT_UNAVAILABLE"),
        ("changed", "SOURCE_CHANGED"),
    ],
)
def test_pipeline_outcomes(tmp_path, monkeypatch, mode, expected):
    repo = Repository(tmp_path, audio=mode != "noaudio")
    monkeypatch.setattr(analysis, "run", lambda *a, **kw: "")
    error = (
        SoftTimeLimitExceeded()
        if mode == "timeout"
        else (VideoError("PROVIDER_RATE_LIMIT", "private") if mode == "provider" else None)
    )
    if mode == "missing":
        (tmp_path / "source.mp4").unlink()
    if mode == "changed":
        (tmp_path / "source.mp4").write_bytes(b"changed")
    analysis.process_analysis(
        repo.job.id,
        repo,
        tmp_path,
        Settings(_env_file=None, enable_paid_ai=mode != "disabled"),
        Providers(error=error),
    )
    result = repo.finishes[-1]
    assert result.get("error", result.get("outcome")) == expected
    assert len(repo.calls) <= 1


def test_reused_transcript_no_second_asr(tmp_path):
    repo = Repository(
        tmp_path, segments=[{"id": "s0000", "start_ms": 0, "end_ms": 30000, "text": "문장"}]
    )
    analysis.process_analysis(
        repo.job.id,
        repo,
        tmp_path,
        Settings(_env_file=None, enable_paid_ai=True),
        Providers(error=AssertionError("ASR called")),
    )
    assert repo.calls == ["proposal"]
    assert repo.finishes[-1]["outcome"] == "NO_SUITABLE_CANDIDATES"

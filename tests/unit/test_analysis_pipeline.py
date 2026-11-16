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
        Settings(
            _env_file=None,
            enable_paid_ai=mode != "disabled",
            transcription_provider="azure",
            recommendation_provider="openai",
        ),
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
        Settings(
            _env_file=None,
            enable_paid_ai=True,
            transcription_provider="azure",
            recommendation_provider="openai",
        ),
        Providers(error=AssertionError("ASR called")),
    )
    assert repo.calls == ["proposal"]
    assert repo.finishes[-1]["outcome"] == "NO_SUITABLE_CANDIDATES"


def test_free_worker_rejects_old_paid_job_before_download(tmp_path):
    repo = Repository(tmp_path)
    analysis.process_analysis(
        repo.job.id,
        repo,
        tmp_path,
        Settings(
            _env_file=None,
            enable_free_ai=True,
            groq_free_tier_confirmed=True,
            recommendation_provider="groq",
        ),
        Providers(error=AssertionError("provider called")),
    )
    assert repo.finishes[-1]["error"] == "PROVIDER_CONFIG"
    assert repo.calls == []


def test_free_transcript_uses_separate_cache_version(tmp_path, monkeypatch):
    from app.adapters.ai import GROQ_ASR_VERSION, provider_config

    settings = Settings(
        _env_file=None,
        enable_free_ai=True,
        groq_free_tier_confirmed=True,
        recommendation_provider="groq",
    )
    repo = Repository(tmp_path)
    repo.job.config = provider_config(settings)
    original = repo.transcript

    def transcript(asset_id, version):
        assert version == GROQ_ASR_VERSION
        return original(asset_id, version)

    repo.transcript = transcript

    def run(args, timeout):
        assert args[-1].endswith("audio.mp3")
        assert "libmp3lame" in args and "64k" in args

    monkeypatch.setattr(analysis, "run", run)
    analysis.process_analysis(repo.job.id, repo, tmp_path, settings, Providers())
    assert repo.finishes[-1]["outcome"] == "NO_SPEECH"


@pytest.mark.parametrize("cached", [False, True])
def test_transcription_only_never_calls_recommendation(tmp_path, monkeypatch, cached):
    from app.adapters.ai import provider_config

    settings = Settings(_env_file=None, enable_free_ai=True, groq_free_tier_confirmed=True)
    segments = [{"id": "s0000", "start_ms": 0, "end_ms": 30000, "text": "문장"}]
    repo = Repository(tmp_path, segments=segments if cached else None)
    repo.job.config = provider_config(settings, "transcription")
    providers = Providers(
        raw={"phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 30000, "text": "문장"}]}
    )
    providers.recommend = lambda *a: pytest.fail("recommendation called")
    monkeypatch.setattr(analysis, "run", lambda *a: None)
    analysis.process_analysis(repo.job.id, repo, tmp_path, settings, providers)
    assert repo.finishes[-1]["outcome"] == "TRANSCRIBED"
    assert repo.calls == ([] if cached else ["transcription"])
    assert repo.saved_segments == segments


def test_recommendation_disabled_fails_before_transcription(tmp_path):
    from app.adapters.ai import provider_config

    settings = Settings(_env_file=None, enable_free_ai=True, groq_free_tier_confirmed=True)
    repo = Repository(tmp_path)
    repo.job.config = provider_config(settings)
    analysis.process_analysis(
        repo.job.id,
        repo,
        tmp_path,
        settings,
        Providers(error=AssertionError("transcription called")),
    )
    assert repo.finishes[-1]["error"] == "RECOMMENDATION_DISABLED"
    assert not repo.calls

"""Saved provider response through PostgreSQL, HTTP subtitles and SRT."""

import os

import httpx
import pytest

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.groq import parse_transcription
from app.domain.recommendations import normalize
from app.domain.subtitles import srt

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Isolated DB/API required"),
]


def test_partial_alignment_survives_storage_and_subtitle_http():
    repo = AnalysisRepository()
    raw = {
        "segments": [
            {"start": 0, "end": 4, "text": "first sentence."},
            {"start": 4, "end": 12, "text": "second. third."},
        ],
        "words": [
            {"start": 0, "end": 4.14, "word": "first sentence."},
            {"start": 4.2, "end": 8, "word": "second."},
            {"start": 8.2, "end": 12, "word": "third."},
        ],
    }
    segments = normalize(parse_transcription(raw), 12000)
    job = repo.create(
        "https://fixture.example/alignment.mp4",
        None,
        "unknown",
        "balanced",
        {"asr_version": "synthetic-partial-alignment-v1", "mode": "transcription"},
    )
    repo.dispatch(job.id, lambda *args: None)
    assert repo.claim(job.id)
    transcript, owned = repo.transcript(job.asset_id, job.config["asr_version"])
    assert owned
    repo.save_transcript(transcript.id, segments)
    assert repo.finish(job.id, outcome="TRANSCRIBED")
    base = os.getenv("TEST_API_URL", "http://api:8000")
    with httpx.Client(base_url=base) as client:
        stored = client.get(f"/analyses/{job.id}/transcript").json()
        assert stored["segments"] == segments
        assert "words" not in stored["segments"][0]
        assert len(stored["segments"][1]["words"]) == 2
        subtitles = client.get(f"/analyses/{job.id}/subtitles").json()
        assert len(subtitles["cues"]) == 3
        assert subtitles["cues"][0]["timing"] == "segment"
        assert all(c["timing"] == "word" for c in subtitles["cues"][1:])
        assert client.get(f"/analyses/{job.id}/subtitles.srt").text == srt(subtitles)
        assert repo.read_transcript(job.asset_id, job.config["asr_version"]) == segments

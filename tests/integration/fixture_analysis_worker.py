"""Synthetic media + deterministic providers. Production code never imports this module."""

import shutil

from app.adapters.process import executable, run
from app.config import get_settings
from app.domain.video import VideoError
from app.services import analysis, video
from app.worker import celery_app


class FixtureProviders:
    def __init__(self, settings):
        assert not settings.openai_api_key.get_secret_value()
        assert not settings.azure_speech_key.get_secret_value()

    def transcribe(self, audio):
        return {
            "phrases": [
                {
                    "offsetMilliseconds": i * 5000,
                    "durationMilliseconds": 5000,
                    "text": f"한국어 인터뷰 테스트 문장 {i}",
                }
                for i in range(36)
            ]
        }, {"provider": "fixture", "cost": None, "usage": None}

    def recommend(self, stage, payload, model):
        if stage == "proposal":
            data = {
                "candidates": [
                    {"start_segment_id": "s0000", "end_segment_id": "s0005", "title": "첫 이야기"},
                    {
                        "start_segment_id": "s0010",
                        "end_segment_id": "s0021",
                        "title": "두 번째 이야기",
                    },
                ]
            }
        else:
            data = {
                "scores": [
                    {
                        "candidate_id": c["id"],
                        "hook": 4,
                        "completeness": 4,
                        "context_independence": 4,
                        "memorable": 3,
                        "editability": 4,
                        "reason": "독립된 이야기와 완결된 답변입니다.",
                        "topic": c["id"],
                        "evidence_ids": [c["segments"][0]["id"]],
                    }
                    for c in payload["candidates"]
                ]
            }
        return data, {"provider": "fixture", "model": "fixture", "cost": None, "usage": None}


def main():
    settings = get_settings()
    fixture = settings.video_data_dir.parent / "analysis-sample.mp4"
    if not fixture.exists():
        run(
            [
                executable("ffmpeg"),
                "-v",
                "error",
                "-n",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=160x90:rate=30:duration=180",
                "-f",
                "lavfi",
                "-i",
                "sine=duration=180",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                str(fixture),
            ],
            60,
        )

    def local_download(url, directory):
        if url != "https://fixture.example/analysis.mp4":
            raise VideoError("DOWNLOAD_FAILED", "External networking disabled")
        target = directory / "source.mp4"
        shutil.copyfile(fixture, target)
        return target

    video.download = local_download
    analysis.Providers = FixtureProviders
    celery_app.worker_main(["worker", "--loglevel=INFO", "--concurrency=1", "-Q", "analysis"])


if __name__ == "__main__":
    main()

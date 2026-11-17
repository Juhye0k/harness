"""Only the downloader is replaced. Real Celery task, DB and FFmpeg still run."""

import shutil

from app.adapters.process import executable, run
from app.config import get_settings
from app.domain.video import VideoError
from app.services import video
from app.worker import celery_app
from tests.integration.faults import install_video_faults


def main():
    settings = get_settings()
    fixture = settings.video_data_dir.parent / "integration-sample.mp4"
    fixture.parent.mkdir(parents=True, exist_ok=True)
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
                "testsrc2=size=160x90:rate=30:duration=20",
                "-f",
                "lavfi",
                "-i",
                "sine=duration=20",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                str(fixture),
            ],
            30,
        )

    def local_download(url, directory):
        if url == "https://fixture.example/tool-failure.mp4":
            raise VideoError("TOOL_FAILED", "fixture failure")
        if url != "https://fixture.example/sample.mp4":
            raise VideoError("DOWNLOAD_FAILED", "External networking disabled in tests")
        target = directory / "source.mp4"
        shutil.copyfile(fixture, target)
        return target

    video.download = local_download
    install_video_faults()
    celery_app.conf.result_backend = settings.redis_url  # Existing diagnostic test only.
    celery_app.worker_main(
        ["worker", "--loglevel=INFO", "--concurrency=1", "-Q", "shortform,video"]
    )


if __name__ == "__main__":
    main()

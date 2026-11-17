"""One bounded analysis task. Stage outputs persist; interrupted tasks never auto-resume."""

import time

from celery.exceptions import SoftTimeLimitExceeded

from app.adapters.ai import Providers, validate_job_config
from app.adapters.media import probe
from app.adapters.process import executable, run
from app.domain.jobs import JobError, output_file
from app.domain.recommendations import candidates, normalize, rank
from app.domain.video import MAX_SECONDS, VideoError
from app.services import video
from app.services.access import worker_guard


def measured(repo, job, stage, call):
    repo.stage(job.id, stage)
    repo.call_start(job.id, stage)  # Unique per stage, even if the process dies mid-call.
    started = time.monotonic()
    try:
        raw, metadata = call()
    except Exception as exc:
        repo.call_finish(
            job.id,
            stage,
            "failed",
            {
                "error_code": exc.code if isinstance(exc, VideoError) else "INTERNAL_ERROR",
                "elapsed_seconds": time.monotonic() - started,
                "usage": None,
                "cost": None,
                **(
                    {"provider_diagnostics": exc.provider_diagnostics}
                    if isinstance(exc, VideoError) and hasattr(exc, "provider_diagnostics")
                    else {}
                ),
            },
        )
        raise
    repo.call_finish(
        job.id, stage, "succeeded", {**metadata, "elapsed_seconds": time.monotonic() - started}
    )
    return raw


@worker_guard("analysis", "repo")
def process_analysis(job_id, repo, root, settings, providers=None):
    job = repo.claim(job_id)
    if job is None:
        return
    providers = providers or Providers(settings)
    try:
        config = validate_job_config(job.config, settings)
        groq_asr = config["transcription_provider"] == "groq"
        repo.stage(job.id, "download")
        asset = repo.asset(job.asset_id)
        if asset.state == "pending":
            directory = root.resolve() / "assets" / str(asset.id)
            directory.mkdir(parents=True, exist_ok=False)
            source = video.download(asset.source_url, directory)
            info = probe(source)
            if info.duration > MAX_SECONDS:
                raise VideoError("LIMIT_EXCEEDED", "원본은 20분 이하여야 합니다.")
            repo.save_asset(
                asset.id,
                path=source.relative_to(root.resolve()).as_posix(),
                sha256=video.checksum(source),
                duration_ms=int(info.duration * 1000),
                has_audio=info.has_audio,
                state="ready",
            )
            asset = repo.asset(asset.id)
        source = output_file(root, asset.path)
        if video.checksum(source) != asset.sha256:
            raise VideoError("SOURCE_CHANGED", "저장한 원본이 변경되었습니다.")
        if not asset.has_audio:
            raise VideoError("NO_AUDIO", "음성 트랙이 없습니다.")
        transcript, owned = repo.transcript(asset.id, config["asr_version"])
        if owned:
            try:
                repo.stage(job.id, "audio")
                # Version-specific directories avoid collisions with other ASR configurations.
                audio_dir = source.parent / config["asr_version"]
                audio_dir.mkdir(exist_ok=True)
                audio = audio_dir / ("audio.mp3" if groq_asr else "audio.wav")
                run(
                    [
                        executable("ffmpeg"),
                        "-nostdin",
                        "-v",
                        "error",
                        "-n",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-i",
                        str(source),
                        "-map",
                        "0:a:0",
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        "-c:a",
                        "libmp3lame" if groq_asr else "pcm_s16le",
                        *(["-b:a", "64k"] if groq_asr else []),
                        str(audio),
                    ],
                    60,
                )
                raw = measured(repo, job, "transcription", lambda: providers.transcribe(audio))
                segments = normalize(raw, asset.duration_ms)
                repo.save_transcript(transcript.id, segments)
            except Exception:
                repo.save_transcript(transcript.id, failed=True)
                raise
        else:
            segments = transcript.segments
        if video.checksum(source) != asset.sha256:
            raise VideoError("SOURCE_CHANGED", "저장한 원본이 변경되었습니다.")
        if not segments:
            repo.finish(job.id, outcome="NO_SPEECH")
            return
        if config["mode"] == "transcription":
            repo.finish(job.id, outcome="TRANSCRIBED")
            return
        # Word timings serve display subtitles, not recommendation prompts.
        segments = [
            {k: v for k, v in segment.items() if k not in ("words", "quality")}
            for segment in segments
        ]
        context = {"genre": job.genre, "purpose": job.purpose}
        raw = measured(
            repo,
            job,
            "proposal",
            lambda: providers.recommend(
                "proposal", {**context, "segments": segments}, job.config["model"]
            ),
        )
        valid, rejected = candidates(raw, segments, asset.duration_ms)
        selected = []
        if valid:
            raw = measured(
                repo,
                job,
                "scoring",
                lambda: providers.recommend(
                    "scoring", {**context, "candidates": valid}, job.config["model"]
                ),
            )
            selected = rank(raw, valid)
        if video.checksum(source) != asset.sha256:
            raise VideoError("SOURCE_CHANGED", "저장한 원본이 변경되었습니다.")
        repo.finish(
            job.id,
            selected,
            rejected,
            outcome="RECOMMENDED" if selected else "NO_SUITABLE_CANDIDATES",
        )
    except SoftTimeLimitExceeded:
        repo.finish(job.id, error="TIMEOUT")
    except (VideoError, JobError) as exc:
        repo.finish(job.id, error=exc.code)
    except Exception:
        # Never persist provider bodies, secrets, local paths or transcript in errors.
        repo.finish(job.id, error="INTERNAL_ERROR")

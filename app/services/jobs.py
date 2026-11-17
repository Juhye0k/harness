"""Job orchestration shared by HTTP and the real Celery task."""

import logging
from pathlib import Path
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.download import validate_url
from app.adapters.job_repository import JobRepository
from app.domain.jobs import JobError, output_file, public_result
from app.domain.video import VideoError, validate_start
from app.services.access import worker_guard
from app.services.video import execute

logger = logging.getLogger(__name__)

# Messages are curated separately from potentially sensitive tool exceptions.
ERROR_MESSAGES = {
    "RESULT_UNAVAILABLE": "저장한 원본이나 출력 파일을 사용할 수 없습니다.",
    "INVALID_INPUT": "영상 입력이 유효하지 않습니다.",
    "INVALID_RANGE": "요청한 구간이 원본 범위를 넘습니다.",
    "INVALID_MEDIA": "영상 파일 또는 필수 정보를 확인할 수 없습니다.",
    "DOWNLOAD_FAILED": "영상을 내려받지 못했습니다.",
    "LIMIT_EXCEEDED": "영상 처리 제한을 초과했습니다.",
    "TIMEOUT": "처리 제한 시간을 초과했습니다.",
    "TOOL_MISSING": "필수 처리 도구가 없습니다.",
    "FONT_MISSING": "한글 자막 폰트가 없습니다.",
    "SUBTITLE_INVALID": "확정 자막과 출력 설정을 확인하세요.",
    "SUBTITLE_INCOMPLETE": "선택 구간의 자막 검수가 필요합니다.",
    "TOOL_FAILED": "영상 처리 도구가 실패했습니다.",
    "OUTPUT_INVALID": "출력 검사를 통과하지 못했습니다.",
    "OUTPUT_CONFLICT": "출력 경로가 충돌했습니다.",
    "IO_FAILED": "영상 파일을 읽거나 저장하지 못했습니다.",
    "TERMINATION_FAILED": "하위 프로세스 종료를 확인하지 못했습니다.",
    "INTERNAL_ERROR": "작업 처리 중 오류가 발생했습니다.",
}


def submit(repository, publish, url: str, start: float):
    validate_start(start)
    _, normalized = validate_url(url)
    job_id = None
    try:
        job = repository.create(normalized, start)
        job_id = job.id
        job = repository.dispatch(job_id, publish)
    except SQLAlchemyError as exc:
        raise JobError(
            "DATABASE_UNAVAILABLE", "작업 저장 상태를 확인할 수 없습니다.", 503, job_id
        ) from exc
    if job.status == "failed":
        raise JobError("DISPATCH_FAILED", job.error_message, 503, job.id)
    return job


@worker_guard("job", "repository")
def process_job(job_id: UUID, repository: JobRepository, root: Path, extractor=None):
    job = repository.claim(job_id)
    if job is None:
        return  # Missing, already running or terminal; never execute again.
    extractor = extractor or execute
    try:
        if getattr(job, "asset_id", None):
            from app.adapters.analysis_repository import AnalysisRepository
            from app.adapters.caption_repository import CaptionRepository
            from app.services.asset_export import execute_asset
            from app.services.final_export import execute_final

            asset = AnalysisRepository(repository.engine).asset(job.asset_id)
            revision = CaptionRepository(repository.engine).for_job(job.id)
            result = (
                execute_final(asset, job, revision, root / str(job.id), root)
                if revision is not None
                else execute_asset(
                    asset, job.start_seconds, job.duration_seconds, root / str(job.id), root
                )
            )
        else:
            result = extractor(job.source_url, job.start_seconds, root=root / str(job.id))
        if result.get("status") == "succeeded":
            public = public_result(result)
            required = {
                "duration",
                "video_track",
                "audio_preserved",
                "decodable",
                "source_unchanged",
            }
            if result.get("render"):
                required |= {"portrait_dimensions", "square_pixels"}
            if set(public["checks"]) != required or not all(
                v is True for v in public["checks"].values()
            ):
                raise ValueError("Output checks incomplete")
            resolved = Path(result["output_path"]).resolve()
            resolved.relative_to((root / str(job.id)).resolve())
            relative = resolved.relative_to(root.resolve()).as_posix()
            output_file(root, relative)
            completion = dict(
                success=True,
                run_id=result["run_id"],
                output_path=relative,
                result=public,
                error_code=None,
                error_message=None,
            )
        else:
            code = result.get("error", {}).get("code", "INTERNAL_ERROR")
            code = code if code in ERROR_MESSAGES else "INTERNAL_ERROR"
            completion = dict(success=False, error_code=code, error_message=ERROR_MESSAGES[code])
    except (VideoError, JobError) as exc:
        code = exc.code if exc.code in ERROR_MESSAGES else "OUTPUT_INVALID"
        completion = dict(success=False, error_code=code, error_message=ERROR_MESSAGES[code])
    except SoftTimeLimitExceeded:
        completion = dict(
            success=False, error_code="TIMEOUT", error_message=ERROR_MESSAGES["TIMEOUT"]
        )
    except Exception as exc:
        logger.warning("Video job failed: job_id=%s error_type=%s", job_id, type(exc).__name__)
        completion = dict(
            success=False,
            error_code="INTERNAL_ERROR",
            error_message=ERROR_MESSAGES["INTERNAL_ERROR"],
        )
    # DB failure here must not be mistaken for completed work. No automatic retry.
    repository.finish(job_id, **completion)

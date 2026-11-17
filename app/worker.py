from celery import Celery

from app.adapters.sns_logging import install_sns_logging
from app.config import get_settings

install_sns_logging()
settings = get_settings()
celery_app = Celery("shortform", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_default_queue="shortform",
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=240,
    task_time_limit=300,
    broker_connection_timeout=3,
    broker_pool_limit=0,
    task_publish_retry=False,
    broker_transport_options={
        "visibility_timeout": 1200,
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
        "retry_on_timeout": False,
        "max_retries": 0,
    },
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="shortform.diagnostics.ping", ignore_result=False)
def diagnostic_ping() -> dict[str, str]:
    """Infrastructure smoke test only; no video processing or business side effects."""
    return {"status": "ok"}


@celery_app.task(
    name="shortform.upload.validate",
    queue="video",
    acks_late=False,
    autoretry_for=(),
    max_retries=0,
    soft_time_limit=180,
    time_limit=240,
)
def validate_uploaded_video(asset_id: str) -> None:
    from uuid import UUID

    from app.adapters.upload_repository import UploadRepository
    from app.services.uploads import validate_upload

    validate_upload(UUID(asset_id), UploadRepository(), get_settings())


@celery_app.task(
    name="shortform.video.extract",
    queue="video",
    acks_late=False,
    autoretry_for=(),
    max_retries=0,
    soft_time_limit=660,
    time_limit=720,
)
def extract_video(job_id: str) -> None:
    from uuid import UUID

    from app.adapters.job_repository import JobRepository
    from app.services.jobs import process_job

    process_job(UUID(job_id), JobRepository(), get_settings().video_data_dir)


@celery_app.task(
    name="shortform.analysis.recommend",
    queue="analysis",
    acks_late=False,
    autoretry_for=(),
    max_retries=0,
    soft_time_limit=960,
    time_limit=1020,
)
def recommend_video(job_id: str) -> None:
    from uuid import UUID

    from app.adapters.analysis_repository import AnalysisRepository
    from app.services.analysis import process_analysis

    settings = get_settings()
    process_analysis(UUID(job_id), AnalysisRepository(), settings.video_data_dir, settings)


@celery_app.task(
    name="shortform.sns.upload",
    queue="sns",
    acks_late=False,
    autoretry_for=(),
    max_retries=0,
    soft_time_limit=600,
    time_limit=660,
)
def upload_youtube(upload_id: str) -> None:
    from uuid import UUID

    from app.adapters.sns_repository import SnsRepository
    from app.services.sns import process_upload

    process_upload(UUID(upload_id), SnsRepository(), get_settings())


@celery_app.task(
    name="shortform.sns.probe",
    queue="sns",
    acks_late=False,
    autoretry_for=(),
    max_retries=0,
)
def probe_youtube(upload_id: str, task_id: str) -> None:
    from uuid import UUID

    from app.adapters.sns_repository import SnsRepository
    from app.services.sns import probe_upload

    probe_upload(UUID(upload_id), UUID(task_id), SnsRepository(), get_settings())

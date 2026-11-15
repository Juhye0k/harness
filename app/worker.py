from celery import Celery

from app.config import get_settings

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
        "visibility_timeout": 900,
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

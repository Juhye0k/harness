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
    broker_transport_options={"visibility_timeout": 600},
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="shortform.diagnostics.ping", ignore_result=False)
def diagnostic_ping() -> dict[str, str]:
    """Infrastructure smoke test only; no video processing or business side effects."""
    return {"status": "ok"}

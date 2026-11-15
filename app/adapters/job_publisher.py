"""Send identifiers only. No product results or source URLs go into Redis."""


def publish_video_job(job_id, task_id):
    from app.worker import celery_app

    with celery_app.connection_for_write(connect_timeout=3) as connection:
        celery_app.send_task(
            "shortform.video.extract",
            args=[str(job_id)],
            task_id=str(task_id),
            queue="video",
            retry=False,
            connection=connection,
        )

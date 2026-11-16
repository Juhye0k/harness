"""Send identifiers only. No product results or source URLs go into Redis."""


def publish_analysis_job(job_id, task_id):
    from app.worker import celery_app

    with celery_app.connection_for_write(connect_timeout=3) as connection:
        celery_app.send_task(
            "shortform.analysis.recommend",
            args=[str(job_id)],
            task_id=str(task_id),
            queue="analysis",
            retry=False,
            connection=connection,
        )


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


def publish_sns_upload(upload_id, task_id):
    from app.worker import upload_youtube

    upload_youtube.apply_async(args=[str(upload_id)], task_id=str(task_id), queue="sns")


def publish_sns_probe(upload_id, task_id):
    from app.worker import probe_youtube

    probe_youtube.apply_async(
        args=[str(upload_id), str(task_id)], task_id=str(task_id), queue="sns"
    )

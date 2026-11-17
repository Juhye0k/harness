"""Bounded raw upload reception; media inspection happens only in the worker."""

import hashlib
import os
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.adapters.upload_repository import UploadRepository
from app.config import get_settings
from app.domain.jobs import JobError
from app.domain.video import MAX_BYTES
from app.services.uploads import upload_directory

router = APIRouter(tags=["local video uploads"])


def repository():
    return UploadRepository()


def publisher():
    from app.adapters.job_publisher import publish_upload

    return publish_upload


class UploadRequest(BaseModel):
    size_bytes: int = Field(gt=0, le=MAX_BYTES, strict=True)


Repo = Annotated[UploadRepository, Depends(repository)]
Publisher = Annotated[Callable, Depends(publisher)]


@router.post("/assets/uploads", status_code=201)
def initiate(body: UploadRequest, repo: Repo):
    asset_id = repo.create(body.size_bytes)
    return {
        "asset_id": str(asset_id),
        "upload_url": f"/assets/{asset_id}/content",
        "status_url": f"/assets/{asset_id}/upload",
    }


@router.get("/assets/{asset_id}/upload")
def status(asset_id: UUID, repo: Repo):
    row = repo.get(asset_id)
    return {
        "asset_id": str(asset_id),
        "status": row.state,
        "size_bytes": row.expected_bytes,
        "received_bytes": row.received_bytes,
        "error_code": row.error_code,
    }


@router.put("/assets/{asset_id}/content", status_code=202)
async def receive(
    asset_id: UUID,
    request: Request,
    repo: Repo,
    publish: Publisher,
):
    receipt = await run_in_threadpool(repo.get, asset_id)
    if request.headers.get("content-type", "").split(";")[0] not in {
        "application/octet-stream",
        "video/mp4",
        "video/webm",
        "video/quicktime",
    }:
        raise JobError("UPLOAD_TYPE", "MP4/WebM 영상 파일을 선택하세요.", 415)
    length = request.headers.get("content-length")
    if length is not None and (not length.isdecimal() or int(length) != receipt.expected_bytes):
        raise JobError("UPLOAD_SIZE", "전송 크기를 확인하세요.", 413)
    directory = upload_directory(get_settings().upload_data_dir, asset_id)
    await run_in_threadpool(repo.claim, asset_id, "created", "receiving")
    staging = directory / "receiving.part"
    completed = directory / "received.bin"
    received = False
    failure = "UPLOAD_INTERRUPTED"
    try:
        await run_in_threadpool(lambda: directory.mkdir(parents=True, exist_ok=False))
        digest = hashlib.sha256()
        size = 0
        with anyio.fail_after(600):
            with staging.open("xb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > receipt.expected_bytes or size > MAX_BYTES:
                        raise JobError(
                            "UPLOAD_SIZE", "파일은 최대 500MiB까지 업로드할 수 있습니다.", 413
                        )
                    digest.update(chunk)
                    await run_in_threadpool(output.write, chunk)
        if size != receipt.expected_bytes:
            raise JobError("UPLOAD_INCOMPLETE", "파일 전송이 끝나지 않았습니다.", 400)
        await run_in_threadpool(os.link, staging, completed)
        staging.unlink()
        await run_in_threadpool(repo.dispatch, asset_id, size, digest.hexdigest(), publish)
        received = True
        return {"asset_id": str(asset_id), "status_url": f"/assets/{asset_id}/upload"}
    except TimeoutError as exc:
        failure = "UPLOAD_TIMEOUT"
        raise JobError("UPLOAD_TIMEOUT", "전송 시간이 10분을 초과했습니다.", 408) from exc
    except OSError as exc:
        failure = "UPLOAD_IO_FAILED"
        raise JobError("UPLOAD_IO_FAILED", "파일을 저장하지 못했습니다.", 503) from exc
    except JobError as exc:
        failure = exc.code
        raise
    finally:
        if not received:
            with anyio.CancelScope(shield=True):
                staging.unlink(missing_ok=True)
                await run_in_threadpool(repo.finish, asset_id, error=failure)

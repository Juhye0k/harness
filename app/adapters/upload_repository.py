"""Short claims protect uploads from duplicate reception and worker redelivery."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.jobs import JobError
from app.models import Asset
from app.services.access import ownership_values
from app.upload_models import Upload


class UploadRepository:
    def __init__(self, engine=None):
        self.engine = engine or get_engine()

    def create(self, size):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            asset = Asset(source_url="", state="receiving", **ownership_values())
            s.add(asset)
            s.flush()
            asset.source_url = "upload:" + str(asset.id)
            s.add(Upload(asset_id=asset.id, expected_bytes=size))
            s.flush()
            return asset.id

    def get(self, asset_id):
        with Session(self.engine) as s:
            row = s.get(Upload, asset_id)
            if row is None:
                raise JobError("UPLOAD_NOT_FOUND", "업로드를 찾을 수 없습니다.", 404)
            s.expunge(row)
            return row

    def claim(self, asset_id, expected, target):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            row = s.scalar(select(Upload).where(Upload.asset_id == asset_id).with_for_update())
            if row is None or row.state != expected:
                raise JobError(
                    "UPLOAD_CONFLICT", "이미 접수했거나 처리 중입니다. 상태를 조회하세요.", 409
                )
            row.state = target
            s.flush()
            return row

    def dispatch(self, asset_id, size, sha, publish):
        with Session(self.engine) as s, s.begin():
            row = s.scalar(select(Upload).where(Upload.asset_id == asset_id).with_for_update())
            if row.state != "receiving":
                raise JobError("UPLOAD_CONFLICT", "업로드 상태가 변경됐습니다.", 409)
            row.received_bytes, row.sha256 = size, sha
            row.state = "queued"
            try:
                publish(asset_id, row.task_id)
            except Exception:
                row.state, row.error_code = "failed", "DISPATCH_FAILED"
                s.get(Asset, asset_id).state = "failed"

    def finish(self, asset_id, error=None, **values):
        with Session(self.engine) as s, s.begin():
            row = s.scalar(select(Upload).where(Upload.asset_id == asset_id).with_for_update())
            if not row or row.state not in {"receiving", "validating"}:
                return False
            row.state, row.error_code = ("failed" if error else "ready"), error
            asset = s.get(Asset, asset_id)
            asset.state = row.state
            for key, value in values.items():
                setattr(asset, key, value)
            return True

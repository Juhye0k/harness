"""Persisted business state; importing models does not open a connection."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow():
    return datetime.now(UTC)


class VideoJob(Base):
    __tablename__ = "video_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','queued','running','succeeded','failed')", name="job_status"
        ),
        CheckConstraint(
            "start_seconds >= 0 AND start_seconds < 'Infinity'::float8", name="job_start"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False, default=uuid4)
    source_url: Mapped[str] = mapped_column(Text)
    start_seconds: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float, default=10.0)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    operator_reason: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(String(64))
    output_path: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"))
    candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("highlight_candidates.id"), unique=True
    )


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_url: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    state: Mapped[str] = mapped_column(String(16), default="pending")


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("asset_id", "version", name="transcript_asset_version"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"))
    version: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(16), default="running")
    segments: Mapped[list | None] = mapped_column(JSONB)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','queued','running','succeeded','failed')", name="analysis_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(Uuid, unique=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"))
    genre: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    config: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str | None] = mapped_column(String(64))
    rejected: Mapped[list | None] = mapped_column(JSONB)
    operator_reason: Mapped[str | None] = mapped_column(Text)


class HighlightCandidate(Base):
    __tablename__ = "highlight_candidates"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_jobs.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSONB)


class TranscriptReview(Base):
    __tablename__ = "transcript_reviews"
    __table_args__ = (
        UniqueConstraint("analysis_id", "asr_version", "policy_version", "segment_id"),
        CheckConstraint("decision IN ('error','ok','uncertain')", name="review_decision"),
        CheckConstraint("revision > 0", name="review_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_jobs.id"))
    asr_version: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[str] = mapped_column(String(80))
    segment_id: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(1000), default="")
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (UniqueConstraint("analysis_id", "stage", name="provider_call_once"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_jobs.id"))
    stage: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default="started")
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class SnsOAuthState(Base):
    __tablename__ = "sns_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(Text)  # Encrypted, never returned.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SnsAccount(Base):
    __tablename__ = "sns_accounts"
    __table_args__ = (UniqueConstraint("owner", "channel_id", name="sns_owner_channel"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    channel_id: Mapped[str] = mapped_column(String(128))
    channel_title: Mapped[str] = mapped_column(String(256))
    credentials: Mapped[str] = mapped_column(Text)  # Fernet ciphertext only.
    version: Mapped[int] = mapped_column(Integer, default=1)
    connected: Mapped[bool] = mapped_column(Boolean, default=True)


class SnsUpload(Base):
    __tablename__ = "sns_uploads"
    __table_args__ = (
        UniqueConstraint("owner", "request_id", name="sns_request_once"),
        CheckConstraint(
            "status IN ('draft','queued','running','succeeded','failed','unknown')",
            name="sns_upload_status",
        ),
        CheckConstraint("privacy IN ('private','unlisted','public')", name="sns_privacy"),
        Index(
            "sns_confirmed_output_once",
            "account_id",
            "job_id",
            "output_version",
            unique=True,
            postgresql_where=text("status <> 'draft'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(Uuid, unique=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(Uuid)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("sns_accounts.id"))
    account_version: Mapped[int] = mapped_column(Integer)
    channel_id: Mapped[str] = mapped_column(String(128))
    channel_title: Mapped[str] = mapped_column(String(256))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("video_jobs.id"))
    output_version: Mapped[str] = mapped_column(String(64))
    output_size: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(100))
    privacy: Mapped[str] = mapped_column(String(16), default="private")
    made_for_kids: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    session_uri: Mapped[str | None] = mapped_column(Text)  # Encrypted upload capability.
    remote_id: Mapped[str | None] = mapped_column(String(64))
    probe_task_id: Mapped[UUID | None] = mapped_column(Uuid)

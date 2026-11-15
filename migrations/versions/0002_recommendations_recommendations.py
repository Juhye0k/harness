"""recommendations

Revision ID: 0002_recommendations
Revises: 0001_video_jobs
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_recommendations"
down_revision = "0001_video_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("has_audio", sa.Boolean(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("genre", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("rejected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("operator_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','queued','running','succeeded','failed')", name="analysis_status"
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index(op.f("ix_analysis_jobs_status"), "analysis_jobs", ["status"], unique=False)
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "version", name="transcript_asset_version"),
    )
    op.create_table(
        "highlight_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_jobs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_highlight_candidates_analysis_id"),
        "highlight_candidates",
        ["analysis_id"],
        unique=False,
    )
    op.create_table(
        "provider_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_jobs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "stage", name="provider_call_once"),
    )
    op.add_column("video_jobs", sa.Column("asset_id", sa.Uuid(), nullable=True))
    op.add_column("video_jobs", sa.Column("candidate_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("video_jobs_candidate_unique", "video_jobs", ["candidate_id"])
    op.create_foreign_key("video_jobs_asset_fk", "video_jobs", "assets", ["asset_id"], ["id"])
    op.create_foreign_key(
        "video_jobs_candidate_fk", "video_jobs", "highlight_candidates", ["candidate_id"], ["id"]
    )


def downgrade():
    op.drop_constraint("video_jobs_candidate_fk", "video_jobs", type_="foreignkey")
    op.drop_constraint("video_jobs_asset_fk", "video_jobs", type_="foreignkey")
    op.drop_constraint("video_jobs_candidate_unique", "video_jobs", type_="unique")
    op.drop_column("video_jobs", "candidate_id")
    op.drop_column("video_jobs", "asset_id")
    op.drop_table("provider_calls")
    op.drop_index(op.f("ix_highlight_candidates_analysis_id"), table_name="highlight_candidates")
    op.drop_table("highlight_candidates")
    op.drop_table("transcripts")
    op.drop_index(op.f("ix_analysis_jobs_status"), table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_table("assets")

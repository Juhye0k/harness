"""Add the first asynchronous video job model."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_video_jobs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "video_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *[
            sa.Column(
                name, sa.DateTime(timezone=True), nullable=name in ("started_at", "finished_at")
            )
            for name in ("created_at", "updated_at", "started_at", "finished_at")
        ],
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("operator_reason", sa.Text()),
        sa.Column("run_id", sa.String(64)),
        sa.Column("output_path", sa.Text()),
        sa.Column("result", postgresql.JSONB()),
        sa.CheckConstraint(
            "status IN ('pending','queued','running','succeeded','failed')", name="job_status"
        ),
        sa.CheckConstraint(
            "start_seconds >= 0 AND start_seconds < 'Infinity'::float8", name="job_start"
        ),
    )
    op.create_index("ix_video_jobs_status", "video_jobs", ["status"])


def downgrade():
    op.drop_table("video_jobs")

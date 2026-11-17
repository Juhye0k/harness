"""Immutable caption snapshots and one render job per snapshot."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_caption_revisions"
down_revision = "0005_auth_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "caption_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("highlight_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_version", sa.String(80), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("cues", JSONB(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("render_job_id", sa.Uuid(), sa.ForeignKey("video_jobs.id"), unique=True),
        sa.UniqueConstraint("candidate_id", "content_hash"),
    )
    op.create_index("ix_caption_revisions_candidate_id", "caption_revisions", ["candidate_id"])


def downgrade():
    op.drop_table("caption_revisions")

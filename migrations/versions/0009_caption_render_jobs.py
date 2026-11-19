"""Pin versioned caption render settings to independent video jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_caption_render_jobs"
down_revision = "0008_analysis_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "caption_render_jobs",
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("video_jobs.id"), primary_key=True),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("caption_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("source_caption_spans", JSONB(), nullable=False),
        sa.UniqueConstraint("revision_id", "input_hash", name="caption_render_once"),
    )


def downgrade():
    # Refuse to orphan v2 outputs: a worker on the older code would treat queued ones
    # as ordinary source extractions and download endpoints would lose their subtitles.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM caption_render_jobs) THEN "
        "RAISE EXCEPTION 'Versioned caption render jobs exist'; END IF; END $$"
    )
    op.drop_table("caption_render_jobs")

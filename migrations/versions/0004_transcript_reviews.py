"""Version-bound human transcript review decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0004_transcript_reviews"
down_revision = "0003_sns_uploads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transcript_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id"), nullable=False),
        sa.Column("asr_version", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("segment_id", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("analysis_id", "asr_version", "policy_version", "segment_id"),
        sa.CheckConstraint("decision IN ('error','ok','uncertain')", name="review_decision"),
        sa.CheckConstraint("revision > 0", name="review_revision"),
    )


def downgrade():
    op.drop_table("transcript_reviews")

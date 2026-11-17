"""Streamed uploads and asynchronous media validation."""

import sqlalchemy as sa
from alembic import op

revision = "0007_asset_uploads"
down_revision = "0006_caption_revisions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asset_uploads",
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), primary_key=True),
        sa.Column("task_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("expected_bytes", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expected_bytes > 0 AND expected_bytes <= 524288000"),
        sa.CheckConstraint("received_bytes >= 0 AND received_bytes <= expected_bytes"),
        sa.CheckConstraint(
            "state IN ('created','receiving','queued','validating','ready','failed')"
        ),
    )


def downgrade():
    op.drop_table("asset_uploads")

"""Owner-scoped, expiring analysis request receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0008_analysis_requests"
down_revision = "0007_asset_uploads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analysis_request_receipts",
        sa.Column("owner_key", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_analysis_request_receipts_analysis_id", "analysis_request_receipts", ["analysis_id"]
    )


def downgrade():
    op.drop_table("analysis_request_receipts")

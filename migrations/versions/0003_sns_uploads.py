"""YouTube OAuth ownership and explicitly approved one-shot uploads.

Revision ID: 0003_sns_uploads
Revises: 0002_recommendations
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_sns_uploads"
down_revision = "0002_recommendations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sns_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sns_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.String(128), nullable=False),
        sa.Column("channel_title", sa.String(256), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("owner", "channel_id", name="sns_owner_channel"),
    )
    op.create_index("ix_sns_accounts_owner", "sns_accounts", ["owner"])
    op.create_table(
        "sns_uploads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("sns_accounts.id"), nullable=False),
        sa.Column("account_version", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.String(128), nullable=False),
        sa.Column("channel_title", sa.String(256), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("video_jobs.id"), nullable=False),
        sa.Column("output_version", sa.String(64), nullable=False),
        sa.Column("output_size", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("privacy", sa.String(16), nullable=False),
        sa.Column("made_for_kids", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("session_uri", sa.Text()),
        sa.Column("remote_id", sa.String(64)),
        sa.Column("probe_task_id", sa.Uuid()),
        sa.UniqueConstraint("owner", "request_id", name="sns_request_once"),
        sa.CheckConstraint(
            "status IN ('draft','queued','running','succeeded','failed','unknown')",
            name="sns_upload_status",
        ),
        sa.CheckConstraint("privacy IN ('private','unlisted','public')", name="sns_privacy"),
    )
    op.create_index("ix_sns_uploads_owner", "sns_uploads", ["owner"])
    op.create_index("ix_sns_uploads_status", "sns_uploads", ["status"])
    op.create_index(
        "sns_confirmed_output_once",
        "sns_uploads",
        ["account_id", "job_id", "output_version"],
        unique=True,
        postgresql_where=sa.text("status <> 'draft'"),
    )


def downgrade():
    op.drop_table("sns_uploads")
    op.drop_table("sns_accounts")
    op.drop_table("sns_oauth_states")

"""Users, revocable sessions, legacy quarantine and data lifecycle."""

import sqlalchemy as sa
from alembic import op

from app import auth_models  # noqa: F401
from app.db import Base

revision = "0005_auth_data"
down_revision = "0004_transcript_reviews"
branch_labels = None
depends_on = None
TABLES = [
    "users",
    "auth_identities",
    "auth_sessions",
    "auth_login_states",
    "resource_uses",
    "deletion_requests",
]


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind())
    for name in ("assets", "video_jobs"):
        op.add_column(name, sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")))
        op.add_column(
            name, sa.Column("legacy", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        op.add_column(name, sa.Column("expires_at", sa.DateTime(timezone=True)))
        op.add_column(name, sa.Column("deleted_at", sa.DateTime(timezone=True)))
        op.create_index(name + "_user", name, ["user_id"])
        op.create_check_constraint(
            name + "_ownership",
            name,
            "(legacy AND user_id IS NULL AND expires_at IS NULL) OR "
            "(NOT legacy AND user_id IS NOT NULL AND expires_at IS NOT NULL)",
        )
    op.add_column(
        "assets",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    # Explicit operator migration required: dropping ownership silently is unsafe.
    raise RuntimeError("Restore the pre-transition backup offline; ownership downgrade is disabled")

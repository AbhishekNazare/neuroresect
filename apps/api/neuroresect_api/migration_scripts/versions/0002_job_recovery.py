"""Persist delivery reservations and worker liveness."""

import sqlalchemy as sa
from alembic import op

revision = "0002_job_recovery"
down_revision = "0001_research_records"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs", sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")

"""Baseline research records, frozen independently of evolving ORM models."""

from alembic import op
from neuroresect_api.baseline_schema import Base

revision = "0001_research_records"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")

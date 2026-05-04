"""add current_step to agent_runs

Revision ID: 008
Revises: 007
Create Date: 2026-05-03

"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("current_step", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "current_step")

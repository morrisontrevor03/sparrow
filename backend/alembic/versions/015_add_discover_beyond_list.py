"""add discover_beyond_list to campaigns

Revision ID: 015
Revises: 014
Create Date: 2026-08-31

"""
import sqlalchemy as sa

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("discover_beyond_list", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "discover_beyond_list")

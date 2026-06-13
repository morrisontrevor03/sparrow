"""add onboarding fields to user_preferences

Revision ID: 001
Revises:
Create Date: 2026-04-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("salary_type", sa.String(10), nullable=True),
    )
    op.add_column(
        "user_preferences",
        sa.Column("location_flexible", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "user_preferences",
        sa.Column("work_environment", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "work_environment")
    op.drop_column("user_preferences", "location_flexible")
    op.drop_column("user_preferences", "salary_type")

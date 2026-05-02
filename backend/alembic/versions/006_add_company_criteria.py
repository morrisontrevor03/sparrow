"""add company_stages and company_industries to user_preferences

Revision ID: 006
Revises: 005
Create Date: 2026-05-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("company_stages", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "user_preferences",
        sa.Column("company_industries", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "company_industries")
    op.drop_column("user_preferences", "company_stages")

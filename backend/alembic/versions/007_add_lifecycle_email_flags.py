"""add lifecycle email tracking flags to users

Revision ID: 007
Revises: 006
Create Date: 2026-05-03

"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("finish_setup_email_sent", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("first_outreach_email_sent", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "first_outreach_email_sent")
    op.drop_column("users", "finish_setup_email_sent")

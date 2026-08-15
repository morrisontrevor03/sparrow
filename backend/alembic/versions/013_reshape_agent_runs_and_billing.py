"""reshape agent_runs counters and replace subscriptions with billing_accounts

Under credits there is no plan and no subscription status — entitlement is the
ledger balance. The Stripe customer mapping is all that's worth keeping.

Revision ID: 013
Revises: 012
Create Date: 2026-08-12

"""
import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("drafts_written", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_runs",
        sa.Column("credits_spent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_column("agent_runs", "jobs_found")
    op.drop_column("agent_runs", "applications_created")

    # Rename in place so the stripe_customer_id mapping survives.
    op.rename_table("subscriptions", "billing_accounts")
    op.drop_column("billing_accounts", "plan")
    op.drop_column("billing_accounts", "status")
    op.drop_column("billing_accounts", "stripe_subscription_id")


def downgrade() -> None:
    op.add_column("billing_accounts", sa.Column("stripe_subscription_id", sa.String(255)))
    op.add_column(
        "billing_accounts",
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
    )
    op.add_column(
        "billing_accounts", sa.Column("plan", sa.String(20), nullable=False, server_default="free")
    )
    op.rename_table("billing_accounts", "subscriptions")

    op.add_column(
        "agent_runs",
        sa.Column("applications_created", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_runs", sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0")
    )
    op.drop_column("agent_runs", "credits_spent")
    op.drop_column("agent_runs", "drafts_written")

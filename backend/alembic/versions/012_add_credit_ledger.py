"""add prepaid credit ledger, drop monthly_usage

Grandfathers every existing user with a starting balance so nobody's first login
after the pricing change is a paywall.

Revision ID: 012
Revises: 011
Create Date: 2026-08-12

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

GRANDFATHER_CREDITS = 200


def upgrade() -> None:
    op.create_table(
        "credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Unique so a redelivered Stripe webhook cannot double-credit.
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True, unique=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])
    op.create_index("ix_credit_ledger_user_created", "credit_ledger", ["user_id", "created_at"])
    op.create_index(
        "ix_credit_ledger_campaign_created", "credit_ledger", ["campaign_id", "created_at"]
    )

    op.create_table(
        "credit_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pack_id", sa.String(50), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=False, unique=True),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"])
    op.create_index(
        "ix_credit_purchases_session", "credit_purchases", ["stripe_checkout_session_id"]
    )
    op.create_index(
        "ix_credit_purchases_payment_intent", "credit_purchases", ["stripe_payment_intent_id"]
    )

    op.execute(
        f"""
        INSERT INTO credit_ledger (id, user_id, delta, reason, created_at)
        SELECT gen_random_uuid(), id, {GRANDFATHER_CREDITS}, 'promo_grant', now()
        FROM users
        """
    )

    op.drop_table("monthly_usage")


def downgrade() -> None:
    op.create_table(
        "monthly_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("jobs_surfaced", sa.Integer(), server_default="0"),
        sa.Column("contacts_surfaced", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_monthly_usage_user_id", "monthly_usage", ["user_id"])

    op.drop_table("credit_purchases")
    op.drop_table("credit_ledger")

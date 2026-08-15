"""add campaigns and backfill one per existing user

Every user who completed onboarding gets a job_search campaign carrying their old
targeting preferences, and their existing contacts are attached to it — so the
pivot does not orphan anyone's data.

Autopilot is deliberately left OFF for backfilled campaigns. Under the old plan,
scheduled runs were free; under credits they spend money. Turning it on silently
would drain a migrated user's balance without them ever agreeing to it.

Revision ID: 010
Revises: 009
Create Date: 2026-08-12

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("campaign_type", sa.String(50), nullable=False, server_default="business_development"),
        sa.Column("objective", sa.Text()),
        sa.Column("target_titles", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("target_companies", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("target_industries", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("target_locations", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("excluded_companies", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("company_stages", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("autopilot_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("autopilot_cadence_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("weekly_credit_cap", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"])

    op.add_column(
        "contacts",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_contacts_campaign_id",
        "contacts",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_contacts_campaign_id", "contacts", ["campaign_id"])

    op.add_column(
        "agent_runs",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_campaign_id",
        "agent_runs",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agent_runs_campaign_id", "agent_runs", ["campaign_id"])

    # Backfill: one campaign per user who has preferences, carrying their targeting.
    op.execute(
        """
        INSERT INTO campaigns (
            id, user_id, name, campaign_type, objective,
            target_titles, target_companies, target_locations,
            excluded_companies, company_stages, target_industries,
            status, autopilot_enabled, autopilot_cadence_days, weekly_credit_cap,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            p.user_id,
            'My job search',
            'job_search',
            CASE
                WHEN p.target_roles IS NOT NULL AND array_length(p.target_roles, 1) > 0
                    THEN 'Find people who can help me land a role in '
                         || array_to_string(p.target_roles, ', ')
                ELSE 'Find people who can help with my job search'
            END,
            COALESCE(p.target_roles, '{}'),
            COALESCE(p.target_companies, '{}'),
            COALESCE(p.target_locations, '{}'),
            COALESCE(p.excluded_companies, '{}'),
            COALESCE(p.company_stages, '{}'),
            COALESCE(p.company_industries, '{}'),
            CASE
                WHEN p.target_roles IS NOT NULL AND array_length(p.target_roles, 1) > 0
                    THEN 'active'
                ELSE 'draft'
            END,
            false,
            3,
            100,
            now(),
            now()
        FROM user_preferences p
        """
    )

    # Attach existing contacts and runs to their user's (single) new campaign.
    op.execute(
        """
        UPDATE contacts c
        SET campaign_id = camp.id
        FROM campaigns camp
        WHERE camp.user_id = c.user_id AND c.campaign_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE agent_runs r
        SET campaign_id = camp.id
        FROM campaigns camp
        WHERE camp.user_id = r.user_id
          AND r.campaign_id IS NULL
          AND r.agent_type = 'networking'
        """
    )

    # The old three-agent taxonomy collapses to one agent type. Networking runs
    # become outreach runs; job-scout and application runs describe features that
    # no longer exist, so they'd only surface as unexplainable rows in the
    # activity feed.
    op.execute("UPDATE agent_runs SET agent_type = 'outreach' WHERE agent_type = 'networking'")
    op.execute("DELETE FROM agent_runs WHERE agent_type IN ('job_scout', 'application')")


def downgrade() -> None:
    op.execute("UPDATE agent_runs SET agent_type = 'networking' WHERE agent_type = 'outreach'")

    op.drop_index("ix_agent_runs_campaign_id", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_campaign_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "campaign_id")

    op.drop_index("ix_contacts_campaign_id", table_name="contacts")
    op.drop_constraint("fk_contacts_campaign_id", "contacts", type_="foreignkey")
    op.drop_column("contacts", "campaign_id")

    op.drop_index("ix_campaigns_user_id", table_name="campaigns")
    op.drop_table("campaigns")

"""reshape user_preferences into account-level settings

Targeting moved to campaigns in 010; what's left here is the person, not the search.

Revision ID: 011
Revises: 010
Create Date: 2026-08-12

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

# Columns that moved onto campaigns (or died with the job-search features).
DROPPED = [
    "target_roles",
    "target_companies",
    "target_locations",
    "excluded_companies",
    "min_salary",
    "max_salary",
    "employment_types",
    "experience_level",
    "salary_type",
    "location_flexible",
    "work_environment",
    "open_to_similar_companies",
    "company_stages",
    "company_industries",
    "scout_enabled",
    "networking_enabled",
    "application_agent_enabled",
]


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("headline", sa.String(255), nullable=True))
    op.add_column("user_preferences", sa.Column("value_prop", sa.Text(), nullable=True))
    op.add_column("user_preferences", sa.Column("timezone", sa.String(64), nullable=True))
    op.add_column(
        "user_preferences",
        sa.Column("email_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "email_low_balance_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )

    # Seed a headline from the old experience level + roles so migrated users have
    # something in their outreach context instead of a blank profile.
    op.execute(
        """
        UPDATE user_preferences
        SET headline = trim(
            COALESCE(initcap(experience_level) || '-level ', '')
            || COALESCE(array_to_string(target_roles, ' / '), 'professional')
        )
        WHERE headline IS NULL
          AND (experience_level IS NOT NULL OR array_length(target_roles, 1) > 0)
        """
    )

    for column in DROPPED:
        op.drop_column("user_preferences", column)


def downgrade() -> None:
    op.add_column("user_preferences", sa.Column("target_roles", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("target_companies", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("target_locations", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("excluded_companies", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("min_salary", sa.Integer()))
    op.add_column("user_preferences", sa.Column("max_salary", sa.Integer()))
    op.add_column("user_preferences", sa.Column("employment_types", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("experience_level", sa.String(50)))
    op.add_column("user_preferences", sa.Column("salary_type", sa.String(10)))
    op.add_column("user_preferences", sa.Column("location_flexible", sa.Boolean(), server_default=sa.true()))
    op.add_column("user_preferences", sa.Column("work_environment", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("open_to_similar_companies", sa.Boolean(), server_default=sa.false()))
    op.add_column("user_preferences", sa.Column("company_stages", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("company_industries", postgresql.ARRAY(sa.Text()), server_default="{}"))
    op.add_column("user_preferences", sa.Column("scout_enabled", sa.Boolean(), server_default=sa.true()))
    op.add_column("user_preferences", sa.Column("networking_enabled", sa.Boolean(), server_default=sa.true()))
    op.add_column("user_preferences", sa.Column("application_agent_enabled", sa.Boolean(), server_default=sa.true()))

    # Restore targeting from the backfilled campaign where one exists.
    op.execute(
        """
        UPDATE user_preferences p
        SET target_roles = c.target_titles,
            target_companies = c.target_companies,
            target_locations = c.target_locations,
            excluded_companies = c.excluded_companies,
            company_stages = c.company_stages,
            company_industries = c.target_industries
        FROM campaigns c
        WHERE c.user_id = p.user_id
        """
    )

    op.drop_column("user_preferences", "email_low_balance_enabled")
    op.drop_column("user_preferences", "email_digest_enabled")
    op.drop_column("user_preferences", "timezone")
    op.drop_column("user_preferences", "value_prop")
    op.drop_column("user_preferences", "headline")

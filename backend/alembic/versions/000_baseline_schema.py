"""baseline schema

The chain previously started at 001, which does `add_column` against tables
nothing had created — `alembic upgrade head` on an empty database failed on the
first revision, and CI's migration-check job could never have been green. Tables
were only ever created by `Base.metadata.create_all` in the app's lifespan.

This revision supplies the missing starting point: the schema as it stood
*before* 001, so 001-008 apply their deltas on top exactly as they were written.

Safe for existing databases: one already stamped at 008 stays at 008 and
upgrades forward normally. Alembic only walks down_revision links, so inserting
a parent below 001 changes nothing for a database that is already past it.

Revision ID: 000
Revises:
Create Date: 2026-08-12

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column("target_roles", ARRAY(sa.Text()), server_default="{}"),
        sa.Column("target_companies", ARRAY(sa.Text()), server_default="{}"),
        sa.Column("target_locations", ARRAY(sa.Text()), server_default="{}"),
        sa.Column("excluded_companies", ARRAY(sa.Text()), server_default="{}"),
        sa.Column("min_salary", sa.Integer()),
        sa.Column("max_salary", sa.Integer()),
        sa.Column("employment_types", ARRAY(sa.Text()), server_default="{}"),
        sa.Column("experience_level", sa.String(50)),
        sa.Column("scout_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("networking_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("application_agent_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("structured_data", JSONB()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("parsed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])

    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("external_id", sa.String(255)),
        sa.Column("source", sa.String(50)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("url", sa.String(1000)),
        sa.Column("salary_min", sa.Integer()),
        sa.Column("salary_max", sa.Integer()),
        sa.Column("employment_type", sa.String(50)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("match_score", sa.Float()),
        sa.Column("match_reasoning", sa.Text()),
        sa.Column("is_new", sa.Boolean(), server_default=sa.true()),
        sa.Column("is_dismissed", sa.Boolean(), server_default=sa.false()),
        sa.Column("email_sent", sa.Boolean(), server_default=sa.false()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])

    op.create_table(
        "applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column(
            "resume_id",
            UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("tailored_resume", JSONB()),
        sa.Column("cover_letter", sa.Text()),
        sa.Column("tailoring_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])

    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name", sa.String(255)),
        sa.Column("title", sa.String(255)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("seniority", sa.String(50)),
        sa.Column("department", sa.String(100)),
        sa.Column("relevance_score", sa.Float()),
        sa.Column("relevance_reasoning", sa.Text()),
        sa.Column("outreach_status", sa.String(50), server_default="discovered"),
        sa.Column("outreach_message", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_contacts_user_id", "contacts", ["user_id"])
    op.create_index("ix_contacts_company", "contacts", ["company"])

    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("trigger", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("input_data", JSONB()),
        sa.Column("tool_calls", JSONB()),
        sa.Column("output_summary", sa.Text()),
        sa.Column("jobs_found", sa.Integer(), server_default="0"),
        sa.Column("contacts_found", sa.Integer(), server_default="0"),
        sa.Column("applications_created", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column("stripe_customer_id", sa.String(255)),
        sa.Column("stripe_subscription_id", sa.String(255)),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_stripe_customer_id", "subscriptions", ["stripe_customer_id"])

    op.create_table(
        "monthly_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("jobs_surfaced", sa.Integer(), server_default="0"),
        sa.Column("contacts_surfaced", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_monthly_usage_user_id", "monthly_usage", ["user_id"])


def downgrade() -> None:
    op.drop_table("monthly_usage")
    op.drop_table("subscriptions")
    op.drop_table("agent_runs")
    op.drop_table("contacts")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("resumes")
    op.drop_table("user_preferences")
    op.drop_table("users")

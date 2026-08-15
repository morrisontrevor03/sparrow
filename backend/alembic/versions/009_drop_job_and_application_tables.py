"""drop job scout and application agent tables

Sparrow pivot: job discovery and resume tailoring are removed. Contacts and users
are preserved; jobs and applications are not.

Revision ID: 009
Revises: 008
Create Date: 2026-08-12

"""
import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # applications references jobs and resumes, so it goes first.
    op.drop_table("applications")
    op.drop_table("jobs")


def downgrade() -> None:
    from sqlalchemy.dialects import postgresql

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
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
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column(
            "resume_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("tailored_resume", postgresql.JSONB()),
        sa.Column("cover_letter", sa.Text()),
        sa.Column("tailoring_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

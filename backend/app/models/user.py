import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    verification_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finish_setup_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    first_outreach_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    preferences: Mapped["UserPreferences | None"] = relationship("UserPreferences", back_populates="user", uselist=False)
    resumes: Mapped[list["Resume"]] = relationship("Resume", back_populates="user")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="user")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="user")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="user")
    agent_runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="user")
    subscription: Mapped["Subscription | None"] = relationship("Subscription", back_populates="user", uselist=False)
    monthly_usage: Mapped[list["MonthlyUsage"]] = relationship("MonthlyUsage", back_populates="user")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    target_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    target_companies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    target_locations: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    excluded_companies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    max_salary: Mapped[int | None] = mapped_column(Integer)
    employment_types: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    experience_level: Mapped[str | None] = mapped_column(String(50))

    salary_type: Mapped[str | None] = mapped_column(String(10))  # "hourly" or "salary"
    location_flexible: Mapped[bool] = mapped_column(Boolean, default=True)
    work_environment: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    open_to_similar_companies: Mapped[bool] = mapped_column(Boolean, default=False)
    company_stages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    company_industries: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    scout_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    networking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    application_agent_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="preferences")

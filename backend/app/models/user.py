import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
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
    campaigns: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="user")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="user")
    agent_runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="user")
    billing_account: Mapped["BillingAccount | None"] = relationship("BillingAccount", back_populates="user", uselist=False)
    credit_entries: Mapped[list["CreditLedgerEntry"]] = relationship("CreditLedgerEntry", back_populates="user")


class UserPreferences(Base):
    """
    Account-level settings — the person, not the campaign.

    Everything targeting-related (titles, companies, locations, stages) lives on
    Campaign, because a user running business development and a job search at the
    same time needs two different target sets.
    """

    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # Short self-description used to personalize outreach. Complements the parsed
    # resume: the resume says what you've done, these say how you want to be framed.
    headline: Mapped[str | None] = mapped_column(String(255))
    value_prop: Mapped[str | None] = mapped_column(Text)

    timezone: Mapped[str | None] = mapped_column(String(64))
    email_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_low_balance_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="preferences")

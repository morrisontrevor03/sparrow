import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Campaign types drive who the agent looks for and how it writes to them.
# See app/services/targeting.py for the per-type ranking + prompt profiles.
CAMPAIGN_TYPES = (
    "business_development",
    "job_search",
    "fundraising",
    "recruiting",
    "custom",
)

CAMPAIGN_STATUSES = ("draft", "active", "paused")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(50), nullable=False, default="business_development")
    # Free text, fed straight into the ranking and drafting prompts. This is the
    # single highest-signal field on the model — "sell our observability tool to
    # platform teams at Series B fintechs" beats any amount of structured filters.
    objective: Mapped[str | None] = mapped_column(Text)

    target_titles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    target_companies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    target_industries: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    target_locations: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    excluded_companies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    company_stages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    autopilot_cadence_days: Mapped[int] = mapped_column(Integer, default=3)
    # Hard ceiling on credits scheduled runs may spend for this campaign in a
    # rolling 7-day window. Manual and MCP-invoked runs are not capped — the user
    # is present and initiated the spend themselves.
    weekly_credit_cap: Mapped[int] = mapped_column(Integer, default=100)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship("User", back_populates="campaigns")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="campaign")

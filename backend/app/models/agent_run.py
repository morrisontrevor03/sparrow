import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "outreach"
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)  # "scheduled" | "manual" | "mcp"
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")  # running | completed | failed
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    tool_calls: Mapped[list | None] = mapped_column(JSONB)
    output_summary: Mapped[str | None] = mapped_column(Text)
    contacts_found: Mapped[int] = mapped_column(Integer, default=0)
    drafts_written: Mapped[int] = mapped_column(Integer, default=0)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User"] = relationship("User", back_populates="agent_runs")

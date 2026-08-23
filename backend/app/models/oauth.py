import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Scopes an MCP client can request. Deliberately coarse — a client either reads
# your contacts or it doesn't; per-campaign scoping would be unusable in a consent
# screen and is enforced by ownership checks anyway.
SCOPES = {
    "profile:read": "Read your name, headline, and background",
    "campaigns:read": "See your campaigns and their settings",
    "campaigns:run": "Create campaigns and run them (spends credits)",
    "contacts:read": "Read the contacts Sparrow has found for you",
    "contacts:write": "Draft messages and update contact status (spends credits)",
}

DEFAULT_SCOPES = "profile:read campaigns:read contacts:read"


class OAuthClient(Base):
    """
    An MCP client registered via RFC 7591 dynamic client registration.

    Clients are public (no secret) by default — MCP desktop clients cannot keep
    one — which is exactly why PKCE is mandatory on the authorization code flow.
    """

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    grant_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["authorization_code", "refresh_token"]
    )
    token_endpoint_auth_method: Mapped[str] = mapped_column(String(50), default="none")
    scope: Mapped[str] = mapped_column(Text, default=DEFAULT_SCOPES)
    client_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthAuthorizationCode(Base):
    """
    A single-use authorization code. Stored hashed: a leaked database row must not
    be redeemable, and the code is only ever compared, never displayed.
    """

    __tablename__ = "oauth_authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)

    # PKCE (RFC 7636). S256 only — `plain` is not accepted.
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(10), nullable=False, default="S256")

    # RFC 8707 resource indicator. Binding the code (and the token minted from it)
    # to this server's URL is what stops a token issued for Sparrow from being
    # replayed against a different MCP server the same client is connected to.
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthToken(Base):
    """An issued access token, with its rotating refresh token."""

    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    access_token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    refresh_token_hash: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    client_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped["OAuthClient"] = relationship("OAuthClient", lazy="joined")

    @property
    def is_active(self) -> bool:
        from datetime import timezone

        if self.revoked_at is not None:
            return False
        return self.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

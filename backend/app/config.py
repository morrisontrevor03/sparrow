from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/sparrow"

    # Auth
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Anthropic
    anthropic_api_key: str = ""

    # OpenAI (fallback when Anthropic is unavailable)
    openai_api_key: str = ""
    openai_fallback_model: str = "gpt-4o-mini"

    # Exa.ai (neural people search — the core discovery dependency)
    exa_api_key: str = ""

    # Email
    resend_api_key: str = ""
    resend_from_email: str = "noreply@sparrow.email"

    # Stripe — one-time credit pack purchases (no subscriptions)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_growth: str = ""
    stripe_price_scale: str = ""

    # Storage
    upload_dir: str = "./uploads"

    # Google OAuth (end-user sign-in)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Analytics
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"

    # App
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    environment: str = "development"

    # Credit pricing. Costs are per unit of work; packs are one-time purchases.
    signup_credit_grant: int = 25
    credits_per_contact: int = 1
    credits_per_draft: int = 2
    credits_per_mcp_call: int = 1
    low_balance_threshold: int = 50

    # MCP / OAuth 2.1 authorization server
    oauth_access_token_ttl_seconds: int = 3600
    oauth_refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    oauth_authorization_code_ttl_seconds: int = 60


settings = Settings()


# Credit packs. `price_id_attr` names the Settings field holding the Stripe price
# ID so packs stay declarative and a missing env var fails loudly at checkout
# rather than silently selling the wrong thing.
CREDIT_PACKS: dict[str, dict] = {
    "starter": {
        "name": "Starter",
        "credits": 500,
        "amount_cents": 2000,
        "price_id_attr": "stripe_price_starter",
    },
    "growth": {
        "name": "Growth",
        "credits": 2500,
        "amount_cents": 7500,
        "price_id_attr": "stripe_price_growth",
    },
    "scale": {
        "name": "Scale",
        "credits": 10000,
        "amount_cents": 25000,
        "price_id_attr": "stripe_price_scale",
    },
}


def pack_price_id(pack_id: str) -> str:
    pack = CREDIT_PACKS[pack_id]
    return getattr(settings, pack["price_id_attr"], "")

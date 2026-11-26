from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_ttl_hours: int = 24

    # "fake" = simulated payments (clearly labelled in the UI); "stripe" = Stripe test mode
    payment_provider: str = "fake"
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # "fake" = log only; "resend" = Resend API (use delivered@resend.dev style test recipients)
    email_provider: str = "fake"
    resend_api_key: str = ""
    email_from: str = "Corgi Demo <onboarding@resend.dev>"
    # Resend's sandbox sender only delivers to the account owner. When set, every email is
    # delivered here instead, labelled with the real recipient (the log keeps the real one).
    email_redirect_to: str = ""

    # where the "Open your portal" button in emails points
    app_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    seed_demo_data: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://seatrush:seatrush@localhost:5432/seatrush"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    hold_ttl_seconds: int = 300
    waitlist_offer_ttl_seconds: int = 300
    idempotency_key_ttl_seconds: int = 60 * 60 * 24

    expiry_worker_interval_seconds: float = 2.0
    outbox_worker_interval_seconds: float = 1.0

    queue_admission_rate_per_batch: int = 50
    queue_batch_interval_seconds: float = 3.0
    rate_limit_per_user_per_minute: int = 30
    rate_limit_per_ip_per_minute: int = 60

    admin_bootstrap_email: str = "admin@seatrush.dev"
    admin_bootstrap_password: str = "ChangeMe123!"

    environment: str = "development"


settings = Settings()

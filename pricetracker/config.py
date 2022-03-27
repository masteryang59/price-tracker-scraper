from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: Path = Path("data/prices.db")
    default_currency: str = "USD"

    # Scraping
    headless: bool = True
    page_timeout_seconds: float = 30
    max_attempts: int = 3
    concurrency: int = 3
    min_domain_delay_seconds: float = 2.0
    respect_robots_txt: bool = True

    # Alerts
    min_drop_percent: float = 1.0
    alert_email_to: str = ""
    from_email: str = "price-tracker@localhost"
    alert_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    outbox_dir: Path = Path("outbox")

    # Used by `pricetracker seed-demo`
    demo_shop_url: str = "http://localhost:8080"


@lru_cache
def get_settings() -> Settings:
    return Settings()

def refresh_token(data=None):
    if data is None:
        return None
    return data

def acknowledge_receipt(data=None):
    if data is None:
        return None
    return data

def refresh_token(data=None):
    if data is None:
        return None
    return data
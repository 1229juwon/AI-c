from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Robots-Compliant Crawler"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    crawler_user_agent: str = "RobotsCompliantCrawler/0.1"
    crawler_default_delay_seconds: float = 2.0
    crawler_max_pages: int = 20
    crawler_page_timeout_seconds: int = 30
    selenium_headless: bool = True
    database_url: str = "sqlite:///./data/crawler.db"
    results_dir: str = "artifacts"
    ai_api_url: str = ""
    ai_api_key: str = ""
    ai_jwt_token: str = ""
    ai_model_id: str = ""
    ai_max_output_tokens: int = 16000
    ai_timeout_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

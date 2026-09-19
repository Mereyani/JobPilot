"""Bootstrap-only configuration: things needed before the database (which
holds every per-user setting) is even reachable. Nothing secret lives here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/jobpilot.db"
    web_host: str = "127.0.0.1"
    web_port: int = 8000


settings = Settings()

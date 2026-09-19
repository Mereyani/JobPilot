from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Candidate
    resume_path: str = "./data/resume.pdf"
    target_countries: str = "Syria,Turkey,Saudi Arabia"
    target_roles: str = "Software Engineer"

    # Rate limiting
    application_batch_size: int = 10
    application_batch_interval_minutes: int = 10
    match_threshold: int = 70

    # Database
    database_url: str = "sqlite:///./data/jobpilot.db"

    # Email
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_auto_send: bool = True

    # Optional risky connectors (off by default, see README)
    enable_linkedin_connector: bool = False
    linkedin_email: str = ""
    linkedin_password: str = ""
    enable_indeed_connector: bool = False
    indeed_email: str = ""
    indeed_password: str = ""

    @property
    def countries(self) -> list[str]:
        return [c.strip() for c in self.target_countries.split(",") if c.strip()]

    @property
    def roles(self) -> list[str]:
        return [r.strip() for r in self.target_roles.split(",") if r.strip()]


settings = Settings()

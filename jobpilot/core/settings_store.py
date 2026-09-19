"""Every per-user setting (AI provider + key, email credentials, search
targets, rate limits) lives in the database, not in a checked-in file, and
is edited from the dashboard's Settings page. This is what makes JobPilot
usable by anyone who clones the repo, not just whoever set it up first.
"""

from pydantic import BaseModel

from jobpilot.core.database import SettingsRecord, get_session

GOOGLE_MODEL_DEFAULT = "gemini-3.8-flash"
ANTHROPIC_MODEL_DEFAULT = "claude-sonnet-5"


class RuntimeSettings(BaseModel):
    # --- AI provider (pick one) ---
    llm_provider: str = "anthropic"  # "anthropic" | "google" | "ollama"
    anthropic_api_key: str = ""
    anthropic_model: str = ANTHROPIC_MODEL_DEFAULT
    google_api_key: str = ""
    google_model: str = GOOGLE_MODEL_DEFAULT
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # --- Email (same account used for IMAP + SMTP, e.g. a Gmail app password) ---
    email_address: str = ""
    email_password: str = ""
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    email_auto_send: bool = True

    # --- Job search ---
    resume_path: str = "./data/resume.pdf"
    target_countries: str = "Syria,Turkey,Saudi Arabia"
    target_roles: str = "Software Engineer"
    match_threshold: int = 70
    # Jobs scoring at/above this are applied to automatically; jobs between
    # match_threshold and this are shown in the dashboard for manual
    # selection instead of being sent on their own.
    auto_apply_threshold: int = 90
    # Off by default because it's the single slowest thing JobPilot does:
    # when a listing has no email of its own, this searches the web for the
    # company's contact address, which means a headless browser per search
    # plus one per candidate result page. Worth minutes per job, and most
    # of the time the answer is still "no usable address" - so it's an
    # explicit opt-in rather than something every apply run pays for.
    company_email_search_enabled: bool = False

    # --- Outbound application pacing ---
    application_batch_size: int = 10
    application_batch_interval_minutes: int = 10

    # --- Automatic recurring runs (off by default - this sends real email
    # unattended once enabled, so it's an explicit opt-in) ---
    auto_run_enabled: bool = False
    auto_run_interval_hours: float = 24

    @property
    def countries(self) -> list[str]:
        return [c.strip() for c in self.target_countries.split(",") if c.strip()]

    @property
    def roles(self) -> list[str]:
        return [r.strip() for r in self.target_roles.split(",") if r.strip()]


EMAIL_PROVIDER_PRESETS = {
    "gmail": {"imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 587},
    "outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
    },
    "yahoo": {"imap_host": "imap.mail.yahoo.com", "imap_port": 993, "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 587},
}


def get_settings() -> RuntimeSettings:
    with get_session() as session:
        record = session.query(SettingsRecord).order_by(SettingsRecord.id.desc()).first()
        if record is None:
            return RuntimeSettings()
        return RuntimeSettings.model_validate(record.data)


def save_settings(new_settings: RuntimeSettings) -> RuntimeSettings:
    with get_session() as session:
        session.query(SettingsRecord).delete()
        session.add(SettingsRecord(data=new_settings.model_dump()))
        session.commit()
    return new_settings


def update_settings(**changes) -> RuntimeSettings:
    updated = get_settings().model_copy(update=changes)
    return save_settings(updated)

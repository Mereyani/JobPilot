"""The dashboard: a small FastAPI app for watching JobPilot work and for
configuring it - AI provider + key, email account, search targets, pacing.
Nothing here is specific to any one person; every field is edited from
the Settings page and stored in the local database.
"""

import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from jobpilot.core.database import ApplicationRecord, EmailRecord, JobRecord, get_session, init_db
from jobpilot.core.settings_store import EMAIL_PROVIDER_PRESETS, get_settings, update_settings
from jobpilot.web.i18n import DEFAULT_LANG, LANGUAGES, translator

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="JobPilot")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _lang_context(request: Request) -> dict:
    lang = request.cookies.get("lang", DEFAULT_LANG)
    if lang not in LANGUAGES:
        lang = DEFAULT_LANG
    return {"lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "languages": LANGUAGES, "t": translator(lang)}

# In-memory only: which stage last ran and how it went. Resets on restart -
# that's fine, it's just a status hint on the dashboard, not app state.
_last_run: dict[str, str] = {}


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _run_stage(name: str, fn) -> None:
    try:
        result = fn()
        _last_run[name] = f"OK ({result})"
    except Exception as exc:
        logger.exception("%s failed", name)
        _last_run[name] = f"Error: {exc}"


@app.get("/")
def dashboard(request: Request):
    with get_session() as session:
        jobs = (
            session.query(JobRecord)
            .order_by(JobRecord.match_score.desc().nullslast(), JobRecord.created_at.desc())
            .limit(200)
            .all()
        )
        applications = session.query(ApplicationRecord).order_by(ApplicationRecord.id.desc()).limit(100).all()
        emails = session.query(EmailRecord).order_by(EmailRecord.id.desc()).limit(50).all()

        settings = get_settings()
        # Computed as real counts over the whole table, not over the
        # display-limited lists above - otherwise these silently undercount
        # once there are more than 100-200 rows.
        stats = {
            "total_jobs": session.query(func.count(JobRecord.id)).scalar(),
            "matched": session.query(func.count(JobRecord.id))
            .filter(JobRecord.match_score >= settings.match_threshold)
            .scalar(),
            "applied": session.query(func.count(ApplicationRecord.id))
            .filter(ApplicationRecord.status == "applied")
            .scalar(),
            "interviews": session.query(func.count(ApplicationRecord.id))
            .filter(ApplicationRecord.status == "interview")
            .scalar(),
        }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "jobs": jobs,
            "applications": applications,
            "emails": emails,
            "stats": stats,
            "last_run": _last_run,
            "settings": settings,
            **_lang_context(request),
        },
    )


@app.post("/run/{stage}")
def run_stage(stage: str, background_tasks: BackgroundTasks):
    from jobpilot.agents import application_agent, email_agent, matching_agent, search_agent

    stages = {
        "search": search_agent.run,
        "match": matching_agent.run,
        "apply": application_agent.run,
        "check-email": email_agent.poll_inbox,
    }
    fn = stages.get(stage)
    if fn is not None:
        _last_run[stage] = "Running..."
        background_tasks.add_task(_run_stage, stage, fn)
    return RedirectResponse("/", status_code=303)


@app.get("/settings")
def settings_form(request: Request, saved: int = 0):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": get_settings(),
            "presets": EMAIL_PROVIDER_PRESETS,
            "saved": saved,
            **_lang_context(request),
        },
    )


@app.get("/lang/{code}")
def set_lang(code: str, request: Request):
    response = RedirectResponse(request.headers.get("referer", "/"), status_code=303)
    if code in LANGUAGES:
        response.set_cookie("lang", code, max_age=60 * 60 * 24 * 365)
    return response


@app.post("/settings")
def save_settings(
    llm_provider: str = Form("anthropic"),
    anthropic_api_key: str = Form(""),
    anthropic_model: str = Form(...),
    google_api_key: str = Form(""),
    google_model: str = Form(...),
    ollama_base_url: str = Form("http://localhost:11434"),
    ollama_model: str = Form(""),
    email_address: str = Form(""),
    email_password: str = Form(""),
    imap_host: str = Form(""),
    imap_port: int = Form(993),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    email_auto_send: str | None = Form(None),
    target_countries: str = Form(""),
    target_roles: str = Form(""),
    match_threshold: int = Form(70),
    application_batch_size: int = Form(10),
    application_batch_interval_minutes: int = Form(10),
    resume_path: str = Form("./data/resume.pdf"),
):
    current = get_settings()
    update_settings(
        llm_provider=llm_provider,
        # Secret fields render blank in the form; keep the stored value
        # unless the user actually typed a new one.
        anthropic_api_key=anthropic_api_key or current.anthropic_api_key,
        anthropic_model=anthropic_model,
        google_api_key=google_api_key or current.google_api_key,
        google_model=google_model,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        email_address=email_address,
        email_password=email_password or current.email_password,
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        email_auto_send=email_auto_send is not None,
        target_countries=target_countries,
        target_roles=target_roles,
        match_threshold=match_threshold,
        application_batch_size=application_batch_size,
        application_batch_interval_minutes=application_batch_interval_minutes,
        resume_path=resume_path,
    )
    return RedirectResponse("/settings?saved=1", status_code=303)

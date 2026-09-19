"""The dashboard: a small FastAPI app for watching JobPilot work and for
configuring it - AI provider + key, email account, search targets, pacing.
Nothing here is specific to any one person; every field is edited from
the Settings page and stored in the local database.
"""

import logging
import threading
import time as time_module
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from jobpilot.core.database import ApplicationRecord, EmailRecord, JobRecord, get_session, init_db
from jobpilot.core.settings_store import EMAIL_PROVIDER_PRESETS, get_settings, update_settings
from jobpilot.web.i18n import DEFAULT_LANG, LANGUAGES, translator

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_AUTO_RUN_POLL_SECONDS = 60


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    threading.Thread(target=_auto_run_loop, daemon=True).start()
    yield


app = FastAPI(title="JobPilot", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    """This dashboard has no login - the only thing standing between a
    malicious web page (open in the same browser, on some other tab) and
    "silently change my SMTP server" or "silently send real applications"
    is that a browser POST to http://127.0.0.1:<port> from another origin
    still carries an Origin header. Any state-changing request whose
    Origin doesn't match our own is rejected outright."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
    return await call_next(request)


def _lang_context(request: Request) -> dict:
    lang = request.cookies.get("lang", DEFAULT_LANG)
    if lang not in LANGUAGES:
        lang = DEFAULT_LANG
    return {"lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "languages": LANGUAGES, "t": translator(lang)}

# In-memory only: which stage last ran and how it went, and which stages
# are currently running. Resets on restart - that's fine, it's just a
# status hint for the dashboard's live-polling JS, not app state.
_last_run: dict[str, str] = {}
_running: set[str] = set()

def _stage_functions() -> dict:
    from jobpilot.agents import application_agent, email_agent, matching_agent, search_agent

    return {
        "search": search_agent.run,
        "match": matching_agent.run,
        "apply": application_agent.run,
        "check-email": email_agent.poll_inbox,
    }


def _run_stage(name: str, fn) -> None:
    try:
        result = fn(progress=lambda msg: _last_run.__setitem__(name, msg))
        _last_run[name] = f"Done: {result}"
    except Exception as exc:
        logger.exception("%s failed", name)
        _last_run[name] = f"Error: {exc}"
    finally:
        _running.discard(name)


def _trigger_stage(stage: str) -> bool:
    """Start a stage in the background if it isn't already running.
    Returns True if it was actually started."""
    fn = _stage_functions().get(stage)
    if fn is None or stage in _running:
        return False
    _last_run[stage] = "Starting..."
    _running.add(stage)
    threading.Thread(target=_run_stage, args=(stage, fn), daemon=True).start()
    return True


def _trigger_apply_selected(job_ids: list[str]) -> bool:
    """Apply to exactly these manually-picked jobs (dashboard checkboxes) -
    a separate pseudo-stage from the automatic `apply`, tracked the same
    way so it shows up live in the status strip too."""
    if not job_ids or "apply-selected" in _running:
        return False
    from jobpilot.agents import application_agent

    def fn(progress=None):
        return application_agent.apply_to_jobs(job_ids, progress=progress)

    _last_run["apply-selected"] = "Starting..."
    _running.add("apply-selected")
    threading.Thread(target=_run_stage, args=("apply-selected", fn), daemon=True).start()
    return True


def _auto_run_loop() -> None:
    """Runs the full pipeline on the interval set in Settings ('Run
    automatically'). Off by default - enabling it means real applications
    get sent, unattended, on a timer. Re-reads settings every poll so
    toggling it off (or changing the interval) takes effect within
    `_AUTO_RUN_POLL_SECONDS`, not only after the next full interval.
    """
    while True:
        settings = get_settings()
        if settings.auto_run_enabled:
            logger.info("Auto-run: starting scheduled pipeline")
            for stage, fn in _stage_functions().items():
                if stage in _running:
                    continue  # a manual run is already in flight for this stage
                _last_run[stage] = "Starting (auto)..."
                _running.add(stage)
                _run_stage(stage, fn)  # blocks until this stage finishes
            interval_hours = get_settings().auto_run_interval_hours
        else:
            interval_hours = _AUTO_RUN_POLL_SECONDS / 3600  # check back soon in case it gets enabled

        deadline = time_module.time() + max(interval_hours, 0.1) * 3600
        while time_module.time() < deadline:
            time_module.sleep(min(_AUTO_RUN_POLL_SECONDS, deadline - time_module.time()))
            if get_settings().auto_run_enabled != settings.auto_run_enabled:
                break  # setting changed mid-wait - re-evaluate immediately


def _compute_stats(session) -> dict:
    settings = get_settings()
    # Real counts over the whole table, not over any display-limited list -
    # otherwise these silently undercount past 100-200 rows.
    return {
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
        stats = _compute_stats(session)

        # Keyed by job external_id so the template can show "already sent"
        # and decide which jobs are eligible for manual selection - a job
        # in the manual band (match_threshold <= score < auto_apply_threshold)
        # is only selectable if it has no application yet, or its one
        # attempt so far failed (eligible for retry, same rule as _eligible_jobs).
        applications_by_job = {a.job_external_id: a for a in session.query(ApplicationRecord).all()}

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "jobs": jobs,
            "applications": applications,
            "applications_by_job": applications_by_job,
            "emails": emails,
            "stats": stats,
            "last_run": _last_run,
            "running": _running,
            "settings": settings,
            **_lang_context(request),
        },
    )


@app.get("/api/status")
def api_status():
    """Polled by the dashboard's JS to show live progress without a manual
    refresh, and to know when to reload for fresh table/stat data."""
    with get_session() as session:
        stats = _compute_stats(session)
    return {"last_run": _last_run, "running": sorted(_running), "stats": stats}


@app.post("/run/{stage}")
def run_stage(stage: str):
    _trigger_stage(stage)
    return RedirectResponse("/", status_code=303)


@app.post("/apply-selected")
def apply_selected(job_ids: list[str] = Form([])):
    _trigger_apply_selected(job_ids)
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
    auto_apply_threshold: int = Form(90),
    company_email_search_enabled: str | None = Form(None),
    application_batch_size: int = Form(10),
    application_batch_interval_minutes: int = Form(10),
    resume_path: str = Form("./data/resume.pdf"),
    auto_run_enabled: str | None = Form(None),
    auto_run_interval_hours: float = Form(24),
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
        auto_apply_threshold=auto_apply_threshold,
        company_email_search_enabled=company_email_search_enabled is not None,
        application_batch_size=application_batch_size,
        application_batch_interval_minutes=application_batch_interval_minutes,
        resume_path=resume_path,
        auto_run_enabled=auto_run_enabled is not None,
        auto_run_interval_hours=auto_run_interval_hours,
    )
    return RedirectResponse("/settings?saved=1", status_code=303)

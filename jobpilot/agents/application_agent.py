"""The whole "apply" step, in one sentence: find a contact email for the
job (on the listing page, or by searching the web for the company's own
contact address if the listing has none), write a tailored cover letter,
send it with the candidate's resume attached - N applications at a time
with a cooldown in between.

Two ways a job gets applied to:
- `run()`: fully automatic, but only for jobs scoring at/above
  `auto_apply_threshold` - a deliberately high bar so unattended sending
  only fires for near-perfect matches.
- `apply_to_jobs()`: applies to exactly the job ids passed in, for the
  dashboard's manual-selection flow (jobs between `match_threshold` and
  `auto_apply_threshold` are shown there instead of being auto-sent).

No platform-specific form-filling, no browser automation for the actual
application: if no email can be found anywhere, it's marked failed for
manual follow-up instead.
"""

import logging
from collections.abc import Callable

from jobpilot.agents.email_agent import build_subject, send_email
from jobpilot.agents.profile_agent import load_profile
from jobpilot.core.database import ApplicationRecord, JobRecord, get_session, utcnow
from jobpilot.core.email_extract import find_contact_email_on_page, search_company_email
from jobpilot.core.llm import ask_text
from jobpilot.core.models import ApplyMethod, CandidateProfile
from jobpilot.core.rate_limiter import BatchRateLimiter
from jobpilot.core.settings_store import get_settings

logger = logging.getLogger(__name__)

COVER_LETTER_SYSTEM_PROMPT = """You write a concise, specific cover letter
(150-250 words) for a job application email. Use only facts present in the
candidate profile - never invent experience. Reference 1-2 concrete details
from the job description that match the candidate's background. The
candidate's resume is attached to this email separately, so you may refer
to "my attached resume/CV" but do not restate its full contents. Output
only the letter body, no subject line or salutation placeholders like
"[Company]"."""


def _contact_email(job: JobRecord) -> str | None:
    if job.apply_method == ApplyMethod.EMAIL.value and job.apply_target:
        return job.apply_target
    email = find_contact_email_on_page(job.url)
    if email:
        return email
    return search_company_email(job.company)


def _cover_letter(profile: CandidateProfile, job: JobRecord) -> str:
    user_prompt = (
        f"CANDIDATE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"JOB POSTING:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description}"
    )
    return ask_text(COVER_LETTER_SYSTEM_PROMPT, user_prompt, max_tokens=500)


def _eligible_jobs(session, min_score: int, only_ids: set[str] | None = None) -> list[JobRecord]:
    # A "failed" attempt (no email found yet, a transient send error, ...)
    # should be retried on the next run - only a real outcome (sent, or a
    # reply came back) means this job is done and should never be
    # attempted again.
    handled_ids = {
        row.job_external_id
        for row in session.query(ApplicationRecord.job_external_id).filter(ApplicationRecord.status != "failed")
    }
    query = (
        session.query(JobRecord)
        .filter(JobRecord.match_score.isnot(None))
        .filter(JobRecord.match_score >= min_score)
    )
    if only_ids is not None:
        query = query.filter(JobRecord.external_id.in_(only_ids))
    jobs = query.order_by(JobRecord.match_score.desc()).all()
    return [j for j in jobs if j.external_id not in handled_ids]


def _apply_one(session, profile: CandidateProfile, job: JobRecord, resume_path: str) -> None:
    thread_key = job.external_id
    # Retrying a previously-failed job updates its existing row instead of
    # piling up duplicate "failed" entries for the same job every run.
    application = session.query(ApplicationRecord).filter_by(job_external_id=job.external_id).first()
    if application is None:
        application = ApplicationRecord(job_external_id=job.external_id, thread_key=thread_key)
    application.status = "pending"
    application.thread_key = thread_key
    application.failure_reason = None

    contact_email = _contact_email(job)
    if not contact_email:
        logger.info("No contact email found for %s - skipping (manual application needed)", job.external_id)
        application.status = "failed"
        application.failure_reason = "no_contact_email"
        session.add(application)
        session.commit()
        return

    try:
        cover_letter = _cover_letter(profile, job)
        subject = build_subject(job.title, job.company, thread_key)
        send_email(contact_email, subject, cover_letter, attachments=[resume_path])
        application.cover_letter = cover_letter
        application.status = "applied"
        application.applied_at = utcnow()
    except Exception as exc:
        logger.exception("Failed to email application for %s", job.external_id)
        application.status = "failed"
        application.failure_reason = f"send_error: {exc}"

    session.add(application)
    session.commit()


def _apply_batch(jobs: list[JobRecord], profile: CandidateProfile, resume_path: str, report: Callable[[str], None]) -> int:
    settings = get_settings()
    limiter = BatchRateLimiter(
        batch_size=settings.application_batch_size,
        interval_minutes=settings.application_batch_interval_minutes,
    )
    total = len(jobs)
    if total == 0:
        report("No eligible jobs to apply to.")
        return 0

    attempted = 0
    report(f"0/{total} applications sent")
    with get_session() as session:
        for batch in limiter.batches(jobs):
            for job in batch:
                # Re-attach a fresh copy of the job row to this session.
                fresh_job = session.get(JobRecord, job.id)
                report(f"Applying ({attempted + 1}/{total}): {fresh_job.title} at {fresh_job.company}...")
                _apply_one(session, profile, fresh_job, resume_path)
                attempted += 1
                report(f"{attempted}/{total} applications processed")
    return attempted


def run(progress: Callable[[str], None] | None = None) -> int:
    """Auto-apply to every job scoring at/above `auto_apply_threshold`,
    throttled per configuration. Returns the number of applications
    attempted (applied + failed).
    """
    report = progress or (lambda _msg: None)

    profile = load_profile()
    if profile is None:
        raise RuntimeError("No candidate profile found - run the profile agent first.")

    settings = get_settings()
    with get_session() as session:
        jobs = _eligible_jobs(session, settings.auto_apply_threshold)
    return _apply_batch(jobs, profile, settings.resume_path, report)


def apply_to_jobs(job_external_ids: list[str], progress: Callable[[str], None] | None = None) -> int:
    """Apply to exactly these jobs (the dashboard's manual-selection flow),
    as long as each is still at/above `match_threshold` and hasn't already
    been successfully handled. Returns the number attempted.
    """
    report = progress or (lambda _msg: None)

    profile = load_profile()
    if profile is None:
        raise RuntimeError("No candidate profile found - run the profile agent first.")

    settings = get_settings()
    with get_session() as session:
        jobs = _eligible_jobs(session, settings.match_threshold, only_ids=set(job_external_ids))
    return _apply_batch(jobs, profile, settings.resume_path, report)

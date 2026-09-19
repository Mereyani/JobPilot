"""The whole "apply" step, in one sentence: find a contact email on the
job's listing page, write a tailored cover letter, send it with the
candidate's resume attached - N applications at a time with a cooldown in
between.

No platform-specific form-filling, no browser automation: if a listing has
no discoverable email, it's marked failed for manual follow-up instead.
"""

import logging
from collections.abc import Callable

from jobpilot.agents.email_agent import build_subject, send_email
from jobpilot.agents.profile_agent import load_profile
from jobpilot.core.database import ApplicationRecord, JobRecord, get_session, utcnow
from jobpilot.core.email_extract import find_contact_email_on_page
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
    return find_contact_email_on_page(job.url)


def _cover_letter(profile: CandidateProfile, job: JobRecord) -> str:
    user_prompt = (
        f"CANDIDATE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"JOB POSTING:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description}"
    )
    return ask_text(COVER_LETTER_SYSTEM_PROMPT, user_prompt, max_tokens=500)


def _pending_jobs(session, match_threshold: int) -> list[JobRecord]:
    # A "failed" attempt (no email found yet, a transient send error, ...)
    # should be retried on the next run - only a real outcome (sent, or a
    # reply came back) means this job is done and should never be
    # attempted again.
    handled_ids = {
        row.job_external_id
        for row in session.query(ApplicationRecord.job_external_id).filter(ApplicationRecord.status != "failed")
    }
    jobs = (
        session.query(JobRecord)
        .filter(JobRecord.match_score.isnot(None))
        .filter(JobRecord.match_score >= match_threshold)
        .order_by(JobRecord.match_score.desc())
        .all()
    )
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


def run(progress: Callable[[str], None] | None = None) -> int:
    """Apply to every eligible pending job, throttled per configuration.

    Returns the number of applications attempted (applied + failed).
    """
    report = progress or (lambda _msg: None)

    profile = load_profile()
    if profile is None:
        raise RuntimeError("No candidate profile found - run the profile agent first.")

    settings = get_settings()
    limiter = BatchRateLimiter(
        batch_size=settings.application_batch_size,
        interval_minutes=settings.application_batch_interval_minutes,
    )

    attempted = 0
    with get_session() as session:
        pending = _pending_jobs(session, settings.match_threshold)
        total = len(pending)
        if total == 0:
            report("No eligible jobs to apply to.")
            return 0
        report(f"0/{total} applications sent")
        for batch in limiter.batches(pending):
            for job in batch:
                report(f"Applying ({attempted + 1}/{total}): {job.title} at {job.company}...")
                _apply_one(session, profile, job, settings.resume_path)
                attempted += 1
                report(f"{attempted}/{total} applications processed")
    return attempted

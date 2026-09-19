"""Generates a tailored cover letter and submits an application for every
job above the match threshold, throttled to
`APPLICATION_BATCH_SIZE` applications per `APPLICATION_BATCH_INTERVAL_MINUTES`.
"""

import logging
from datetime import datetime

from jobpilot.agents.email_agent import build_subject, send_email
from jobpilot.agents.profile_agent import load_profile
from jobpilot.config import settings
from jobpilot.connectors.bayt import BaytConnector
from jobpilot.core.database import ApplicationRecord, JobRecord, get_session
from jobpilot.core.llm import ask_text
from jobpilot.core.models import Application, ApplicationStatus, ApplyMethod, CandidateProfile, JobListing
from jobpilot.core.rate_limiter import BatchRateLimiter

logger = logging.getLogger(__name__)

COVER_LETTER_SYSTEM_PROMPT = """You write a concise, specific cover letter
(150-250 words) for a job application. Use only facts present in the
candidate profile - never invent experience. Reference 1-2 concrete details
from the job description that match the candidate's background. Output only
the letter body, no subject line or salutation placeholders like "[Company]"."""


def _connectors_by_source() -> dict:
    connectors = {"bayt": BaytConnector()}
    if settings.enable_linkedin_connector:
        from jobpilot.connectors.linkedin import LinkedInConnector

        connectors["linkedin"] = LinkedInConnector()
    if settings.enable_indeed_connector:
        from jobpilot.connectors.indeed import IndeedConnector

        connectors["indeed"] = IndeedConnector()
    return connectors


def _to_job_listing(record: JobRecord) -> JobListing:
    return JobListing(
        source=record.source,
        external_id=record.external_id,
        title=record.title,
        company=record.company,
        location=record.location,
        country=record.country,
        url=record.url,
        description=record.description,
        apply_method=ApplyMethod(record.apply_method),
        apply_target=record.apply_target,
    )


def _cover_letter(profile: CandidateProfile, job: JobRecord) -> str:
    user_prompt = (
        f"CANDIDATE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"JOB POSTING:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description}"
    )
    return ask_text(COVER_LETTER_SYSTEM_PROMPT, user_prompt, max_tokens=500)


def _pending_jobs(session) -> list[JobRecord]:
    applied_ids = {row.job_external_id for row in session.query(ApplicationRecord.job_external_id).all()}
    jobs = (
        session.query(JobRecord)
        .filter(JobRecord.match_score.isnot(None))
        .filter(JobRecord.match_score >= settings.match_threshold)
        .order_by(JobRecord.match_score.desc())
        .all()
    )
    return [j for j in jobs if j.external_id not in applied_ids]


def _apply_one(session, connectors: dict, profile: CandidateProfile, job: JobRecord) -> None:
    cover_letter = _cover_letter(profile, job)
    thread_key = job.external_id
    application = ApplicationRecord(
        job_external_id=job.external_id,
        status="pending",
        cover_letter=cover_letter,
        thread_key=thread_key,
    )

    try:
        if job.apply_method == ApplyMethod.EMAIL.value and job.apply_target:
            subject = build_subject(job.title, job.company, thread_key)
            send_email(job.apply_target, subject, cover_letter)
        else:
            connector = connectors.get(job.source)
            if connector is None:
                raise NotImplementedError(f"No connector available for source '{job.source}'")
            listing = _to_job_listing(job)
            application_model = Application(
                job_external_id=job.external_id,
                status=ApplicationStatus.PENDING,
                cover_letter=cover_letter,
                thread_key=thread_key,
            )
            connector.apply(listing, application_model)
        application.status = "applied"
        application.applied_at = datetime.utcnow()
    except NotImplementedError as exc:
        logger.warning("Skipping auto-apply for %s: %s", job.external_id, exc)
        application.status = "failed"
    except Exception:
        logger.exception("Failed to apply to %s", job.external_id)
        application.status = "failed"

    session.add(application)
    session.commit()


def run() -> int:
    """Apply to every eligible pending job, throttled per configuration.

    Returns the number of applications attempted (applied + failed).
    """
    profile = load_profile()
    if profile is None:
        raise RuntimeError("No candidate profile found - run the profile agent first.")

    connectors = _connectors_by_source()
    limiter = BatchRateLimiter(
        batch_size=settings.application_batch_size,
        interval_minutes=settings.application_batch_interval_minutes,
    )

    attempted = 0
    with get_session() as session:
        pending = _pending_jobs(session)
        for batch in limiter.batches(pending):
            for job in batch:
                _apply_one(session, connectors, profile, job)
                attempted += 1
    return attempted

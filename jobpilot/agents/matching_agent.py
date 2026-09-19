"""Scores un-scored jobs against the candidate's profile using Claude."""

import logging

from jobpilot.agents.profile_agent import load_profile
from jobpilot.core.database import JobRecord, get_session
from jobpilot.core.llm import ask_json
from jobpilot.core.models import CandidateProfile

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You score how well a candidate matches a job posting.
Return a JSON object with exactly two keys:
score (integer 0-100, where 100 is a perfect match on skills/seniority/domain),
reason (one or two sentences explaining the score, mentioning the strongest
match and the biggest gap)."""


def _score(profile: CandidateProfile, job: JobRecord) -> tuple[int, str]:
    user_prompt = (
        f"CANDIDATE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"JOB POSTING:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Location: {job.location}\nDescription:\n{job.description}"
    )
    data = ask_json(SYSTEM_PROMPT, user_prompt, max_tokens=300)
    score = int(data.get("score", 0))
    reason = str(data.get("reason", ""))
    return max(0, min(100, score)), reason


def run() -> int:
    """Score every job that doesn't have a match_score yet.

    Returns the number of jobs scored.
    """
    profile = load_profile()
    if profile is None:
        raise RuntimeError("No candidate profile found - run the profile agent first.")

    scored = 0
    with get_session() as session:
        pending = session.query(JobRecord).filter(JobRecord.match_score.is_(None)).all()
        for job in pending:
            try:
                score, reason = _score(profile, job)
            except Exception:
                logger.exception("Failed to score job %s", job.external_id)
                continue
            job.match_score = score
            job.match_reason = reason
            scored += 1
        session.commit()
    return scored

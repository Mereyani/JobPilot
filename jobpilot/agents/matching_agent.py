"""Scores un-scored jobs against the candidate's profile using Claude."""

import logging

from jobpilot.agents.profile_agent import load_profile
from jobpilot.core.database import JobRecord, get_session
from jobpilot.core.llm import ask_json
from jobpilot.core.models import CandidateProfile

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You score how well a candidate matches a job posting, for
someone who wants to apply only to jobs they are actually qualified for -
not stretch roles.

Seniority fit is a hard gate, not just one factor among others: infer the
candidate's experience level from their profile (years of relevant work
experience, whether they are a recent graduate/junior, etc.), and infer the
job's required level from its title and description (e.g. "Senior",
"Staff", "Principal", "Lead", or years-of-experience requirements). If the
job clearly requires meaningfully more seniority than the candidate has,
cap the score at 30 regardless of how well the skills otherwise match - a
skills match does not make up for being under-qualified on seniority.
Within that constraint, score skills/domain overlap normally.

Return a JSON object with exactly two keys:
score (integer 0-100, where 100 is a strong match on both skills and
seniority level),
reason (one or two sentences explaining the score, mentioning the strongest
match and the biggest gap - explicitly note it if seniority was the
limiting factor)."""


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

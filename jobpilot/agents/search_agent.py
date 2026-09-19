"""Runs every connector across the configured countries, upserting results
into the jobs table.

Search keywords are generated per country from the candidate's actual
profile rather than a single fixed role string - this keeps results
relevant to what the candidate can actually do (no invented seniority)
and lets each country's keyword set include the language postings there
are typically written in (e.g. Arabic phrasings for Syria/Saudi Arabia),
which the Bayt connector then searches directly.
"""

import logging
from collections.abc import Callable

from jobpilot.agents.profile_agent import load_profile
from jobpilot.connectors.bayt import BaytConnector
from jobpilot.core.database import JobRecord, get_session
from jobpilot.core.llm import ask_json
from jobpilot.core.models import CandidateProfile, JobListing
from jobpilot.core.settings_store import get_settings

logger = logging.getLogger(__name__)

KEYWORDS_SYSTEM_PROMPT = """You generate job-search keywords for a candidate
to use on a job board, for one specific target country.

Rules:
- Base every keyword on what the candidate can actually do today per their
  profile - do not include "Senior", "Staff", "Lead", "Principal", "Manager",
  or any title implying more experience/seniority than they currently have.
- Include keywords in whichever language(s) job postings in that country are
  normally written in. For Arabic-speaking countries (e.g. Syria, Saudi
  Arabia, Egypt, Jordan, UAE), include some Arabic-language job-title
  phrasings alongside English ones, since many local postings are in Arabic.
  For other countries, English is usually enough unless you know postings
  there commonly use another language.
- Cover a reasonable spread of the candidate's actual skills (e.g. a
  generalist backend/AI candidate might get "Software Engineer", "Python
  Developer", "Machine Learning Engineer", "مهندس برمجيات") rather than one
  narrow title repeated.

Return a JSON object with exactly one key, "keywords": an array of 4 to 8
short strings, each usable directly as a job-board search query."""


def _keywords_for_country(profile: CandidateProfile | None, country: str, fallback: list[str]) -> list[str]:
    if profile is None:
        return fallback
    try:
        user_prompt = f"CANDIDATE PROFILE:\n{profile.model_dump_json(indent=2)}\n\nTARGET COUNTRY: {country}"
        data = ask_json(KEYWORDS_SYSTEM_PROMPT, user_prompt, max_tokens=400)
        keywords = [k.strip() for k in data.get("keywords", []) if isinstance(k, str) and k.strip()]
        return keywords[:8] if keywords else fallback
    except Exception:
        logger.exception("Failed to generate AI search keywords for %s - falling back to configured roles", country)
        return fallback


def _connectors() -> list:
    return [BaytConnector()]


def _upsert(session, job: JobListing) -> bool:
    """Insert a job if it's new. Returns True if it was newly added."""
    existing = session.query(JobRecord).filter_by(external_id=job.external_id).first()
    if existing:
        return False
    session.add(
        JobRecord(
            source=job.source,
            external_id=job.external_id,
            title=job.title,
            company=job.company,
            location=job.location,
            country=job.country,
            url=job.url,
            description=job.description,
            apply_method=job.apply_method.value,
            apply_target=job.apply_target,
            posted_at=job.posted_at,
        )
    )
    return True


def run(limit_per_query: int = 25, progress: Callable[[str], None] | None = None) -> int:
    """Search all countries across every connector.

    Returns the number of newly discovered jobs.
    """
    report = progress or (lambda _msg: None)

    settings = get_settings()
    profile = load_profile()
    new_count = 0
    with get_session() as session:
        for connector in _connectors():
            for country in settings.countries:
                report(f"Generating search keywords for {country}...")
                keywords = _keywords_for_country(profile, country, settings.roles)
                report(f"Searching {connector.name} in {country} for: {', '.join(keywords)}")
                try:
                    jobs = connector.search(keywords, country, limit=limit_per_query)
                except Exception:
                    logger.exception("%s search failed for %s", connector.name, country)
                    report(f"{connector.name} search failed for {country} - see logs")
                    continue
                added = 0
                for job in jobs:
                    if _upsert(session, job):
                        new_count += 1
                        added += 1
                report(f"{country}: found {len(jobs)} listings, {added} new")
        session.commit()
    return new_count

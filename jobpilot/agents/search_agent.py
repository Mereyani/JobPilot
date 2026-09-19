"""Runs every connector across the configured countries/roles and upserts
results into the jobs table."""

import logging

from jobpilot.connectors.bayt import BaytConnector
from jobpilot.core.database import JobRecord, get_session
from jobpilot.core.models import JobListing
from jobpilot.core.settings_store import get_settings

logger = logging.getLogger(__name__)


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


def run(limit_per_query: int = 25) -> int:
    """Search all countries x roles across every connector.

    Returns the number of newly discovered jobs.
    """
    settings = get_settings()
    new_count = 0
    with get_session() as session:
        for connector in _connectors():
            for country in settings.countries:
                try:
                    jobs = connector.search(settings.roles, country, limit=limit_per_query)
                except Exception:
                    logger.exception("%s search failed for %s", connector.name, country)
                    continue
                for job in jobs:
                    if _upsert(session, job):
                        new_count += 1
        session.commit()
    return new_count

"""Ties the agents together into one run: search -> match -> apply -> check email."""

import logging

from jobpilot.agents import application_agent, email_agent, matching_agent, search_agent

logger = logging.getLogger(__name__)


def run_once() -> dict[str, int]:
    new_jobs = search_agent.run()
    logger.info("Search agent found %d new jobs", new_jobs)

    scored = matching_agent.run()
    logger.info("Matching agent scored %d jobs", scored)

    applied = application_agent.run()
    logger.info("Application agent attempted %d applications", applied)

    emails = email_agent.poll_inbox()
    logger.info("Email agent processed %d inbound emails", emails)

    return {
        "new_jobs": new_jobs,
        "scored": scored,
        "applications_attempted": applied,
        "emails_processed": emails,
    }

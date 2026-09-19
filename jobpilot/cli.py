import logging

import click

from jobpilot.core.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@click.group()
def cli() -> None:
    """JobPilot - a multi-agent job search & application assistant."""
    init_db()


@cli.command("parse-profile")
@click.option("--resume", required=True, help="Path to your resume PDF.")
def parse_profile(resume: str) -> None:
    """Parse a resume into a structured candidate profile."""
    from jobpilot.agents import profile_agent

    profile = profile_agent.run(resume)
    click.echo(profile.model_dump_json(indent=2))


@cli.command("search")
def search() -> None:
    """Search all enabled connectors for new jobs."""
    from jobpilot.agents import search_agent

    count = search_agent.run()
    click.echo(f"Found {count} new jobs.")


@cli.command("match")
def match() -> None:
    """Score every unscored job against the saved candidate profile."""
    from jobpilot.agents import matching_agent

    count = matching_agent.run()
    click.echo(f"Scored {count} jobs.")


@cli.command("apply")
def apply_() -> None:
    """Apply to every eligible job above the match threshold (rate-limited)."""
    from jobpilot.agents import application_agent

    count = application_agent.run()
    click.echo(f"Attempted {count} applications.")


@cli.command("check-email")
def check_email() -> None:
    """Poll the inbox, classify replies, and (if enabled) auto-respond."""
    from jobpilot.agents import email_agent

    count = email_agent.poll_inbox()
    click.echo(f"Processed {count} emails.")


@cli.command("run")
def run() -> None:
    """Run the full pipeline once: search -> match -> apply -> check email."""
    from jobpilot import orchestrator

    result = orchestrator.run_once()
    click.echo(result)


@cli.command("serve")
@click.option("--host", default=None, help="Defaults to WEB_HOST in .env, or 127.0.0.1.")
@click.option("--port", default=None, type=int, help="Defaults to WEB_PORT in .env, or 8000.")
def serve(host: str | None, port: int | None) -> None:
    """Launch the dashboard - configure settings and watch jobs/applications/emails."""
    import uvicorn

    from jobpilot.config import settings

    uvicorn.run("jobpilot.web.app:app", host=host or settings.web_host, port=port or settings.web_port)


if __name__ == "__main__":
    cli()

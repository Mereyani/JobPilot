from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from jobpilot.agents.application_agent import _apply_one, _contact_email, _eligible_jobs
from jobpilot.core.database import ApplicationRecord, Base, JobRecord
from jobpilot.core.models import CandidateProfile

PROFILE = CandidateProfile(name="Test Candidate", skills=["Python"])


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


def _make_job(session, external_id="bayt:1", match_score=80, company="Acme") -> JobRecord:
    job = JobRecord(
        source="bayt",
        external_id=external_id,
        title="Software Engineer",
        company=company,
        url="https://example.com/job/1",
        apply_method="form",
        match_score=match_score,
    )
    session.add(job)
    session.commit()
    return job


def test_failed_application_is_retried_not_excluded(session):
    job = _make_job(session)
    session.add(ApplicationRecord(job_external_id=job.external_id, status="failed", thread_key=job.external_id))
    session.commit()

    pending = _eligible_jobs(session, min_score=70)

    assert [j.external_id for j in pending] == [job.external_id]


def test_applied_job_is_excluded_from_eligible(session):
    job = _make_job(session)
    session.add(ApplicationRecord(job_external_id=job.external_id, status="applied", thread_key=job.external_id))
    session.commit()

    assert _eligible_jobs(session, min_score=70) == []


def test_interview_and_rejected_jobs_are_excluded(session):
    j1 = _make_job(session, external_id="bayt:1")
    j2 = _make_job(session, external_id="bayt:2")
    session.add(ApplicationRecord(job_external_id=j1.external_id, status="interview"))
    session.add(ApplicationRecord(job_external_id=j2.external_id, status="rejected"))
    session.commit()

    assert _eligible_jobs(session, min_score=70) == []


def test_below_threshold_jobs_are_excluded(session):
    _make_job(session, match_score=50)
    assert _eligible_jobs(session, min_score=70) == []


def test_only_ids_filter(session):
    j1 = _make_job(session, external_id="bayt:1", match_score=75)
    _make_job(session, external_id="bayt:2", match_score=95)

    result = _eligible_jobs(session, min_score=70, only_ids={"bayt:1"})

    assert [j.external_id for j in result] == [j1.external_id]


def test_retry_updates_existing_row_instead_of_duplicating(session):
    job = _make_job(session)
    session.add(ApplicationRecord(job_external_id=job.external_id, status="failed", thread_key=job.external_id))
    session.commit()

    with patch("jobpilot.agents.application_agent._contact_email", return_value=None):
        _apply_one(session, PROFILE, job, resume_path="/no/resume.pdf")

    rows = session.query(ApplicationRecord).filter_by(job_external_id=job.external_id).all()
    assert len(rows) == 1
    assert rows[0].status == "failed"


def test_successful_apply_attaches_resume_and_marks_applied(session, tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    job = _make_job(session)

    with (
        patch("jobpilot.agents.application_agent._contact_email", return_value="hiring@acme.com"),
        patch("jobpilot.agents.application_agent._cover_letter", return_value="Dear hiring team, ..."),
        patch("jobpilot.agents.application_agent.send_email") as mock_send,
    ):
        _apply_one(session, PROFILE, job, resume_path=str(resume))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["attachments"] == [str(resume)]

    row = session.query(ApplicationRecord).filter_by(job_external_id=job.external_id).one()
    assert row.status == "applied"
    assert row.applied_at is not None


def test_contact_email_falls_back_to_company_search_when_page_has_none(session):
    job = _make_job(session, company="Acme Corp")

    with (
        patch("jobpilot.agents.application_agent.find_contact_email_on_page", return_value=None),
        patch("jobpilot.agents.application_agent.search_company_email", return_value="hiring@acme.com") as mock_search,
    ):
        result = _contact_email(job)

    assert result == "hiring@acme.com"
    mock_search.assert_called_once_with("Acme Corp")


def test_contact_email_skips_company_search_when_page_has_an_email(session):
    job = _make_job(session, company="Acme Corp")

    with (
        patch("jobpilot.agents.application_agent.find_contact_email_on_page", return_value="jobs@acme.com"),
        patch("jobpilot.agents.application_agent.search_company_email") as mock_search,
    ):
        result = _contact_email(job)

    assert result == "jobs@acme.com"
    mock_search.assert_not_called()

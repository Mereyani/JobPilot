from jobpilot.core.models import ApplyMethod, CandidateProfile, JobListing


def test_candidate_profile_defaults():
    profile = CandidateProfile(name="Test Candidate")
    assert profile.skills == []
    assert profile.languages == {}


def test_job_listing_requires_core_fields():
    job = JobListing(
        source="bayt",
        external_id="bayt:123",
        title="Software Engineer",
        company="Acme",
        url="https://example.com/job/123",
    )
    assert job.apply_method == ApplyMethod.UNKNOWN
    assert job.match_score is None

from unittest.mock import patch

from jobpilot.agents.search_agent import _keywords_for_country
from jobpilot.core.models import CandidateProfile

PROFILE = CandidateProfile(name="Test Candidate", skills=["Python", "TensorFlow"])


def test_falls_back_to_configured_roles_without_a_profile():
    assert _keywords_for_country(None, "Turkey", ["Software Engineer"]) == ["Software Engineer"]


def test_uses_ai_keywords_when_profile_present():
    with patch(
        "jobpilot.agents.search_agent.ask_json",
        return_value={"keywords": ["Software Engineer", "مهندس برمجيات", "Python Developer"]},
    ):
        keywords = _keywords_for_country(PROFILE, "Saudi Arabia", ["Software Engineer"])
    assert keywords == ["Software Engineer", "مهندس برمجيات", "Python Developer"]


def test_falls_back_on_ai_failure():
    with patch("jobpilot.agents.search_agent.ask_json", side_effect=RuntimeError("boom")):
        keywords = _keywords_for_country(PROFILE, "Turkey", ["Software Engineer"])
    assert keywords == ["Software Engineer"]


def test_falls_back_when_ai_returns_no_usable_keywords():
    with patch("jobpilot.agents.search_agent.ask_json", return_value={"keywords": []}):
        keywords = _keywords_for_country(PROFILE, "Turkey", ["Software Engineer"])
    assert keywords == ["Software Engineer"]

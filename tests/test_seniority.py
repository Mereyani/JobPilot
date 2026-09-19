import pytest

from jobpilot.core.seniority import required_years, title_is_senior, too_senior


@pytest.mark.parametrize(
    "title",
    [
        "Senior Software Engineer (Oracle)",  # the real posting that motivated this
        "Sr. Backend Developer",
        "Staff Engineer",
        "Principal Data Scientist",
        "Engineering Manager",
        "Head of Platform",
        "Solution Architect",
        "Tech Lead",
        "مهندس برمجيات أول",
        "مدير تقنية المعلومات",
        "رئيس قسم التطوير",
        "خبير أمن معلومات",
    ],
)
def test_rejects_over_level_titles(title):
    assert title_is_senior(title)


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer - New Grad",
        "Junior Python Developer",
        "Data Analyst",
        "IT Technician",
        "Technical Support Specialist",
        "مهندس برمجيات",
        "مطور واجهات أمامية",
        # "Lead Generation" is an entry-level sales role, not a lead role.
        "Lead Generation Specialist",
    ],
)
def test_accepts_titles_at_the_candidates_level(title):
    assert not title_is_senior(title)


def test_reads_years_of_experience_from_the_description():
    assert required_years("We need 5+ years of experience in Python") == 5
    assert required_years("خبرة لا تقل عن 7 سنوات") == 7
    assert required_years("No experience required") is None


def test_takes_the_largest_year_figure_mentioned():
    text = "2 years in QA, 6 years of backend development required"
    assert required_years(text) == 6


def test_too_senior_reports_which_rule_rejected_the_job():
    assert too_senior("Senior Engineer", "") == "senior_title"
    assert too_senior("Software Engineer", "8 years of experience") == "requires_8_years"
    assert too_senior("Software Engineer", "1 year of experience") is None


def test_a_junior_title_with_a_modest_experience_ask_still_passes():
    assert too_senior("Backend Developer", "2 years of experience preferred") is None

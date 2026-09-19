import json
from unittest.mock import patch

from jobpilot.connectors.websearch import (
    WebSearchConnector,
    _listing_from_jsonld,
    _matches_country,
    _postings_on_page,
    _same_site_job_links,
)
from jobpilot.core.models import ApplyMethod

# Shaped exactly like the markup jobsyria.net serves on a real listing,
# with invented content.
POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "مهندس برمجيات",
    "description": "<p>مطلوب مهندس برمجيات. للتواصل: careers@example-sy.com</p>",
    "datePosted": "2026-09-16T07:42:53+00:00",
    "hiringOrganization": {"@type": "Organization", "name": "شركة مثال"},
    "jobLocation": {
        "@type": "Place",
        "address": {"@type": "PostalAddress", "addressCountry": "SY", "addressRegion": "دمشق"},
    },
}


def _page(obj) -> str:
    return f'<html><head><script type="application/ld+json">{json.dumps(obj)}</script></head><body>x</body></html>'


def test_parses_a_real_shaped_job_posting():
    listings = _postings_on_page(_page(POSTING), "https://board.example/jobs/1", "Syria")

    assert len(listings) == 1
    job = listings[0]
    assert job.title == "مهندس برمجيات"
    assert job.company == "شركة مثال"
    assert job.source == "web"
    assert job.posted_at.year == 2026
    # HTML inside the description is stripped, not passed through.
    assert "<p>" not in job.description


def test_an_email_in_the_posting_becomes_the_apply_target():
    job = _postings_on_page(_page(POSTING), "https://board.example/jobs/1", "Syria")[0]

    assert job.apply_method == ApplyMethod.EMAIL
    assert job.apply_target == "careers@example-sy.com"


def test_a_posting_without_an_email_is_not_marked_as_emailable():
    obj = dict(POSTING, description="<p>قدم عبر الموقع</p>")
    job = _postings_on_page(_page(obj), "https://board.example/jobs/2", "Syria")[0]

    assert job.apply_method == ApplyMethod.FORM
    assert job.apply_target is None


def test_the_same_url_always_gets_the_same_id_so_reruns_dedupe():
    url = "https://board.example/jobs/1"
    first = _postings_on_page(_page(POSTING), url, "Syria")[0]
    second = _postings_on_page(_page(POSTING), url, "Syria")[0]

    assert first.external_id == second.external_id
    assert first.external_id.startswith("web:")


def test_graph_wrapped_markup_is_flattened():
    page = _page({"@context": "https://schema.org", "@graph": [{"@type": "WebSite"}, POSTING]})
    assert len(_postings_on_page(page, "https://board.example/jobs/3", "Syria")) == 1


def test_a_page_with_no_job_markup_yields_nothing():
    page = '<html><script type="application/ld+json">{"@type":"FAQPage"}</script></html>'
    assert _postings_on_page(page, "https://board.example/faq", "Syria") == []


def test_malformed_json_ld_is_skipped_rather_than_raising():
    page = '<html><script type="application/ld+json">{not json at all</script></html>'
    assert _postings_on_page(page, "https://board.example/x", "Syria") == []


def test_country_matching_accepts_iso_codes_and_names():
    assert _matches_country("SY", "Syria")
    assert _matches_country("Turkey", "Turkey")
    assert _matches_country("Istanbul, TR", "Turkey")
    assert not _matches_country("DE", "Syria")
    # Unknown location is allowed through - small boards often omit it.
    assert _matches_country(None, "Syria")


def test_a_posting_from_the_wrong_country_is_dropped():
    obj = dict(POSTING)
    obj["jobLocation"] = {"address": {"addressCountry": "DE"}}
    assert _listing_from_jsonld(obj, "https://board.example/j", "Syria", "") is None


def test_index_links_are_filtered_to_plausible_postings():
    html = """
      <a href="/jobs/engineer/123">one</a>
      <a href="/jobs?category=it">a filter, not a posting</a>
      <a href="/jobs/search">a search page</a>
      <a href="https://other-site.example/jobs/9">off-site</a>
      <a href="/about">not a job</a>
    """
    links = _same_site_job_links(html, "https://board.example/jobs")

    assert links == ["https://board.example/jobs/engineer/123"]


def test_the_boards_own_support_address_is_not_used_as_the_employer_email():
    """Real bug: a Saudi board's support address was attached to six
    unrelated companies, which would have mailed six applications to that
    board's help desk."""
    obj = dict(POSTING, description="قدم عبر الموقع")
    page = _page(obj).replace("<body>x</body>", "<body>support@careers-ksa.com</body>")

    job = _postings_on_page(page, "https://www.careers-ksa.com/jobs/7", "Syria")[0]

    assert job.apply_target is None
    assert job.apply_method == ApplyMethod.FORM


def test_an_employer_address_on_a_board_page_is_still_accepted():
    obj = dict(POSTING, description="قدم عبر الموقع")
    page = _page(obj).replace("<body>x</body>", "<body>hr@some-employer.com</body>")

    job = _postings_on_page(page, "https://www.careers-ksa.com/jobs/7", "Syria")[0]

    assert job.apply_target == "hr@some-employer.com"


def test_placeholder_addresses_are_not_treated_as_contacts():
    obj = dict(POSTING, description="Send your CV to name@company.com")
    job = _postings_on_page(_page(obj), "https://board.example/jobs/9", "Syria")[0]

    assert job.apply_target is None


def test_a_job_word_in_the_hostname_does_not_make_every_link_a_posting():
    """Real bug: on career.now the host itself contains "career", so
    matching against the whole URL made stylesheets look like postings."""
    html = """
      <a href="/assets/index-BqUxTBnb.css">stylesheet</a>
      <a href="/">home</a>
      <a href="/companies">companies</a>
      <a href="/jobs/backend-developer/42">an actual posting</a>
    """
    links = _same_site_job_links(html, "https://career.now/jobs/software-engineer/turkey")

    assert links == ["https://career.now/jobs/backend-developer/42"]


def test_search_crawls_one_level_when_the_result_is_an_index_page():
    index_html = '<a href="/jobs/eng/1">a posting</a>'

    with patch("jobpilot.connectors.websearch._bing_search", return_value=["https://board.example/jobs"]):
        with patch(
            "jobpilot.connectors.websearch.fetch_page",
            side_effect=[index_html, _page(POSTING)],
        ) as mock_fetch:
            jobs = WebSearchConnector().search(["مهندس برمجيات"], "Syria", limit=10)

    assert [j.title for j in jobs] == ["مهندس برمجيات"]
    assert mock_fetch.call_count == 2


def test_search_does_not_crawl_when_the_result_is_already_a_posting():
    with patch("jobpilot.connectors.websearch._bing_search", return_value=["https://board.example/jobs/1"]):
        with patch("jobpilot.connectors.websearch.fetch_page", return_value=_page(POSTING)) as mock_fetch:
            jobs = WebSearchConnector().search(["مهندس برمجيات"], "Syria", limit=10)

    assert len(jobs) == 1
    mock_fetch.assert_called_once()


def test_search_survives_a_failing_search_engine():
    with patch("jobpilot.connectors.websearch._bing_search", side_effect=RuntimeError("engine down")):
        assert WebSearchConnector().search(["anything"], "Syria") == []

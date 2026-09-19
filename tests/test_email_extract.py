from unittest.mock import patch

from jobpilot.core.email_extract import _decode_bing_redirect, find_contact_email, search_company_email


def test_finds_a_plain_email():
    assert find_contact_email("Contact us at jobs@company.com for details.") == "jobs@company.com"


def test_strips_trailing_sentence_period():
    text = "Please send your CV to careers@company.com. We look forward to it."
    assert find_contact_email(text) == "careers@company.com"


def test_skips_noreply_and_platform_addresses():
    text = "Sent from noreply@bayt.com. Real contact: hiring@acme.com"
    assert find_contact_email(text) == "hiring@acme.com"


def test_returns_none_when_no_email_present():
    assert find_contact_email("Apply through our website, no email listed.") is None


def test_decode_bing_redirect_unwraps_real_url():
    href = (
        "https://www.bing.com/ck/a?!&&p=abc"
        "&u=a1aHR0cHM6Ly93d3cuZ29vZGpvYmdhbWVzLmNvbS8&ntb=1"
    )
    assert _decode_bing_redirect(href) == "https://www.goodjobgames.com/"


def test_decode_bing_redirect_passes_through_non_bing_url():
    assert _decode_bing_redirect("https://example.com/page") == "https://example.com/page"


def test_search_company_email_skips_generic_placeholder_names():
    with patch("jobpilot.core.email_extract._bing_search") as mock_search:
        result = search_company_email("Confidential Company")
    assert result is None
    mock_search.assert_not_called()


def test_search_company_email_checks_search_results_in_order():
    with patch("jobpilot.core.email_extract._bing_search", return_value=["https://a.example", "https://b.example"]):
        with patch(
            "jobpilot.core.email_extract.find_contact_email_on_page",
            side_effect=[None, "hiring@company.com"],
        ) as mock_fetch:
            result = search_company_email("Acme Corp")
    assert result == "hiring@company.com"
    assert mock_fetch.call_count == 2

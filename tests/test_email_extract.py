from jobpilot.core.email_extract import find_contact_email


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

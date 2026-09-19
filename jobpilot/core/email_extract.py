"""Best-effort extraction of a contact email from a job posting page.

This is deliberately simple (a regex over the page text, skipping obvious
noise addresses) rather than a second AI call or a search-engine lookup -
per-job auto-apply here means "find an email and send to it", not a deep
research pipeline.
"""

import re

import requests

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Addresses/domains that show up on job pages but are never a real
# application contact (tracking pixels, platform no-reply addresses, etc.)
_NOISE = ("noreply", "no-reply", "donotreply", "sentry.io", "wixpress.com", "example.com")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# A handful of listing sites (Bayt included) sit behind Cloudflare's
# bot-challenge middleware, which a plain HTTP client can never pass -
# it needs actual JS execution. We try the cheap path first and only pay
# for a headless browser when the cheap path is clearly challenge-walled.
_CHALLENGE_MARKERS = ("Just a moment", "cf-browser-verification", "challenges.cloudflare.com")


def find_contact_email(text: str) -> str | None:
    for candidate in EMAIL_RE.findall(text):
        # The domain character class allows '.', so a sentence-ending
        # period right after the address (".com.") gets captured too -
        # strip it rather than send to an address that can't exist.
        candidate = candidate.rstrip(".")
        lowered = candidate.lower()
        if any(noise in lowered for noise in _NOISE):
            continue
        return candidate
    return None


def _looks_challenge_walled(status_code: int, text: str) -> bool:
    if status_code == 403:
        return True
    return any(marker in text for marker in _CHALLENGE_MARKERS)


def _fetch_with_browser(url: str, timeout: float) -> str | None:
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def find_contact_email_on_page(url: str, timeout: float = 15.0) -> str | None:
    text = None
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if not _looks_challenge_walled(response.status_code, response.text):
            response.raise_for_status()
            text = response.text
    except requests.RequestException:
        text = None

    if text is None:
        text = _fetch_with_browser(url, timeout)

    return find_contact_email(text) if text else None

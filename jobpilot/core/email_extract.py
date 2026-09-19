"""Best-effort extraction of a contact email from a job posting page, with
a web-search fallback (`search_company_email`) for when the listing itself
doesn't expose one.
"""

import base64
import re
from urllib.parse import parse_qs, quote, urlparse

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


_GENERIC_COMPANY_NAMES = {"confidential company", "unknown", ""}


def _decode_bing_redirect(href: str) -> str | None:
    """Bing wraps every organic result in a `bing.com/ck/a?...&u=a1<b64>`
    tracking redirect - unwrap it to the real target URL rather than
    fetching through Bing's own click-tracking endpoint."""
    try:
        parsed = urlparse(href)
        if "bing.com" not in parsed.netloc or not parsed.path.startswith("/ck/a"):
            return href
        encoded = parse_qs(parsed.query).get("u", [None])[0]
        if not encoded or not encoded.startswith("a1"):
            return None
        b64 = encoded[2:]
        b64 += "=" * (-len(b64) % 4)
        return base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
    except Exception:
        return None


def _bing_search(query: str, max_results: int, timeout: float) -> list[str]:
    """Renders a Bing results page with headless Chromium (not a plain
    `requests` call - Bing's real organic results only show up once the
    page's JS runs). Tried DuckDuckGo first, but it now serves an actual
    visual CAPTCHA to automated requests, which this project will not
    attempt to solve or bypass under any circumstance; Bing did not
    present one in testing."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(
                f"https://www.bing.com/search?q={quote(query)}",
                timeout=int(timeout * 1000),
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(1500)
            hrefs = page.eval_on_selector_all("li.b_algo h2 a", "els => els.map(e => e.href)")
            browser.close()
    except Exception:
        return []

    urls = []
    for href in hrefs[:max_results]:
        real_url = _decode_bing_redirect(href)
        if real_url:
            urls.append(real_url)
    return urls


def search_company_email(company: str, max_results: int = 4, timeout: float = 20.0) -> str | None:
    """Last resort when a job listing itself has no email: search the web
    for the company's own contact/careers address and check the top
    results. Skipped for placeholder company names ("Confidential
    Company", etc.) where a search would be meaningless."""
    if company.strip().lower() in _GENERIC_COMPANY_NAMES:
        return None

    for url in _bing_search(f'"{company}" careers contact email', max_results, timeout):
        email = find_contact_email_on_page(url, timeout=timeout)
        if email:
            return email
    return None

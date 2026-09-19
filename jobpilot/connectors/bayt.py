"""Bayt.com connector.

Bayt's job-search results are public pages - no login, no account, and
`robots.txt` explicitly permits a generic user agent to fetch
`/en/<country>/jobs/<role>-jobs/`. But the site sits behind Cloudflare's
bot-challenge middleware, which returns a "Just a moment..." interstitial
(HTTP 403) to a plain `requests` call - it needs a real JS-capable
browser to pass, not because Bayt itself objects to automation, but
because of Cloudflare in front of it. So this connector drives headless
Chromium via Playwright purely to *render the page*: no credentials, no
session, nothing that touches an account.

Selectors were captured from a live page on 2026-09-19; Bayt can and does
change its markup, so if `search()` starts returning nothing, re-check the
selectors below first. PRs welcome.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from jobpilot.connectors.base import JobConnector
from jobpilot.core.models import ApplyMethod, JobListing

BASE_URL = "https://www.bayt.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

COUNTRY_SLUGS = {
    "syria": "syria",
    "turkey": "turkey",
    "türkiye": "turkey",
    "saudi arabia": "saudi-arabia",
    "ksa": "saudi-arabia",
}


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class BaytConnector(JobConnector):
    name = "bayt"

    def __init__(self, page_load_delay_seconds: float = 2.0) -> None:
        self.page_load_delay_seconds = page_load_delay_seconds

    def _country_slug(self, country: str) -> str:
        return COUNTRY_SLUGS.get(country.strip().lower(), _slugify(country))

    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        country_slug = self._country_slug(country)
        listings: list[JobListing] = []
        seen_ids: set[str] = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            try:
                for keyword in keywords:
                    role_slug = _slugify(keyword)
                    url = f"{BASE_URL}/en/{country_slug}/jobs/{role_slug}-jobs/"
                    try:
                        page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        page.wait_for_timeout(int(self.page_load_delay_seconds * 1000))
                        html = page.content()
                    except Exception:
                        continue
                    for job in self._parse(html, country):
                        if job.external_id not in seen_ids:
                            seen_ids.add(job.external_id)
                            listings.append(job)
                    if len(listings) >= limit:
                        break
            finally:
                browser.close()
        return listings[:limit]

    def _parse(self, html: str, country: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[JobListing] = []
        for card in soup.select("li[data-js-job]"):
            job_id = card.get("data-job-id")
            title_link = card.select_one('h2 a[data-js-aid="jobID"]')
            if not job_id or not title_link:
                continue
            company_el = card.select_one("div.job-company-location-wrapper > div")
            desc_el = card.select_one(".jb-descr")
            description = ""
            if desc_el:
                description = desc_el.get_text(" ", strip=True)
                description = re.sub(r"^Summary:\s*", "", description)
            job_url = urljoin(BASE_URL, title_link["href"])
            results.append(
                JobListing(
                    source=self.name,
                    external_id=f"bayt:{job_id}",
                    title=title_link.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "Unknown",
                    country=country,
                    url=job_url,
                    description=description,
                    apply_method=ApplyMethod.FORM,
                    apply_target=job_url,
                )
            )
        return results

"""Bayt.com connector.

Bayt's job-search results are public pages, and its robots.txt allows a
generic user agent to fetch `/en/<country>/jobs/<role>-jobs/` (it only
blocks LinkedInBot/IndeedBot outright, and a handful of unrelated paths).
So this connector just does a polite, identified HTTP GET + parse - no
login, no browser automation, no bot-detection concerns.

Selectors were captured from a live page on 2026-09-19; Bayt can and does
change its markup, so if `search()` starts returning nothing, re-check the
selectors below first. PRs welcome.
"""

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from jobpilot.connectors.base import JobConnector
from jobpilot.core.models import Application, ApplyMethod, JobListing

BASE_URL = "https://www.bayt.com"
USER_AGENT = "JobPilotBot/0.1 (personal job-search assistant; github.com/<you>/jobpilot)"

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
    tos_risk = False

    def __init__(self, request_delay_seconds: float = 2.0) -> None:
        self.request_delay_seconds = request_delay_seconds
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _country_slug(self, country: str) -> str:
        return COUNTRY_SLUGS.get(country.strip().lower(), _slugify(country))

    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        country_slug = self._country_slug(country)
        listings: list[JobListing] = []
        seen_ids: set[str] = set()
        for keyword in keywords:
            role_slug = _slugify(keyword)
            url = f"{BASE_URL}/en/{country_slug}/jobs/{role_slug}-jobs/"
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
            except requests.RequestException:
                continue
            for job in self._parse(response.text, country):
                if job.external_id not in seen_ids:
                    seen_ids.add(job.external_id)
                    listings.append(job)
            time.sleep(self.request_delay_seconds)
            if len(listings) >= limit:
                break
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

    def apply(self, job: JobListing, application: Application) -> bool:
        raise NotImplementedError(
            "Bayt applications require a logged-in session. JobPilot surfaces "
            "these listings for the matching/email agents but does not "
            "auto-submit through Bayt's own apply form yet - contributions "
            "welcome (see CONTRIBUTING.md)."
        )

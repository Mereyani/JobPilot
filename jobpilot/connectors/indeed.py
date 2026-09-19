"""Indeed connector - OFF by default, same reasoning as linkedin.py.

Indeed's ToS also restricts automated scraping/applying, and its former
public Publisher API for search has been shut down for new users. This
connector drives a plain, visible browser session (no anti-detection
tricks, no CAPTCHA solving) and may get rate-limited or blocked by Indeed.

Enable via ENABLE_INDEED_CONNECTOR=true in .env after reading the
ToS-risk note in README.md.
"""

from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from jobpilot.config import settings
from jobpilot.connectors.base import JobConnector
from jobpilot.core.models import Application, ApplyMethod, JobListing

SEARCH_URL = "https://www.indeed.com/jobs?q={keywords}&l={location}"


class IndeedConnector(JobConnector):
    name = "indeed"
    tos_risk = True

    def __init__(self) -> None:
        if not settings.enable_indeed_connector:
            raise RuntimeError(
                "IndeedConnector is disabled. Set ENABLE_INDEED_CONNECTOR=true "
                "in .env after reading the ToS-risk note in README.md."
            )

    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        listings: list[JobListing] = []
        query = " ".join(keywords)
        url = SEARCH_URL.format(keywords=quote_plus(query), location=quote_plus(country))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_selector("div.job_seen_beacon", timeout=15000)

            cards = page.query_selector_all("div.job_seen_beacon")
            for card in cards[:limit]:
                title_el = card.query_selector("h2.jobTitle span")
                company_el = card.query_selector('span[data-testid="company-name"]')
                link_el = card.query_selector("h2.jobTitle a")
                if not title_el or not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                job_id = href.split("jk=")[-1].split("&")[0] if "jk=" in href else href
                listings.append(
                    JobListing(
                        source=self.name,
                        external_id=f"indeed:{job_id}",
                        title=title_el.inner_text().strip(),
                        company=company_el.inner_text().strip() if company_el else "Unknown",
                        country=country,
                        url=f"https://www.indeed.com{href}" if href.startswith("/") else href,
                        apply_method=ApplyMethod.FORM,
                        apply_target=f"https://www.indeed.com{href}" if href.startswith("/") else href,
                    )
                )
            browser.close()
        return listings

    def apply(self, job: JobListing, application: Application) -> bool:
        raise NotImplementedError(
            "Auto-apply on Indeed is intentionally not implemented. "
            "Use this connector for discovery only, or contribute a "
            "reviewed implementation."
        )

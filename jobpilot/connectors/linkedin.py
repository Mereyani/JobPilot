"""LinkedIn connector - OFF by default, and for good reason.

LinkedIn's Terms of Service prohibit automated use of the site, including
scripted search and "Easy Apply" submission. Running this connector risks
your personal LinkedIn account being restricted or banned. JobPilot will
not try to get around LinkedIn's bot detection (no CAPTCHA solving, no
fingerprint spoofing) - it drives a normal, visible browser session and
accepts that it may get blocked.

Enable at your own risk via ENABLE_LINKEDIN_CONNECTOR=true and
LINKEDIN_EMAIL/LINKEDIN_PASSWORD in .env. Until then this connector is
inert - the search/orchestrator layers skip it entirely.

Selectors below are a best-effort starting point (LinkedIn's DOM changes
often and is not something we actively track); expect to have to fix them.
"""

from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from jobpilot.config import settings
from jobpilot.connectors.base import JobConnector
from jobpilot.core.models import Application, ApplyMethod, JobListing

SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords={keywords}&location={location}"


class LinkedInConnector(JobConnector):
    name = "linkedin"
    tos_risk = True

    def __init__(self) -> None:
        if not settings.enable_linkedin_connector:
            raise RuntimeError(
                "LinkedInConnector is disabled. Set ENABLE_LINKEDIN_CONNECTOR=true "
                "in .env after reading the ToS-risk note in README.md."
            )
        if not settings.linkedin_email or not settings.linkedin_password:
            raise RuntimeError("LINKEDIN_EMAIL / LINKEDIN_PASSWORD are not set.")

    def _login(self, page) -> None:
        page.goto("https://www.linkedin.com/login")
        page.fill("#username", settings.linkedin_email)
        page.fill("#password", settings.linkedin_password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        listings: list[JobListing] = []
        query = " ".join(keywords)
        url = SEARCH_URL.format(keywords=quote_plus(query), location=quote_plus(country))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            self._login(page)
            page.goto(url)
            page.wait_for_selector("ul.jobs-search__results-list", timeout=15000)

            cards = page.query_selector_all("ul.jobs-search__results-list li")
            for card in cards[:limit]:
                title_el = card.query_selector("h3")
                company_el = card.query_selector("h4")
                link_el = card.query_selector("a")
                if not title_el or not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                job_id = href.split("?")[0].rstrip("/").split("-")[-1]
                listings.append(
                    JobListing(
                        source=self.name,
                        external_id=f"linkedin:{job_id}",
                        title=title_el.inner_text().strip(),
                        company=company_el.inner_text().strip() if company_el else "Unknown",
                        country=country,
                        url=href.split("?")[0],
                        apply_method=ApplyMethod.FORM,
                        apply_target=href.split("?")[0],
                    )
                )
            browser.close()
        return listings

    def apply(self, job: JobListing, application: Application) -> bool:
        # Deliberately not implemented: driving LinkedIn's "Easy Apply" modal
        # end-to-end (including account-specific screening questions) is
        # exactly the kind of high-blast-radius automation this project
        # wants a human to review before it exists. Wire this up yourself
        # if you accept the account-suspension risk - see README.
        raise NotImplementedError(
            "Auto-apply on LinkedIn is intentionally not implemented. "
            "Use this connector for discovery only, or contribute a "
            "reviewed implementation."
        )

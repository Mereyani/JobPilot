"""A job source that isn't a job site.

Every other connector is bound to one platform. This one searches the open
web and reads whatever it lands on, which is what actually reaches the
small local boards where the target countries' jobs live - and, unlike the
big platforms, those postings tend to print a contact email right in the
text.

How it finds structure in arbitrary pages: Google requires a job page to
carry schema.org `JobPosting` data in a <script type="application/ld+json">
tag before it will index it as a job, so essentially any page that wants to
be found as a job posting publishes one. That markup is the same shape on a
Syrian board, a Turkish careers page and a company's own site, so parsing it
yields structured listings from sites this code has never seen.

Two shapes get handled:
- the search result *is* a posting -> parse its JobPosting markup directly
- the result is a board's index page -> follow same-site links that look
  like postings and parse those (one level down only, strictly bounded)

Verified against real pages while building this: jobsyria.net publishes
complete JobPosting markup (title, description, hiringOrganization,
addressCountry) on its individual listings.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from jobpilot.connectors.base import JobConnector
from jobpilot.core.email_extract import _bing_search, fetch_page, find_contact_email
from jobpilot.core.models import ApplyMethod, JobListing

logger = logging.getLogger(__name__)

# Deliberately small. Every number here costs a page fetch, and a search
# stage that takes twenty minutes is one the user will stop running.
MAX_QUERIES = 4
RESULTS_PER_QUERY = 12
MAX_CRAWL_PER_SITE = 8
FETCH_TIMEOUT = 20.0

# The big aggregators render their listings with JS behind a login/bot wall,
# so they return nothing useful here - but they outrank everything else and
# would eat the whole fetch budget. They're excluded in the query itself
# (so the search engine hands back smaller sites instead of them) and
# re-checked on the results as a backstop, since the operator is a hint
# rather than a guarantee.
_EXCLUDED_HOSTS = (
    "linkedin.com",
    "indeed.com",
    "jooble.org",
    "glassdoor.com",
    "ziprecruiter.com",
    "monster.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "wikipedia.org",
    "pinterest.com",
)
# Note: tried putting "-site:linkedin.com ..." in the query itself first.
# Bing ignored it - the excluded sites came back anyway - so the filtering
# is done here on the results, and RESULTS_PER_QUERY is set high enough
# that the survivors are still worth crawling.

# Static assets share the same paths as content and must never be fetched
# as if they were postings.
_ASSET_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".pdf", ".zip")


def _is_excluded(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == bad or host.endswith("." + bad) for bad in _EXCLUDED_HOSTS)

_LD_JSON_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

# URL shapes that tend to be an individual posting rather than a category
# or a search page. Arabic included - local boards use it in their paths.
_JOB_PATH_RE = re.compile(r"/(job|jobs|vacanc|career|position|wazifa|وظيفة|وظائف)", re.I)
# ...and shapes that are definitely not a single posting.
_INDEX_PATH_RE = re.compile(r"(\?|/(search|category|categories|tag|tags|page|list|alerts)\b)", re.I)

# ISO codes for the countries this gets pointed at, so a posting tagged
# "SY" still matches a search for "Syria".
_COUNTRY_CODES = {
    "syria": "sy",
    "turkey": "tr",
    "türkiye": "tr",
    "saudi arabia": "sa",
    "egypt": "eg",
    "jordan": "jo",
    "united arab emirates": "ae",
    "uae": "ae",
    "qatar": "qa",
    "kuwait": "kw",
    "lebanon": "lb",
    "germany": "de",
}


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", value or "")).strip()


def _iter_jsonld_objects(html: str):
    """Yield every JSON-LD object on the page, flattening the @graph and
    top-level-array forms sites use interchangeably."""
    for blob in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(blob.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item:
                    stack.append(item["@graph"])
                yield item


def _is_job_posting(obj: dict) -> bool:
    node_type = obj.get("@type")
    if isinstance(node_type, list):
        return "JobPosting" in node_type
    return node_type == "JobPosting"


def _text_of(value) -> str:
    """schema.org fields are polymorphic - a name can be a string, an
    object with a `name`, or a list of either."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _text_of(value.get("name") or value.get("@value") or "")
    if isinstance(value, list):
        return next((t for t in (_text_of(v) for v in value) if t), "")
    return ""


def _location_of(obj: dict) -> tuple[str | None, str | None]:
    """Return (human-readable location, country string or ISO code)."""
    place = obj.get("jobLocation")
    if isinstance(place, list):
        place = next((p for p in place if isinstance(p, dict)), None)
    if not isinstance(place, dict):
        return None, None
    address = place.get("address")
    if isinstance(address, list):
        address = next((a for a in address if isinstance(a, dict)), None)
    if not isinstance(address, dict):
        return _text_of(place) or None, None
    country = _text_of(address.get("addressCountry")) or None
    parts = [
        _text_of(address.get("addressLocality")),
        _text_of(address.get("addressRegion")),
        country or "",
    ]
    return ", ".join(p for p in parts if p) or None, country


def _matches_country(found: str | None, wanted: str) -> bool:
    """Keep a posting only if it plausibly belongs to the country searched
    for. An unknown location is allowed through - plenty of small boards
    omit the field, and the matching agent reads the description anyway."""
    if not found:
        return True
    found_l = found.strip().lower()
    wanted_l = wanted.strip().lower()
    if wanted_l in found_l or found_l in wanted_l:
        return True
    code = _COUNTRY_CODES.get(wanted_l)
    # Match the ISO code as a whole token, so "Istanbul, TR" counts as
    # Turkey while a substring hit inside another word does not.
    tokens = set(re.split(r"[^a-z0-9]+", found_l))
    return bool(code and code in tokens)


def _parse_date(value) -> datetime | None:
    raw = _text_of(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _base_domain(host: str) -> str:
    """"www.careers-ksa.com" -> "careers-ksa.com". Good enough to tell
    "the job board" apart from "an employer"."""
    host = host.lower().strip().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) > 2 else host


def _site_domain(url: str) -> str:
    return _base_domain(urlparse(url).netloc)


def _employer_email(description: str, page_html: str, url: str) -> str | None:
    """The employer's address, not the job board's.

    The posting text is trusted directly - "send your CV to ..." is written
    by the employer. The surrounding page is only a fallback, and anything
    on the board's own domain is rejected there: a live run picked up
    support@careers-ksa.com and attached it to six unrelated companies,
    which would have sent six applications to that board's help desk.
    """
    from_description = find_contact_email(description)
    if from_description:
        return from_description

    from_page = find_contact_email(page_html)
    if from_page and _base_domain(from_page.rsplit("@", 1)[-1]) == _site_domain(url):
        return None
    return from_page


def _listing_from_jsonld(obj: dict, url: str, country: str, page_html: str) -> JobListing | None:
    title = _strip_html(_text_of(obj.get("title")))
    if not title:
        return None

    location, found_country = _location_of(obj)
    if not _matches_country(found_country, country):
        return None

    description = _strip_html(_text_of(obj.get("description")))
    company = _strip_html(_text_of(obj.get("hiringOrganization"))) or "Unknown"

    email = _employer_email(description, page_html, url)

    return JobListing(
        source="web",
        external_id="web:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16],
        title=title,
        company=company,
        location=location,
        country=country,
        url=url,
        description=description[:8000],
        apply_method=ApplyMethod.EMAIL if email else ApplyMethod.FORM,
        apply_target=email,
        posted_at=_parse_date(obj.get("datePosted")),
    )


def _postings_on_page(html: str, url: str, country: str) -> list[JobListing]:
    listings = []
    for obj in _iter_jsonld_objects(html):
        if not _is_job_posting(obj):
            continue
        listing = _listing_from_jsonld(obj, url, country, html)
        if listing:
            listings.append(listing)
    return listings


def _same_site_job_links(html: str, base_url: str) -> list[str]:
    """Links on an index page that look like individual postings."""
    host = urlparse(base_url).netloc
    out: list[str] = []
    for href in _HREF_RE.findall(html):
        full = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(full)
        if parsed.netloc != host or parsed.scheme not in ("http", "https"):
            continue
        if parsed.path.lower().endswith(_ASSET_SUFFIXES):
            continue
        # Match the *path*, never the whole URL: a host like "career.now"
        # contains "career", which made every link on that site - including
        # its stylesheets - look like a job posting.
        if not _JOB_PATH_RE.search(parsed.path) or _INDEX_PATH_RE.search(full):
            continue
        if full.rstrip("/") == base_url.rstrip("/") or full in out:
            continue
        out.append(full)
    return out


class WebSearchConnector(JobConnector):
    """Searches the open web rather than any one job platform."""

    name = "web"

    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        found: dict[str, JobListing] = {}
        visited: set[str] = set()

        for keyword in keywords[:MAX_QUERIES]:
            if len(found) >= limit:
                break
            try:
                results = _bing_search(f"{keyword} {country}", RESULTS_PER_QUERY, FETCH_TIMEOUT)
            except Exception:
                logger.exception("Web search failed for %r in %s", keyword, country)
                continue

            for url in results:
                if len(found) >= limit or url in visited or _is_excluded(url):
                    continue
                visited.add(url)
                html = fetch_page(url, timeout=FETCH_TIMEOUT)
                if not html:
                    continue

                postings = _postings_on_page(html, url, country)
                if postings:
                    for listing in postings:
                        found.setdefault(listing.external_id, listing)
                    continue

                # No markup here - treat it as a board index and look one
                # level down for the actual postings.
                for link in _same_site_job_links(html, url)[:MAX_CRAWL_PER_SITE]:
                    if len(found) >= limit or link in visited:
                        continue
                    visited.add(link)
                    sub_html = fetch_page(link, timeout=FETCH_TIMEOUT)
                    if not sub_html:
                        continue
                    for listing in _postings_on_page(sub_html, link, country):
                        found.setdefault(listing.external_id, listing)

        return list(found.values())[:limit]

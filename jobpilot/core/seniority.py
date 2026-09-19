"""A deterministic "is this job above the candidate's level?" check.

The matching agent already asks the LLM to treat seniority as a hard gate,
but a small local model does not reliably honour that instruction - a real
run scored "Senior Software Engineer (Oracle)" at 80 for a new-graduate
profile. Prompt wording cannot fix that reliably, so the rule lives here
instead: plain string matching, same answer every time, no model involved.

Titles are matched in English and Arabic, since postings in the target
countries come in both.
"""

import re

# English seniority markers. Every one of these implies more experience
# than a junior/new-grad candidate can claim.
_EN_PATTERNS = [
    r"\bsenior\b",
    r"\bsr\.?\b",
    r"\bstaff\b",
    r"\bprincipal\b",
    r"\bexpert\b",
    r"\barchitect\b",
    r"\bdirector\b",
    r"\bchief\b",
    r"\bhead\s+of\b",
    r"\bvp\b",
    r"\bvice\s+president\b",
    r"\bmanager\b",
    r"\bsupervisor\b",
    # "Lead" alone means seniority, but "Lead Generation" is an entry-level
    # sales role - matching it would reject a job the candidate could do.
    r"\blead\b(?!\s+generation)",
]

# Arabic seniority markers. "أول" (senior/first) and "كبير" (chief/senior)
# are the usual title modifiers; the rest are outright management titles.
_AR_PATTERNS = [
    r"كبير",
    r"أول\b",
    r"اول\b",
    r"رئيس",
    r"مدير",
    r"مديرة",
    r"قائد",
    r"مشرف",
    r"خبير",
    r"استشاري",
]

_SENIOR_RE = re.compile("|".join(_EN_PATTERNS + _AR_PATTERNS), re.IGNORECASE)

# Years-of-experience demands: anything asking for this many or more is
# past what a recent graduate can honestly claim.
_MIN_YEARS_CONSIDERED_SENIOR = 4
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:years|yrs|year|سنوات|سنة)",
    re.IGNORECASE,
)


def title_is_senior(title: str) -> bool:
    """True if the job *title* alone marks the role as above junior level."""
    return bool(_SENIOR_RE.search(title or ""))


def required_years(text: str) -> int | None:
    """Largest "N years of experience" figure mentioned, if any."""
    years = [int(m) for m in _YEARS_RE.findall(text or "")]
    plausible = [y for y in years if 0 < y <= 40]
    return max(plausible) if plausible else None


def too_senior(title: str, description: str = "") -> str | None:
    """Return a short machine-readable reason if this job is out of a junior
    candidate's range, or None if it passes.

    The reason is stored on the job so the dashboard can explain *why*
    something scored zero instead of just showing a zero.
    """
    if title_is_senior(title):
        return "senior_title"
    years = required_years(description)
    if years is not None and years >= _MIN_YEARS_CONSIDERED_SENIOR:
        return f"requires_{years}_years"
    return None

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ApplyMethod(str, Enum):
    EMAIL = "email"
    FORM = "form"
    ATS_API = "ats_api"
    UNKNOWN = "unknown"


class CandidateProfile(BaseModel):
    """Structured resume data, extracted by the profile agent."""

    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    languages: dict[str, str] = Field(default_factory=dict)
    education: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)


class JobListing(BaseModel):
    source: str
    external_id: str
    title: str
    company: str
    location: str | None = None
    country: str | None = None
    url: str
    description: str = ""
    apply_method: ApplyMethod = ApplyMethod.UNKNOWN
    apply_target: str | None = None  # email address or form URL, depending on apply_method
    posted_at: datetime | None = None
    match_score: int | None = None
    match_reason: str | None = None

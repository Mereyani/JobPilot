"""Parses a resume PDF into a structured CandidateProfile."""

import pdfplumber

from jobpilot.core.database import ProfileRecord, get_session
from jobpilot.core.llm import ask_json
from jobpilot.core.models import CandidateProfile

SYSTEM_PROMPT = """You extract structured candidate data from resume text.
Return a JSON object with exactly these keys:
name, email, phone, location, headline, summary,
skills (array of strings), languages (object of language -> proficiency),
education (array of strings, one per degree/entry),
experience (array of strings, one per role, "Title at Company (dates): summary"),
links (object of label -> url, e.g. {"linkedin": "..."}).
Use null for unknown scalar fields and empty arrays/objects for unknown lists/maps.
Do not invent information that is not present in the text."""


def extract_text(pdf_path: str) -> str:
    chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def parse_resume(pdf_path: str) -> CandidateProfile:
    text = extract_text(pdf_path)
    if not text.strip():
        raise ValueError(f"Could not extract any text from {pdf_path}")
    data = ask_json(SYSTEM_PROMPT, text)
    return CandidateProfile.model_validate(data)


def save_profile(profile: CandidateProfile) -> None:
    with get_session() as session:
        session.query(ProfileRecord).delete()
        session.add(ProfileRecord(data=profile.model_dump()))
        session.commit()


def load_profile() -> CandidateProfile | None:
    with get_session() as session:
        record = session.query(ProfileRecord).order_by(ProfileRecord.id.desc()).first()
        return CandidateProfile.model_validate(record.data) if record else None


def run(pdf_path: str) -> CandidateProfile:
    profile = parse_resume(pdf_path)
    save_profile(profile)
    return profile

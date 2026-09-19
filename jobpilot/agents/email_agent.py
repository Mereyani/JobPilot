"""Sends application emails, and polls the inbox for replies to classify
and (optionally) auto-respond to.

Uses plain IMAP/SMTP so it works with any provider, not just Gmail/Outlook.
"""

import email
import imaplib
import logging
import re
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText

from jobpilot.core.database import ApplicationRecord, EmailRecord, get_session
from jobpilot.core.llm import ask_json, ask_text
from jobpilot.config import settings

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"\[JobPilot:([^\]]+)\]")

CLASSIFY_SYSTEM_PROMPT = """You classify an email reply to a job application.
Return a JSON object with exactly one key, "category", whose value is one of:
"interview_invite", "rejection", "request_info", "other"."""

REPLY_SYSTEM_PROMPT = """You draft a short, professional reply to a recruiter
email on behalf of a job applicant. Match the tone of the incoming email.
For interview invitations: confirm interest and ask the recruiter to propose
times. For requests for more information: answer using only the candidate
profile provided - never invent facts. For rejections: send a brief, polite
thank-you and note continued interest in future roles. Sign off with the
candidate's name. Output only the email body, no subject line."""


def build_subject(job_title: str, company: str, thread_key: str) -> str:
    return f"Application for {job_title} at {company} [JobPilot:{thread_key}]"


def send_email(to_address: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP is not configured - set SMTP_* in .env")
    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = settings.smtp_user
    message["To"] = to_address

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_user, [to_address], message.as_string())


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    return "".join(
        part.decode(enc or "utf-8", errors="ignore") if isinstance(part, bytes) else part
        for part, enc in parts
    )


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="ignore")
        return ""
    return msg.get_payload(decode=True).decode(errors="ignore")


def poll_inbox(limit: int = 20) -> int:
    """Fetch unseen inbound emails, classify them, correlate them to an
    application by the [JobPilot:<thread_key>] tag, and (if
    EMAIL_AUTO_SEND) draft + send a reply. Returns the number processed.
    """
    if not settings.imap_host:
        raise RuntimeError("IMAP is not configured - set IMAP_* in .env")

    processed = 0
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as imap:
        imap.login(settings.imap_user, settings.imap_password)
        imap.select("INBOX")
        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            return 0
        message_ids = data[0].split()[:limit]

        with get_session() as session:
            for msg_id in message_ids:
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode(msg.get("Subject"))
                sender = _decode(msg.get("From"))
                body = _extract_body(msg)

                match = TAG_RE.search(subject)
                thread_key = match.group(1) if match else None

                try:
                    category = ask_json(CLASSIFY_SYSTEM_PROMPT, f"Subject: {subject}\n\n{body}")["category"]
                except Exception:
                    logger.exception("Failed to classify email %s", subject)
                    category = "other"

                session.add(
                    EmailRecord(
                        application_thread_key=thread_key,
                        direction="inbound",
                        subject=subject,
                        body=body,
                        sender=sender,
                        category=category,
                    )
                )

                application = None
                if thread_key:
                    application = (
                        session.query(ApplicationRecord)
                        .filter_by(thread_key=thread_key)
                        .first()
                    )
                if application:
                    application.status = (
                        "interview" if category == "interview_invite" else application.status
                    )
                    application.status = "rejected" if category == "rejection" else application.status
                    if application.status not in ("interview", "rejected"):
                        application.status = "replied"

                if settings.email_auto_send and category != "other":
                    try:
                        reply_body = ask_text(REPLY_SYSTEM_PROMPT, f"Incoming email:\n{body}")
                        reply_to = email.utils.parseaddr(sender)[1]
                        send_email(reply_to, f"Re: {subject}", reply_body)
                        session.add(
                            EmailRecord(
                                application_thread_key=thread_key,
                                direction="outbound",
                                subject=f"Re: {subject}",
                                body=reply_body,
                                sender=settings.smtp_user,
                                category=category,
                            )
                        )
                    except Exception:
                        logger.exception("Failed to auto-reply to %s", sender)

                imap.store(msg_id, "+FLAGS", "\\Seen")
                processed += 1
            session.commit()
    return processed

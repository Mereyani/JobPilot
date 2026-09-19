from unittest.mock import MagicMock, patch

from jobpilot.agents import email_agent
from jobpilot.core.settings_store import RuntimeSettings


def _settings(**overrides) -> RuntimeSettings:
    base = RuntimeSettings(
        email_address="me@example.com",
        email_password="app-password",
        smtp_host="smtp.example.com",
        smtp_port=587,
    )
    return base.model_copy(update=overrides)


def test_send_email_without_attachment_is_plain_text():
    with patch("jobpilot.agents.email_agent.get_settings", return_value=_settings()):
        with patch("smtplib.SMTP") as smtp_cls:
            server = MagicMock()
            smtp_cls.return_value.__enter__.return_value = server

            email_agent.send_email("them@company.com", "Subject", "Body text")

            sent = server.sendmail.call_args.args[2]
            assert "Content-Type: text/plain" in sent
            assert "multipart" not in sent.lower()


def test_send_email_attaches_existing_file(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fake content")

    with patch("jobpilot.agents.email_agent.get_settings", return_value=_settings()):
        with patch("smtplib.SMTP") as smtp_cls:
            server = MagicMock()
            smtp_cls.return_value.__enter__.return_value = server

            email_agent.send_email("them@company.com", "Subject", "Body text", attachments=[str(resume)])

            sent = server.sendmail.call_args.args[2]
            assert "multipart" in sent.lower()
            assert "resume.pdf" in sent


def test_send_email_skips_missing_attachment_paths():
    with patch("jobpilot.agents.email_agent.get_settings", return_value=_settings()):
        with patch("smtplib.SMTP") as smtp_cls:
            server = MagicMock()
            smtp_cls.return_value.__enter__.return_value = server

            email_agent.send_email("them@company.com", "Subject", "Body text", attachments=["/no/such/file.pdf"])

            sent = server.sendmail.call_args.args[2]
            assert "multipart" not in sent.lower()

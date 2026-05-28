import os
import smtplib
import warnings
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from agents.researcher import VCDossier
from agents.scorer import Score
from models import RunResult


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _smtp_configured() -> bool:
    return all(_env(k) for k in ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "DIGEST_FROM", "DIGEST_TO"])


def _html_body(
    result: RunResult,
    top_vcs: list[tuple[VCDossier, Score]],
    duration_s: float,
    langfuse_url: str | None,
) -> str:
    run_date = _now_date()
    cost_line = ""
    errors_section = ""

    if result.errors:
        items = "".join(f"<li>{e}</li>" for e in result.errors)
        errors_section = f"<h3>Failures ({len(result.errors)})</h3><ul>{items}</ul>"

    top_section = ""
    if top_vcs:
        rows = "".join(
            f"<tr><td>{d.name}</td><td>{s.total}/25</td><td>{s.summary}</td></tr>"
            for d, s in top_vcs
        )
        top_section = (
            "<h3>Top new VCs</h3>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<tr><th>Name</th><th>Score</th><th>Rationale</th></tr>"
            f"{rows}</table>"
        )

    langfuse_line = (
        f"<p>Langfuse trace: <a href='{langfuse_url}'>{langfuse_url}</a></p>"
        if langfuse_url else ""
    )

    airtable_base = _env("AIRTABLE_BASE_ID")
    airtable_link = (
        f"<p>Review drafts in <a href='https://airtable.com/{airtable_base}'>Airtable</a>.</p>"
        if airtable_base else ""
    )

    return f"""
<html><body style="font-family: sans-serif; max-width: 700px;">
<h2>Gonzo Funnel — {run_date}</h2>
<table>
  <tr><td><b>VCs scouted</b></td><td>{result.vcs_scouted}</td></tr>
  <tr><td><b>VCs researched</b></td><td>{result.vcs_researched}</td></tr>
  <tr><td><b>Drafts ready</b></td><td>{result.drafts_written}</td></tr>
  <tr><td><b>Duration</b></td><td>{duration_s:.0f}s</td></tr>
  <tr><td><b>Status</b></td><td>{result.status}</td></tr>
</table>
{top_section}
{airtable_link}
{errors_section}
{langfuse_line}
</body></html>
"""


def send_digest(
    result: RunResult,
    top_vcs: list[tuple[VCDossier, Score]],
    duration_s: float,
    langfuse_url: str | None = None,
) -> None:
    if not _smtp_configured():
        warnings.warn("SMTP not configured — skipping digest email", stacklevel=2)
        return

    run_date = _now_date()
    subject = (
        f"[Gonzo Funnel] {run_date} — "
        f"{result.drafts_written} drafts ready, {result.vcs_scouted} new VCs"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _env("DIGEST_FROM")
    msg["To"] = _env("DIGEST_TO")
    msg.attach(MIMEText(_html_body(result, top_vcs, duration_s, langfuse_url), "html"))

    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT") or "587")
    user = _env("SMTP_USER")
    password = _env("SMTP_PASS")

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(msg["From"], msg["To"], msg.as_string())

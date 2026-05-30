import email
import email.header
import os
import warnings
from unittest.mock import MagicMock, patch

import pytest

from agents.researcher import VCDossier
from agents.scorer import Score, ScoreDimension
from notify.email import send_digest, _smtp_configured
from models import RunResult


def _make_result(**kwargs):
    defaults = dict(
        run_id="run_test",
        vcs_scouted=5,
        vcs_researched=5,
        drafts_written=3,
        errors=[],
    )
    defaults.update(kwargs)
    r = RunResult(**defaults)
    return r


def _make_dossier(name="Accel"):
    return VCDossier(
        name=name, url="https://accel.com", country="USA",
        thesis_summary="Deep tech.", stage_focus=["Seed"], ticket_size="$500K",
        partners=["Partner A"], sources=[],
    )


def _make_score(total=16):
    names = ["A", "B", "C", "D", "E"]
    per, rem = divmod(total, 5)
    dims = [ScoreDimension(name=names[i], score=per+(1 if i < rem else 0), rationale="r")
            for i in range(5)]
    return Score(dimensions=dims, total=total, go=total >= 17, summary="s")


def test_send_digest_skips_when_smtp_not_configured():
    with patch.dict(os.environ, {}, clear=True):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            send_digest(_make_result(), [], 30.0)
        assert any("SMTP not configured" in str(warning.message) for warning in w)


def test_send_digest_sends_when_configured():
    smtp_env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "user@example.com",
        "SMTP_PASS": "password",
        "DIGEST_FROM": "from@example.com",
        "DIGEST_TO": "to@example.com",
    }
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, smtp_env), \
         patch("smtplib.SMTP", return_value=mock_smtp):
        send_digest(
            _make_result(),
            [(_make_dossier(), _make_score())],
            42.0,
        )

    mock_smtp.sendmail.assert_called_once()


def test_smtp_configured_false_when_missing_vars():
    with patch.dict(os.environ, {}, clear=True):
        assert _smtp_configured() is False


def test_smtp_configured_true_when_all_set():
    smtp_env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USER": "user",
        "SMTP_PASS": "pass",
        "DIGEST_FROM": "from@example.com",
        "DIGEST_TO": "to@example.com",
    }
    with patch.dict(os.environ, smtp_env):
        assert _smtp_configured() is True


def test_subject_contains_run_date_and_counts():
    smtp_env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "user@example.com",
        "SMTP_PASS": "password",
        "DIGEST_FROM": "from@example.com",
        "DIGEST_TO": "to@example.com",
    }
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)
    captured = {}

    def capture_sendmail(from_, to_, msg):
        captured["msg"] = msg

    mock_smtp.sendmail.side_effect = capture_sendmail

    with patch.dict(os.environ, smtp_env), \
         patch("smtplib.SMTP", return_value=mock_smtp):
        send_digest(_make_result(drafts_written=3, vcs_scouted=5), [], 10.0)

    msg_obj = email.message_from_string(captured["msg"])
    subject_parts = email.header.decode_header(msg_obj["Subject"])
    subject = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in subject_parts
    )
    assert "3 drafts ready" in subject
    assert "5 new VCs" in subject

"""
Unit tests for mailer.py.

Run from project root:
    python -m pytest testing/test_mailer.py -v

Covers:
  - MAIL_DISABLED short-circuits to True without HTTP
  - Missing POSTMARK_SERVER_TOKEN -> False + error log
  - Missing EMAIL_FROM -> False + error log
  - Network error (RequestException) -> False
  - Non-200 response -> False
  - Non-JSON response -> False
  - Postmark ErrorCode != 0 -> False
  - Happy path: 200 + ErrorCode 0 -> True + correct payload sent

All HTTP is mocked via unittest.mock; no live Postmark requests fired.
"""
import json
import logging
import os
from unittest.mock import patch, MagicMock

import pytest
import requests

import mailer


@pytest.fixture(autouse=True)
def _capture_info(caplog):
    """[MAIL-DISABLED] and [EMAIL-SENT] are INFO-level; pytest's caplog
    defaults to WARNING. Bump it for every test so assertions on those
    tags actually see them."""
    caplog.set_level(logging.INFO, logger="mailer")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Clear all mailer-relevant env vars before each test so one test's
    state doesn't leak into another. Tests opt in to specific values via
    monkeypatch.setenv as needed."""
    for k in ("MAIL_DISABLED", "POSTMARK_SERVER_TOKEN", "EMAIL_FROM", "EMAIL_FROM_NAME"):
        monkeypatch.delenv(k, raising=False)


def test_mail_disabled_short_circuits(monkeypatch, caplog):
    monkeypatch.setenv("MAIL_DISABLED", "1")
    # Note: no Postmark token set — proves the short-circuit happens
    # BEFORE the token check.
    with patch.object(mailer.requests, "post") as mock_post:
        result = mailer.send_email("to@x.test", "subj", "<p>html</p>", "text")
    assert result is True
    mock_post.assert_not_called()
    assert "[MAIL-DISABLED]" in caplog.text


def test_missing_token_returns_false(caplog):
    # No MAIL_DISABLED, no POSTMARK_SERVER_TOKEN -> config error path
    with patch.object(mailer.requests, "post") as mock_post:
        result = mailer.send_email("to@x.test", "subj", "<p>html</p>", "text")
    assert result is False
    mock_post.assert_not_called()
    assert "[EMAIL-SEND-FAILED]" in caplog.text
    assert "POSTMARK_SERVER_TOKEN unset" in caplog.text


def test_missing_from_addr_returns_false(monkeypatch, caplog):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token")
    # EMAIL_FROM unset
    with patch.object(mailer.requests, "post") as mock_post:
        result = mailer.send_email("to@x.test", "subj", "<p>html</p>", "text")
    assert result is False
    mock_post.assert_not_called()
    assert "EMAIL_FROM unset" in caplog.text


def test_network_error_returns_false(monkeypatch, caplog):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token")
    monkeypatch.setenv("EMAIL_FROM", "from@x.test")
    with patch.object(
        mailer.requests, "post",
        side_effect=requests.ConnectionError("DNS failure"),
    ):
        result = mailer.send_email("to@x.test", "subj", "<p>html</p>", "text")
    assert result is False
    assert "[EMAIL-SEND-FAILED]" in caplog.text
    assert "network error" in caplog.text


def test_non_json_response_returns_false(monkeypatch, caplog):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token")
    monkeypatch.setenv("EMAIL_FROM", "from@x.test")
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_response.text = "<html>Bad Gateway</html>"
    mock_response.json.side_effect = ValueError("not json")
    with patch.object(mailer.requests, "post", return_value=mock_response):
        result = mailer.send_email("to@x.test", "subj", "<p>html</p>", "text")
    assert result is False
    assert "non-JSON response" in caplog.text


def test_postmark_error_code_returns_false(monkeypatch, caplog):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token")
    monkeypatch.setenv("EMAIL_FROM", "from@x.test")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ErrorCode": 422,
        "Message": "The 'From' address is not a valid Sender Signature.",
    }
    with patch.object(mailer.requests, "post", return_value=mock_response):
        result = mailer.send_email("to@x.test", "subj", "<p>html</p>", "text")
    assert result is False
    assert "ErrorCode=422" in caplog.text
    assert "not a valid Sender Signature" in caplog.text


def test_happy_path_returns_true_and_sends_correct_payload(monkeypatch, caplog):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token-abc")
    monkeypatch.setenv("EMAIL_FROM", "support@windowquoting.test")
    monkeypatch.setenv("EMAIL_FROM_NAME", "Window Quoting")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ErrorCode": 0,
        "Message": "OK",
        "MessageID": "abc-123-xyz",
    }
    with patch.object(mailer.requests, "post", return_value=mock_response) as mock_post:
        result = mailer.send_email(
            "user@example.com",
            "Verify your email",
            "<p>Click <a href='...'>here</a></p>",
            "Click here: ...",
        )

    assert result is True
    assert "[EMAIL-SENT]" in caplog.text
    assert "message_id=abc-123-xyz" in caplog.text

    # Verify Postmark received the correct payload + headers
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == mailer.POSTMARK_API_URL
    assert kwargs["headers"]["X-Postmark-Server-Token"] == "test-token-abc"
    body = kwargs["json"]
    assert body["From"] == "Window Quoting <support@windowquoting.test>"
    assert body["To"] == "user@example.com"
    assert body["Subject"] == "Verify your email"
    assert body["HtmlBody"] == "<p>Click <a href='...'>here</a></p>"
    assert body["TextBody"] == "Click here: ..."
    assert body["MessageStream"] == "outbound"


def test_kwargs_override_env(monkeypatch):
    """Caller-supplied token/from override env. Useful for tests that
    want to verify behavior without poking os.environ."""
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "env-token")
    monkeypatch.setenv("EMAIL_FROM", "env@x.test")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ErrorCode": 0, "MessageID": "id"}
    with patch.object(mailer.requests, "post", return_value=mock_response) as mock_post:
        mailer.send_email(
            "to@x.test", "s", "h", "t",
            server_token="override-token",
            from_addr="override@x.test",
            from_name="Override Name",
        )
    args, kwargs = mock_post.call_args
    assert kwargs["headers"]["X-Postmark-Server-Token"] == "override-token"
    assert kwargs["json"]["From"] == "Override Name <override@x.test>"


def test_bare_sender_when_name_empty(monkeypatch):
    """When EMAIL_FROM_NAME is unset / empty, From should be bare addr."""
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "t")
    monkeypatch.setenv("EMAIL_FROM", "bare@x.test")
    monkeypatch.setenv("EMAIL_FROM_NAME", "")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ErrorCode": 0, "MessageID": "id"}
    with patch.object(mailer.requests, "post", return_value=mock_response) as mock_post:
        mailer.send_email("to@x.test", "s", "h", "t")
    body = mock_post.call_args.kwargs["json"]
    assert body["From"] == "bare@x.test"

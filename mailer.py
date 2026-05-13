"""
Transactional email backend — Postmark HTTP API.

Why Postmark (Inquisitor C3):
  - Transactional-only product; deliverability reputation is the best on the
    free tier (100 emails/month, $15/mo for 10k after).
  - HTTP API (not SMTP) — no auth handshake to debug, no port-25 firewall
    issues, idempotent retries are trivial.
  - Webhook payloads for bounces / spam complaints are clean (out of scope
    for v1; surface via dashboard monitoring).

Public API:
  send_email(to, subject, html_body, text_body) -> bool

Side effects:
  - Logs `[EMAIL-SENT]` on success
  - Logs `[EMAIL-SEND-FAILED]` on failure (network, 4xx, 5xx) and returns False
  - Logs `[MAIL-DISABLED]` and returns True when MAIL_DISABLED=1 (test scaffold)
  - Never raises — callers can branch on the bool without try/except

Configuration (env vars, all read at boot via config.py):
  POSTMARK_SERVER_TOKEN — required outside DEV_MODE; missing in prod = boot error
  EMAIL_FROM            — verified sender address in Postmark
  EMAIL_FROM_NAME       — friendly display name ("Panefree Quotes")
  MAIL_DISABLED         — test-only kill switch; no real HTTP when set

Why the kill switch mirrors WTF_CSRF_DISABLED / RATELIMIT_DISABLED:
  Same pattern, same rationale: the test harness (stress_probe, locust, the
  H3 acceptance tests) needs deterministic local runs without spending the
  Postmark monthly quota or polluting the dashboard with synthetic sends.
  Production MUST NOT set MAIL_DISABLED — a config check in app.py boots
  with a loud warning when it's set so the misconfig is impossible to miss.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

POSTMARK_API_URL = "https://api.postmarkapp.com/email"
POSTMARK_TIMEOUT_S = 10  # network call budget — Postmark's median is ~200ms; 10s catches dead-network


def _is_mail_disabled() -> bool:
    """Test-scaffold kill switch. Read on every call rather than cached at
    import time so individual tests can toggle via monkeypatch."""
    return os.environ.get("MAIL_DISABLED", "").lower() in ("1", "true", "yes")


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    *,
    server_token: Optional[str] = None,
    from_addr: Optional[str] = None,
    from_name: Optional[str] = None,
) -> bool:
    """
    Send one transactional email through Postmark.

    Returns True on success (HTTP 200 with Postmark ErrorCode=0), False on
    any failure (network, non-2xx, non-zero ErrorCode). Never raises.

    Caller is responsible for deciding what to do on a False return —
    typical pattern is to log a higher-level failure and continue (e.g.
    /register persists the user row even if the verification email fails;
    the user can request a resend).

    Kwargs `server_token`, `from_addr`, `from_name` exist for unit tests
    to inject without monkey-patching os.environ. Production callers
    leave them as None and the function reads from env.
    """
    if _is_mail_disabled():
        logger.info(
            "[MAIL-DISABLED] would send to=%s subject=%r (text=%d chars, html=%d chars)",
            to, subject, len(text_body), len(html_body),
        )
        return True

    token = server_token or os.environ.get("POSTMARK_SERVER_TOKEN")
    sender = from_addr or os.environ.get("EMAIL_FROM")
    sender_name = from_name or os.environ.get("EMAIL_FROM_NAME", "Panefree Quotes")

    if not token:
        logger.error(
            "[EMAIL-SEND-FAILED] to=%s subject=%r: POSTMARK_SERVER_TOKEN unset "
            "(and MAIL_DISABLED is not set — this is a config error)",
            to, subject,
        )
        return False
    if not sender:
        logger.error(
            "[EMAIL-SEND-FAILED] to=%s subject=%r: EMAIL_FROM unset",
            to, subject,
        )
        return False

    # Postmark accepts "Name <addr@example.com>" or bare "addr@example.com".
    from_field = f"{sender_name} <{sender}>" if sender_name else sender

    payload = {
        "From": from_field,
        "To": to,
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": "outbound",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": token,
    }

    try:
        resp = requests.post(
            POSTMARK_API_URL,
            json=payload,
            headers=headers,
            timeout=POSTMARK_TIMEOUT_S,
        )
    except requests.RequestException as e:
        logger.error(
            "[EMAIL-SEND-FAILED] to=%s subject=%r: network error %r",
            to, subject, e,
        )
        return False

    # Postmark always returns JSON; ErrorCode=0 means success. Non-200
    # responses also carry ErrorCode + Message we want surfaced in the log.
    try:
        body = resp.json()
    except ValueError:
        logger.error(
            "[EMAIL-SEND-FAILED] to=%s subject=%r: non-JSON response status=%s body=%r",
            to, subject, resp.status_code, resp.text[:200],
        )
        return False

    error_code = body.get("ErrorCode")
    if resp.status_code == 200 and error_code == 0:
        logger.info(
            "[EMAIL-SENT] to=%s subject=%r message_id=%s",
            to, subject, body.get("MessageID"),
        )
        return True

    logger.error(
        "[EMAIL-SEND-FAILED] to=%s subject=%r: status=%s ErrorCode=%s Message=%r",
        to, subject, resp.status_code, error_code, body.get("Message"),
    )
    return False

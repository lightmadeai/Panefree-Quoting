"""
User-facing notice payloads — pure Python, no Flask dependency. Lives outside
app.py so it can be unit-tested without booting the Flask app + database.
"""

from datetime import timedelta


def build_soft_cap_notice(quote_count, threshold, contact_url):
    """
    CTA payload for an annual subscriber whose quote volume in the current
    billing period has reached the threshold. Returns None below threshold
    so the caller can short-circuit with `if notice:`. The notice is purely
    informational — generation is never throttled regardless of count.

    Sprint 3: contact_url now points to the in-app `/contact` intake form
    instead of a `mailto:` — captures more structured info (company,
    volume, growth) than an email body.
    """
    if quote_count < threshold:
        return None
    return {
        "count": quote_count,
        "threshold": threshold,
        "message": (
            f"You've used {quote_count} of {threshold} quotes this year. "
            f"Need more? Contact us for custom pricing."
        ),
        "contact_url": contact_url,
    }


def build_soft_cap_warning(quote_count, threshold):
    """
    Early-warning tier for annual subscribers approaching the soft cap
    (Sprint 4 T1). Fires at 80% of `threshold` and stays active until the
    user crosses 100%, at which point the upstream soft_cap_notice takes
    over with its CTA. This warning has NO CTA — it's a heads-up, not a
    sales ask.

      < 80% threshold  -> None (silent)
      80-99% threshold -> warning payload, informational only
      >= 100%          -> None here (caller uses build_soft_cap_notice instead)

    The 80% boundary is computed integer-style (`threshold * 8 // 10`) so
    behavior is deterministic for any integer threshold and there's no
    floating-point edge at exact 80% boundaries.
    """
    warning_floor = (threshold * 8) // 10
    if quote_count < warning_floor or quote_count >= threshold:
        return None
    return {
        "code": "SOFT_CAP_WARNING",
        "count": quote_count,
        "warning_threshold": warning_floor,
        "soft_cap": threshold,
        "message": (
            f"You've used {quote_count}+ quotes this year. "
            f"We'll reach out if you need volume pricing."
        ),
    }


def build_rate_limit_notice(quote_count, threshold, oldest_in_window, now):
    """
    Rolling-window rate-limit response. Returns None if the user is under
    threshold; otherwise a payload the route splices into a 429 response.
    Caller computes oldest_in_window from the DB; this function is pure
    given those inputs.

    The countdown is "minutes until the oldest quote in the window falls
    out" — that's when the user's effective count drops back below the
    threshold and the next request will succeed.
    """
    if quote_count < threshold:
        return None
    fall_out = oldest_in_window + timedelta(hours=1)
    seconds = max(0, int((fall_out - now).total_seconds()))
    # Round up so the countdown never undersells the wait — telling someone
    # "1 minute" when it's actually 90 seconds away is worse than rounding up.
    minutes = max(1, (seconds + 59) // 60)
    return {
        "code": "RATE_LIMITED",
        "message": (
            f"You've reached {threshold} quotes this hour. "
            f"Next available in {minutes} minute{'' if minutes == 1 else 's'}."
        ),
        "retry_after_minutes": minutes,
    }

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

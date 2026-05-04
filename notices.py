"""
User-facing notice payloads — pure Python, no Flask dependency. Lives outside
app.py so it can be unit-tested without booting the Flask app + database.
"""


def build_soft_cap_notice(quote_count, threshold, contact_email):
    """
    CTA payload for an annual subscriber whose quote volume in the current
    billing period has reached the threshold. Returns None below threshold
    so the caller can short-circuit with `if notice:`. The notice is purely
    informational — generation is never throttled regardless of count.
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
        "contact_email": contact_email,
        "contact_url": f"mailto:{contact_email}",
    }

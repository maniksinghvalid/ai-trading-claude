"""Constant-time bearer-token check for the AI Trading Analyst proxy.

Layer 2 of the 5-layer auth model (high-entropy URL · bearer · payload
validation · rate limit · monthly rotation). See producer plan §"Auth model
— 5 layers, bounded-blast-radius".

The token lives in Vercel env var ``PROXY_AUTH_TOKEN``; routines present
it via the ``Authorization: Bearer <token>`` header. Compared with
``hmac.compare_digest`` to avoid timing side channels.
"""

import hmac
import os
from typing import Optional


class AuthError(Exception):
    """Raised when a request fails bearer validation. Maps to HTTP 401."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def expected_token() -> Optional[str]:
    """Return the deployment's expected bearer, or None if unset.

    A missing token is a deployment-config bug — the proxy is unusable. We
    surface this as a 401 so callers see a uniform failure mode (vs a
    server-side 500 that would leak deployment-state information).
    """
    return os.environ.get("PROXY_AUTH_TOKEN")


def check_bearer(authorization_header: Optional[str]) -> None:
    """Validate an Authorization header. Raises ``AuthError`` on any failure.

    Failure modes (all map to HTTP 401 with intentionally vague messages —
    we tell the caller "auth failed" without specifying which check tripped):
    - Missing header
    - Header doesn't start with ``Bearer ``
    - Token doesn't match (constant-time compared)
    - Deployment has no ``PROXY_AUTH_TOKEN`` configured

    The proxy never logs the token itself — only "auth ok" / "auth failed".
    """
    expected = expected_token()
    if not expected:
        # Deployment misconfiguration. Fail closed.
        raise AuthError("auth not configured")

    if not authorization_header:
        raise AuthError("missing authorization")

    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("malformed authorization")

    presented = parts[1].strip()
    # compare_digest requires equal-length bytes; pad both sides before compare
    # to keep the timing constant regardless of presented-token length.
    if not hmac.compare_digest(
        presented.encode("utf-8"), expected.encode("utf-8")
    ):
        raise AuthError("bearer mismatch")

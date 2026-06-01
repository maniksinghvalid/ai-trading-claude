"""Tiny JSON-response helpers that integrate with Vercel's
``BaseHTTPRequestHandler`` signature.

All responses include ``schema_version`` in the body so clients can detect
proxy upgrades. The 401/400/429 paths are intentionally short on detail —
the proxy must not leak internal state or "did the auth check or the
payload check fail" information.
"""

import json
from http.server import BaseHTTPRequestHandler


def send_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: dict,
) -> None:
    """Write ``body`` as JSON with the given HTTP status."""
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    # Leak nothing about deployment internals via Server header
    handler.send_header("X-Proxy-Schema-Version", "1")
    handler.end_headers()
    handler.wfile.write(payload)


def send_auth_error(handler, reason: str = "auth failed") -> None:
    """Generic 401. Detail intentionally vague."""
    send_json(handler, 401, {"error": "unauthorized", "reason": reason})


def send_validation_error(handler, reason: str, details: dict = None) -> None:
    """400 with structured detail so callers can fix their payload."""
    send_json(handler, 400, {
        "error": "validation_failed",
        "reason": reason,
        "details": details or {},
    })


def send_rate_limited(handler, retry_after: int = 60) -> None:
    """429 with Retry-After hint."""
    handler.send_response(429)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Retry-After", str(retry_after))
    handler.end_headers()
    handler.wfile.write(json.dumps({
        "error": "rate_limited",
        "retry_after": retry_after,
    }).encode("utf-8"))


def send_internal_error(handler, reason: str = "internal error") -> None:
    """500. We log details server-side via stderr; the response itself is
    deliberately uninformative.
    """
    send_json(handler, 500, {"error": "internal_error", "reason": reason})


def read_json_body(handler) -> dict:
    """Read + parse the request body as JSON. Raises ValueError on bad JSON
    or oversized payload (> 500 KB hard cap per plan endpoint table).
    """
    length = int(handler.headers.get("Content-Length", "0"))
    if length > 500 * 1024:
        raise ValueError("payload too large (> 500 KB)")
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))

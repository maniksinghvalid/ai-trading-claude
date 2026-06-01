"""Shared ``BaseHTTPRequestHandler`` boilerplate for every proxy endpoint.

Each ``proxy/api/<op>.py`` instantiates ``handler = make_handler(<op_fn>)``
where ``op_fn(payload: dict) -> dict`` is the endpoint's logic. The boilerplate
handles bearer auth (layer 2), payload validation entry (layer 3 happens
inside op_fn via the per-endpoint Pydantic models), rate limiting (layer 4),
and response shaping.

Method is hardcoded to POST — these are RPC-style ops, not REST resources.
"""

import sys
import traceback
from http.server import BaseHTTPRequestHandler

from pydantic import ValidationError as PydanticValidationError

from . import auth, ratelimit, responses, validate


def _client_ip(handler) -> str:
    """Extract the client IP. Vercel sets x-forwarded-for; fall back to the
    socket peer.
    """
    fwd = handler.headers.get("x-forwarded-for", "")
    if fwd:
        # First entry is the original client; the rest is proxy chain
        return fwd.split(",")[0].strip()
    try:
        return handler.client_address[0]
    except Exception:
        return "unknown"


def make_handler(op_fn, *, endpoint: str):
    """Return a ``BaseHTTPRequestHandler`` subclass that runs the 5-layer
    auth stack and then dispatches to ``op_fn(payload) -> dict``.
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Suppress default access log; we have structured logs via stderr
            # for events that matter (auth failures, validation failures,
            # rate-limit hits, internal errors).
            pass

        def do_POST(self):
            try:
                # Layer 2: bearer auth
                try:
                    auth.check_bearer(self.headers.get("Authorization"))
                except auth.AuthError as e:
                    sys.stderr.write(
                        f"[auth] {endpoint} {_client_ip(self)} 401: {e.reason}\n"
                    )
                    return responses.send_auth_error(self, e.reason)

                # Layer 4: rate limit (before parsing body so we don't waste
                # work on abusive clients)
                try:
                    ratelimit.check_rate_limit(_client_ip(self))
                except ratelimit.RateLimitExceeded as e:
                    sys.stderr.write(
                        f"[ratelimit] {endpoint} {_client_ip(self)} 429\n"
                    )
                    return responses.send_rate_limited(self, e.retry_after)

                # Parse body
                try:
                    body = responses.read_json_body(self)
                except ValueError as e:
                    return responses.send_validation_error(
                        self, "malformed JSON", {"detail": str(e)}
                    )

                # Layer 3: per-endpoint validation happens inside op_fn
                try:
                    result = op_fn(body)
                except validate.ValidationError as e:
                    sys.stderr.write(
                        f"[validate] {endpoint} {_client_ip(self)} 400: {e.reason}\n"
                    )
                    return responses.send_validation_error(
                        self, e.reason, e.details
                    )
                except PydanticValidationError as e:
                    # Pydantic raises this when the per-endpoint request
                    # model (UpsertRequest / QueryRequest / etc.) rejects
                    # the payload. Surface the first error's loc + msg so
                    # callers can fix the payload without us leaking the
                    # full model schema.
                    errors = e.errors()
                    first = errors[0] if errors else {}
                    loc = ".".join(str(x) for x in (first.get("loc") or []))
                    msg = first.get("msg", "schema violation")
                    sys.stderr.write(
                        f"[validate] {endpoint} {_client_ip(self)} 400: "
                        f"pydantic — {loc}: {msg}\n"
                    )
                    return responses.send_validation_error(
                        self,
                        f"{loc}: {msg}" if loc else msg,
                        {"errors": [
                            {"loc": ".".join(str(x) for x in (err.get("loc") or [])),
                             "msg": err.get("msg")}
                            for err in errors
                        ]},
                    )
                except Exception:
                    sys.stderr.write(
                        f"[error] {endpoint} {_client_ip(self)} 500\n"
                        + traceback.format_exc()
                    )
                    return responses.send_internal_error(self)

                return responses.send_json(self, 200, result)

            except Exception:
                # Top-level safety net — never leak a stack trace to the client
                sys.stderr.write(
                    f"[error-toplevel] {endpoint} 500\n"
                    + traceback.format_exc()
                )
                try:
                    responses.send_internal_error(self)
                except Exception:
                    pass

        def do_GET(self):
            # Method-not-allowed: 405. Don't reveal endpoint surface.
            responses.send_json(
                self, 405, {"error": "method_not_allowed"}
            )

    return Handler

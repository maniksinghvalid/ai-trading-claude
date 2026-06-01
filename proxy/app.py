"""Single WSGI entrypoint for the AI Trading Analyst proxy.

Vercel's modern Python runtime expects ONE entrypoint module
(``app.py`` / ``index.py`` / ``main.py`` / etc.) rather than the legacy
per-file ``api/*.py`` pattern. This module is that entrypoint — it
dispatches POST `/upsert`, `/query`, `/list`, `/fetch`, `/delete` to the
``*_op(body)`` callables defined in ``api/*.py`` and runs the same 5-layer
auth stack (auth → rate limit → JSON parse → per-endpoint validation →
op) the per-file handlers ran.

Local dev: ``python3 -m wsgiref.simple_server`` (see
``scripts/run_local_proxy.py`` for the boot script the D.19 gate uses).

Vercel: ``app`` is the WSGI callable Vercel imports.
"""

import json
import os
import pathlib
import sys
import traceback

# Make `from _lib import ...` and `from api.<op> import <op>_op` resolve
# both locally and inside Vercel's /var/task runtime layout.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Ensure validate.py can find trade_schemas.py inside the Vercel bundle
# (it falls back to repo-local paths for dev; this env var lets ops also
# override at deploy time without code changes).
os.environ.setdefault(
    "TRADE_SCHEMAS_PATH",
    str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "trade_schemas.py"),
)

from pydantic import ValidationError as PydanticValidationError

from _lib import auth, ratelimit, validate
from api.upsert import upsert_op
from api.query import query_op
from api.list import list_op
from api.fetch import fetch_op
from api.delete import delete_op

OPS = {
    "/upsert": upsert_op,
    "/query":  query_op,
    "/list":   list_op,
    "/fetch":  fetch_op,
    "/delete": delete_op,
}


def _json_response(start_response, status, body, extra_headers=None):
    payload = json.dumps(body).encode("utf-8")
    headers = [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(payload))),
        ("X-Proxy-Schema-Version", "1"),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    start_response(status, headers)
    return [payload]


def _client_ip(environ):
    """Extract the originating client IP. Vercel + most proxies set
    X-Forwarded-For; first entry is the original client.
    """
    fwd = environ.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return environ.get("REMOTE_ADDR", "unknown")


def app(environ, start_response):
    """WSGI entrypoint. POST <op> only; everything else → 405."""
    method = environ.get("REQUEST_METHOD", "")
    path = environ.get("PATH_INFO", "")

    if method != "POST":
        return _json_response(
            start_response, "405 Method Not Allowed",
            {"error": "method_not_allowed"},
        )

    op_fn = OPS.get(path)
    if op_fn is None:
        return _json_response(
            start_response, "404 Not Found",
            {"error": "not_found", "path": path},
        )

    try:
        # Layer 2: bearer auth
        try:
            auth.check_bearer(environ.get("HTTP_AUTHORIZATION"))
        except auth.AuthError as e:
            sys.stderr.write(
                f"[auth] {path} {_client_ip(environ)} 401: {e.reason}\n"
            )
            return _json_response(
                start_response, "401 Unauthorized",
                {"error": "unauthorized", "reason": e.reason},
            )

        # Layer 4: rate limit (before body parse — don't waste work on abusers)
        try:
            ratelimit.check_rate_limit(_client_ip(environ))
        except ratelimit.RateLimitExceeded as e:
            sys.stderr.write(
                f"[ratelimit] {path} {_client_ip(environ)} 429\n"
            )
            return _json_response(
                start_response, "429 Too Many Requests",
                {"error": "rate_limited", "retry_after": e.retry_after},
                extra_headers=[("Retry-After", str(e.retry_after))],
            )

        # Parse body
        try:
            length = int(environ.get("CONTENT_LENGTH", "0") or "0")
            if length > 500 * 1024:
                return _json_response(
                    start_response, "400 Bad Request",
                    {"error": "validation_failed",
                     "reason": "payload too large (> 500 KB)"},
                )
            raw = environ["wsgi.input"].read(length) if length > 0 else b""
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, json.JSONDecodeError) as e:
            return _json_response(
                start_response, "400 Bad Request",
                {"error": "validation_failed", "reason": "malformed JSON",
                 "details": {"detail": str(e)}},
            )

        # Layer 3: per-endpoint validation + op dispatch
        try:
            result = op_fn(body)
        except validate.ValidationError as e:
            sys.stderr.write(
                f"[validate] {path} {_client_ip(environ)} 400: {e.reason}\n"
            )
            return _json_response(
                start_response, "400 Bad Request",
                {"error": "validation_failed",
                 "reason": e.reason,
                 "details": e.details or {}},
            )
        except PydanticValidationError as e:
            errors = e.errors()
            first = errors[0] if errors else {}
            loc = ".".join(str(x) for x in (first.get("loc") or []))
            msg = first.get("msg", "schema violation")
            return _json_response(
                start_response, "400 Bad Request",
                {"error": "validation_failed",
                 "reason": f"{loc}: {msg}" if loc else msg,
                 "details": {"errors": [
                     {"loc": ".".join(str(x) for x in (err.get("loc") or [])),
                      "msg": err.get("msg")}
                     for err in errors
                 ]}},
            )
        except Exception:
            sys.stderr.write(
                f"[error] {path} {_client_ip(environ)} 500\n"
                + traceback.format_exc()
            )
            return _json_response(
                start_response, "500 Internal Server Error",
                {"error": "internal_error"},
            )

        return _json_response(start_response, "200 OK", result)

    except Exception:
        sys.stderr.write(
            f"[error-toplevel] {path} 500\n" + traceback.format_exc()
        )
        return _json_response(
            start_response, "500 Internal Server Error",
            {"error": "internal_error"},
        )

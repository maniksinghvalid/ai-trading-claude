"""Per-IP rate limiting via Upstash Redis (REST API; serverless-friendly).

Layer 4 of the 5-layer auth model. 100 req/min per source IP by default;
bursts allowed via a sliding window. Routines use < 30 req/run, so the
threshold protects against runaway loops + token-leak abuse.

**No-op fallback:** if ``UPSTASH_REDIS_REST_URL`` is unset, rate limiting
is disabled with a one-line log warning. This lets the proxy deploy
without forcing the Upstash signup step — the operator can wire Upstash
later. Production-grade deployments should always set both env vars.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request


class RateLimitExceeded(Exception):
    """Raised when the per-IP request count exceeds the threshold. Maps to
    HTTP 429.
    """

    def __init__(self, retry_after: int = 60):
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after


_WARNED_NO_UPSTASH = False


def _upstash_creds():
    global _WARNED_NO_UPSTASH
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        if not _WARNED_NO_UPSTASH:
            sys.stderr.write(
                "[ratelimit] UPSTASH_REDIS_REST_URL / _TOKEN unset; rate "
                "limiting DISABLED. The proxy is still protected by bearer "
                "auth + payload validation, but a leaked token would not "
                "throttle. Set both env vars to enable (Upstash free tier "
                "covers this load).\n"
            )
            _WARNED_NO_UPSTASH = True
        return None, None
    return url, token


def _upstash_pipeline(url: str, token: str, commands: list) -> list:
    """POST a Redis-style pipeline to Upstash REST.

    Returns the list of result entries. Raises on HTTP errors.
    """
    req = urllib.request.Request(
        url + "/pipeline",
        data=json.dumps(commands).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        # Network blip — fail OPEN (don't block legitimate traffic on a
        # rate-limiter outage). Log loudly.
        sys.stderr.write(
            f"[ratelimit] Upstash unreachable ({e}); failing open for this "
            "request. Investigate if this persists.\n"
        )
        return []


def check_rate_limit(
    source_ip: str,
    max_per_minute: int = 100,
) -> None:
    """Increment the per-IP minute counter; raise if over threshold.

    Uses a fixed-window counter (sliding window would need more commands;
    fixed-window with a 60s TTL is good enough for "100 req/min" enforcement
    on a research-tool-grade proxy).
    """
    url, token = _upstash_creds()
    if not url:
        return  # rate limiting disabled (logged once at boot)

    window = int(time.time() // 60)
    key = f"ratelimit:{source_ip}:{window}"

    # INCR then EXPIRE in a pipeline (atomic enough for a fixed-window
    # counter — the worst case is a counter that doesn't expire,
    # auto-cleared by Redis eviction).
    result = _upstash_pipeline(url, token, [
        ["INCR", key],
        ["EXPIRE", key, 60],
    ])

    if not result:
        return  # fail-open path already logged

    # result[0] = {"result": <new count>}
    try:
        count = int(result[0].get("result", 0))
    except (KeyError, TypeError, ValueError):
        return  # malformed response; fail open

    if count > max_per_minute:
        raise RateLimitExceeded(retry_after=60)

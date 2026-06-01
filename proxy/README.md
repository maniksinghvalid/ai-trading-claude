# AI Trading Analyst — Vercel HTTPS Proxy (slice 7.5)

Single-purpose serverless function that holds the producer's
`PINECONE_API_KEY` so cloud routines can read/write Pinecone without
embedding the key in a routine prompt.

This proxy is **research-tool-grade**, not production-grade. See
[Threat model](#threat-model) below. Worst-case compromise = "rebuild the
index from Drive" = ½ day inconvenience.

---

## Architecture

```
Cloud routine sandbox                Vercel function (this directory)
┌──────────────────────────┐         ┌──────────────────────────┐
│ trade_memory.py          │         │ /upsert /query /list     │  pinecone
│   sees PINECONE_PROXY_URL│  HTTPS  │ /fetch /delete           │  serverless
│        PINECONE_PROXY_TOKEN ──────►│                          │ ──────────►
│   routes via urllib +    │  Bearer │ holds PINECONE_API_KEY   │
│   Authorization: Bearer  │         │ in Vercel env vars       │
└──────────────────────────┘         └──────────────────────────┘
```

The routine never holds the Pinecone key. The proxy validates every
payload against the canonical schema in `scripts/trade_schemas.py` (the
same schema the local producer enforces) — single source of truth.

---

## Endpoints

All POST, JSON in / JSON out. Bearer auth required on every call.

| Endpoint | Body | Returns |
|---|---|---|
| `POST /upsert` | `{namespace, records: [...]}` ≤ 100, integrated-inference (text) or pre-embedded (values) | `{upserted_integrated, upserted_pre_embedded}` |
| `POST /query`  | `{namespace, text OR vector, top_k ≤ 50, filter?}` | `{hits: [{_id, _score, fields}]}` |
| `POST /list`   | `{namespace, prefix (required), limit ≤ 1000, pagination_token?}` | `{ids, next_pagination_token}` |
| `POST /fetch`  | `{namespace, ids: [...]}` ≤ 100 | `{records: {id: metadata_dict}}` |
| `POST /delete` | `{namespace, ids OR filter, confirm: "yes"}` | `{deleted_count, by: "ids"\|"filter"}` |

Response status codes:
- **200** — success
- **400** — `validation_failed` (bad payload, unknown namespace, missing
  `confirm` on /delete, oversize, etc.) — body has `reason` + `details`
- **401** — `unauthorized` (missing/wrong bearer, missing
  `PROXY_AUTH_TOKEN` on the proxy itself) — body has vague `reason` only
- **429** — `rate_limited` — `Retry-After` header in seconds
- **500** — `internal_error` — body intentionally uninformative; see
  Vercel runtime logs for the actual stack

---

## Deploy

### Option A — Vercel CLI (developer machine)

```bash
cd proxy/
npm i -g vercel              # one-time
vercel login                 # one-time
vercel --prod                # deploys; prints the deployment URL
```

The first `vercel` run asks you to link the directory to a Vercel project.
Accept the prompts to create a new project (e.g. `ai-trading-proxy`); the
URL will look like `https://ai-trading-proxy-<hash>.vercel.app`.

### Option B — Vercel MCP (from inside Claude Code)

If your Claude Code session has the Vercel MCP connected, ask:
> "Use `mcp__claude_ai_Vercel__deploy_to_vercel` to deploy this proxy."

The MCP handles the auth + project link + first deploy in one step.

### After deploy — set the env vars

In the Vercel project settings → Environment Variables, set:

| Name | Value | Notes |
|---|---|---|
| `PINECONE_API_KEY` | `pcsk_...` | the producer's full-access Pinecone key |
| `PROXY_AUTH_TOKEN` | `<32-char hex>` | generate with `openssl rand -hex 32` |
| `PINECONE_INDEX` | `trade-reports` | optional; defaults to this |
| `UPSTASH_REDIS_REST_URL` | `https://...` | optional; enables rate limiting (free tier) |
| `UPSTASH_REDIS_REST_TOKEN` | `...` | optional; required if URL is set |

After setting env vars, redeploy with `vercel --prod` so they take effect.

### Deployment Protection — two options

Vercel projects default to having "Deployment Protection" (SSO gate) on,
which blocks every request before it reaches our function — including
routine traffic with valid `PROXY_AUTH_TOKEN`. Pick one:

**Option A: Disable Deployment Protection** (simplest)

Project Settings → **Deployment Protection** → set Vercel Authentication
to **Disabled**. Our own bearer + payload validation + namespace
allowlist handle the gating job. The deploy URL is already
high-entropy enough that enumeration isn't a credible threat.

**Option B: Keep DP on, add Protection Bypass for Automation**

1. Project Settings → **Deployment Protection** → "Protection Bypass for
   Automation" → **Add new** → copy the generated token (Vercel calls
   this a "bypass secret")
2. On the producer side (and in any cloud routine prompt), set
   `VERCEL_PROTECTION_BYPASS=<the-bypass-secret>` alongside
   `PINECONE_PROXY_URL` and `PINECONE_PROXY_TOKEN`
3. `trade_memory.py` (slice 7.5+) attaches the
   `x-vercel-protection-bypass: <token>` header to every proxy request
   when the env var is set; without that header, Vercel SSO would
   intercept

Trade-off: two tokens to rotate (bypass + bearer); more
defense-in-depth, more surface to manage. For research-tool-grade use,
Option A is fine; for "I want to keep the dashboard SSO-protected
even though the API is public", Option B is the answer.

### Sanity-check the deploy

```bash
URL=https://<your-deployment>.vercel.app
TOKEN=<the PROXY_AUTH_TOKEN you set>

# Auth check: should return 400 (validation_failed on empty payload),
# NOT 401 — that proves the bearer is correct
curl -sS -X POST "$URL/query" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}'
# Expected: {"error":"validation_failed","reason":"...","details":{...}}

# Wrong-token check: should return 401
curl -sS -X POST "$URL/query" \
    -H "Authorization: Bearer wrong-token" \
    -H "Content-Type: application/json" \
    -d '{}'
# Expected: {"error":"unauthorized","reason":"bearer mismatch"}

# Forbidden-namespace check: should return 400 (allowlist guard)
curl -sS -X POST "$URL/query" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"namespace":"forbidden","text":"hi","top_k":1}'
# Expected: {"error":"validation_failed","reason":"namespace 'forbidden' not in allowlist",...}
```

### Wire the producer (`trade_memory.py`)

```bash
export PINECONE_PROXY_URL="https://<your-deployment>.vercel.app"
export PINECONE_PROXY_TOKEN="<the PROXY_AUTH_TOKEN you set>"

# `doctor` should report "Cloud-proxy mode active" and the auth check pass
python3 ~/.claude/skills/trade/scripts/trade_memory.py doctor
```

When both env vars are set, every routine + analyze + recall + thesis call
routes through the proxy automatically. Skills don't branch — the
branching lives inside `VectorStore` (see `scripts/trade_memory.py`
docstring "Cloud-mode wiring (slice 7.5)").

---

## Rotation procedures

### Bearer token (monthly — 5-minute op)

1. Generate a new token: `openssl rand -hex 32`
2. Vercel project settings → Environment Variables → edit
   `PROXY_AUTH_TOKEN` → paste new value
3. Redeploy: `vercel --prod` (env-var changes need a redeploy to take effect)
4. Update the routine prompt: replace the old `PINECONE_PROXY_TOKEN=...`
   line with the new one (in whichever `/schedule`-created RemoteTrigger
   holds it)
5. Verify with `doctor`: `python3 .../trade_memory.py doctor` should still
   report "Proxy auth check passed"

### Subdomain URL (quarterly — 10-minute op)

1. Create a new Vercel project (or rename the existing one to get a new
   hash-suffixed URL): `vercel project add ai-trading-proxy-<new-hash>`
2. Re-deploy with the same env vars: `vercel --prod`
3. Update `PINECONE_PROXY_URL` in every routine prompt that references it
4. Old project: pause + queue for deletion 7 days later (leave time to
   roll back if something breaks)

### Log review (weekly — 2-minute op)

Use the Vercel MCP or the dashboard:

```
mcp__claude_ai_Vercel__get_runtime_logs
  deploymentId: <your latest>
```

Look for:
- 401 spikes → someone trying brute force; rotate the bearer immediately
- 429 spikes → rate limiter doing its job (good) OR runaway routine (bad);
  investigate the source IP
- 500 → real bugs; investigate the stack in stderr

---

## Token hygiene — `PINECONE_PROXY_TOKEN` is NOT a secret-grade location

The bearer lives in the routine prompt body submitted via `/schedule` to
the RemoteTrigger API. That prompt is not stored in a repo file by
default — **but the moment you put it somewhere git-tracked, you leak it**.

### ✅ Safe places to store the token

- Vercel project's Environment Variables UI (this is the canonical home)
- A local password manager (1Password, Bitwarden, macOS Keychain)
- The routine prompt itself (in the RemoteTrigger payload — not stored
  locally in a repo file)

### ✗ Unsafe places — DO NOT put the token here

- Anywhere under the repo root (including `proxy/.env`, `scripts/.env`,
  `.env`)
- Anywhere in `.claude/` — that directory gets rsync-mirrored into Git by
  `scripts/sync_claude_dir.sh` (see CLAUDE.md cross-file contracts)
- Any chat transcript you save locally
- Any deployment-helper script (`deploy.sh`, `setup.sh`, etc.) tracked by
  git
- Any `.env*` file checked into git — even `.env.example` should NEVER
  carry the real value (use a placeholder)
- A markdown notes file (`TODO.md`, `notes.md`) tracked by git

If you accidentally commit the token: **rotate it immediately** (see
above), then `git filter-repo` or BFG the leaked commit out of history,
then force-push. Vercel's Pinecone key + your token are decoupled, so a
leaked token doesn't expose the Pinecone key — but it does mean someone
else can write contract-valid records to your `trade` namespace.

---

## Threat model

**What this auth model protects against:**
- Casual scrapers (high-entropy URL not enumerable)
- Schema-bypass attacks (Pydantic + namespace allowlist + explicit
  `confirm:"yes"` on /delete)
- Runaway routines (rate limiter — when Upstash is wired)
- Token brute force (rate limiter + constant-time comparison)

**What it does NOT protect against:**
- A determined attacker with the bearer token (they can write
  schema-valid records to the `trade` namespace — but they can't
  exfiltrate the Pinecone key, can't reach other indexes, can't bulk
  delete without `confirm:"yes"`)
- Production-grade compliance (no audit logs beyond stderr, no per-user
  permissions, no PII handling)
- Multi-tenant scenarios (single bearer for all routines — if the
  trading-chatbot wants per-user keys, that's a slice 9+ extension)

**Worst-case compromise:** an attacker with the bearer writes garbage
records to your `trade` namespace and burns your Pinecone quota. Recovery:

1. Rotate the bearer (5 min — see above)
2. `trade_memory.py delete --ticker GARBAGE --yes` (or `rebuild` from the
   Drive archive of legitimate TRADE-*.md reports)

½ day inconvenience, no permanent damage.

---

## Cost

Vercel free tier: 100 GB-hours/month function execution + 100 GB egress.
A daily routine fires ~30 requests/run × 30 days = ~900 requests/month
× ~200ms each = ~3 minutes of execution/month. Effectively zero.

Upstash Redis free tier: 10K commands/day. Rate limiter uses 2
commands/request (INCR + EXPIRE) = 60 commands/run. Effectively zero.

Pinecone is unchanged from the §1 plan estimate of $0.15–$0.30/month for
a 20-ticker daily portfolio.

**Total expected: ~$0/month** for the proxy tier.

---

## Verifying parity with local mode (D.19 gate)

Every commit that touches `proxy/api/*.py`, `proxy/_lib/validate.py`, or
`scripts/trade_schemas.py` should run this check:

```bash
# Local (direct SDK)
python3 scripts/trade_memory.py ingest /tmp/TRADE-ANALYSIS-TEST.md
python3 scripts/trade_memory.py latest TEST --type ANALYSIS > /tmp/local.json

# Clean up
python3 scripts/trade_memory.py delete --ticker TEST --yes

# Cloud (via proxy)
export PINECONE_PROXY_URL=https://<your-deployment>.vercel.app
export PINECONE_PROXY_TOKEN=<token>
python3 scripts/trade_memory.py ingest /tmp/TRADE-ANALYSIS-TEST.md
python3 scripts/trade_memory.py latest TEST --type ANALYSIS > /tmp/cloud.json

# Compare
diff /tmp/local.json /tmp/cloud.json
# Expected: no diff
```

If there's drift, it means proxy validation is rejecting a field the local
producer accepts, or vice versa. Both paths import the same
`trade_schemas.py` so this should be very hard to break — but the gate is
the regression catch.

---

## File layout

```
proxy/
├── app.py                  # Single WSGI entrypoint — Vercel imports `app`
├── api/                    # Per-endpoint op_fn callables (imported by app.py)
│   ├── __init__.py
│   ├── upsert.py           # upsert_op(body)
│   ├── query.py            # query_op(body)
│   ├── list.py             # list_op(body)
│   ├── fetch.py            # fetch_op(body)
│   └── delete.py           # delete_op(body)
├── _lib/                   # Shared helpers
│   ├── auth.py             # Constant-time bearer compare
│   ├── validate.py         # Imports trade_schemas + per-endpoint Pydantic models
│   ├── ratelimit.py        # Upstash REST with no-op fallback
│   ├── pinecone_client.py  # Singleton Pinecone client
│   └── responses.py        # JSON helpers
├── requirements.txt        # pinecone>=5, pydantic>=2
├── vercel.json             # Single-function config pointing at app.py
├── .env.example            # template; real values live in Vercel UI
└── README.md               # this file
```

Vercel's modern Python runtime requires a single WSGI/ASGI entrypoint
(`app.py` is one of the auto-detected names). `app.py` dispatches each
POST request to the matching `*_op(body)` callable in `api/`. The per-file
files in `api/` are NOT deployed as individual serverless functions — they
just hold the endpoint logic that `app.py` imports.

`scripts/trade_schemas.py` (one directory up) is bundled into the function
deploy via `vercel.json`'s `includeFiles` config and located at runtime
by `proxy/_lib/validate.py`'s `_import_trade_schemas()` helper.

---

## Related docs

- `plan/portfolio-routine-and-vector-memory.md` §"Cloud path: Vercel HTTPS proxy" — the producer plan section that specs this proxy
- `plan/cfg-verification-20260531.md` — why Path D (this proxy) was chosen over Path C (direct connector)
- `CLAUDE.md` — project conventions; the "cross-file contracts" section flags trade_schemas.py as the SSOT for the record contract

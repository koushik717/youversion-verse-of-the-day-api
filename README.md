# Verse of the Day API

A small FastAPI service that collapses YouVersion's two-call verse-of-the-day
flow (`/v1/verse_of_the_days/{day}` → `/v1/bibles/{version}/passages/{id}`)
into a single `GET /votd` endpoint.

## Setup & run instructions

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit .env and paste in the app key
export $(cat .env | xargs)       # or use your own way of loading env vars

uvicorn app.main:app --reload --port 8000
```

Try it:

```bash
curl "http://127.0.0.1:8000/votd?day=195&version=206"
curl "http://127.0.0.1:8000/votd"                        # today, default version
curl "http://127.0.0.1:8000/votd?day=0"                   # 400, INVALID_DAY
curl "http://127.0.0.1:8000/versions"                     # stretch goal
```

### Running the tests

Tests never call the live YouVersion API — every HTTP call is served by an
`httpx.MockTransport` fixture (`tests/conftest.py`), so no app key or network
access is needed to run them.

```bash
pip install -r requirements.txt   # pytest is included
pytest
```

## Decisions & Assumptions

The spec left a few things open on purpose. Here's what I chose and why:

- **`day` omitted → today's day-of-year in UTC.** The service doesn't know
  the caller's timezone, and UTC is the one unambiguous choice available
  without adding a `timezone` parameter the spec doesn't ask for.
- **`version` omitted → defaults to `206` (World English Bible).** It's
  public-domain and always accessible with the provided key, so an
  unqualified `GET /votd` always succeeds instead of failing or silently
  picking a version that might 403 (like `111`/NIV would).
- **Validation happens before any upstream call.** `day=0`, `day=367`,
  `day=abc` are all rejected locally as `INVALID_DAY` — YouVersion is never
  touched for a request that can't possibly succeed. Same idea for a
  non-integer `version`, rejected as `INVALID_VERSION`.
- **A version YouVersion itself rejects (e.g. `111`/NIV, `403 Access
  denied`) surfaces as `502 UPSTREAM_ERROR`, not `400`.** The spec calls
  this "expected licensing behavior, not a bug," and this service has no
  way to know in advance which version IDs are licensed for a given app
  key — that's YouVersion's call to make, not ours. Rejecting it as *our*
  validation error would be misleading.
- **Caching is two-level, not one flat `(day, version)` cache.** `day →
  passage_id` and `(version, passage_id) → text` are cached separately, in
  memory, for the life of the process. That means requesting the same day
  in two different versions still only calls the calendar endpoint once,
  and requesting two different days that happen to land on the same
  passage in the same version only fetches the text once. Both pieces are
  static, so there's no invalidation to worry about.
- **Error responses always use the shape from the spec** —
  `{"error": {"code": ..., "message": ...}}` — via a single `ApiError`
  exception carrying `(status_code, code, message)`, caught by one FastAPI
  exception handler. Every failure path (validation, upstream 5xx,
  timeout, malformed upstream JSON) raises that same exception instead of
  building the JSON ad hoc per route.
- **Query params are parsed as raw strings, not FastAPI's typed
  `int` params.** FastAPI's built-in type coercion would return its own
  `422` error shape for `day=abc`, which conflicts with requirement #2
  ("every error returns JSON of exactly this shape"). Parsing manually
  keeps *all* error responses consistent.

## What I'd do next

- Add a cache TTL (or at least a manual eviction hook) — today's cache is
  correct because the data is genuinely static, but an unbounded
  in-memory dict isn't something I'd want running unmonitored for weeks
  in production.
- Add a lock around the cache fill so two concurrent requests for the same
  brand-new `(day, version)` don't both fan out to YouVersion (a minor
  "cache stampede" on the very first request for a given key — harmless
  here, but worth closing).
- Add the optional stretch's version list to the `/votd` response's
  `version` validation, so an unrecognized-but-well-formed integer version
  gets a clearer error message than a bare 502.
- Structured logging (with the app key explicitly redacted) instead of
  relying on "we just never log headers."

# Security scan (StackHawk HawkScan DAST)

Target: a throwaway backend instance (`MEETBRIEF_DATA_DIR` scratch dir, port 8001, models off, scan-only API token),
configured by `stackhawk.yml` — OpenAPI spec `/openapi.json`, header authentication `X-MeetBrief-Token`,
tech flags limited to Python / JavaScript / SQLite / macOS-Linux. App on the platform: **MeetMind AI** (the project's earlier name; same application ID), env Development.

| Scan | Result |
|---|---|
| First full scan `5c225b38…` | 1 High (SQL Injection), 2 Medium (CSP wildcard, Anti-CSRF), 3 Low (error disclosure ×2, DELETE method) |
| Final full scan `de62a633…` | threshold PASS; 0 open findings (2 triaged false positives), 0 HTTP 500 responses |
| Scan after adding recording upload / finalize / .docx import `fbe40db6…` | threshold PASS; no new findings, 0 HTTP 500; new routes exercised ~200–300× each; no temp files left behind |
| Shared rooms + transcript import, first scan `85656f11…` | threshold PASS; 1 new Low: *Information Leak – Email Address* (room views listed every member's email) → fixed |
| Rooms final full scan `3ae73993…` | threshold PASS; 0 open findings; all 12 room routes, `/api/import/{provider}`, upload-recording, finalize and catch-up exercised |

| Rescan after the rooms bug-fix pass (idle-room expiry, pending heartbeat, startup banner) | **not run**: the StackHawk plan expired (HTTP 402 from the platform). Covered instead by unit tests and a manual review of the changed routes |

## Fixed
* **Owner token shown to others.** The startup banner printed the full-access API token even when the server listens
  on the network (`MEETBRIEF_HOST=0.0.0.0`), so anyone looking at the screen could copy it. It is now only printed for
  a loopback-only server; otherwise the banner shows the file path.
* **Race condition → HTTP 500 (root cause of the "SQL Injection" and "error disclosure" findings).** The shared
  sqlite connection was used concurrently by FastAPI's worker threads; 87 requests failed with
  `sqlite3.InterfaceError`. All `Database` methods are now serialized on a re-entrant lock
  (`backend/database/db.py`); regression test `test_concurrent_db_access_is_serialized`. All SQL was already
  parameterized — injection payloads return a clean 404.
* **Unhandled errors** now return a generic `{"detail": "Internal error"}` (details only in the server log);
  test `test_unhandled_errors_do_not_leak_details`.
* **CSP** for the web app: every directive explicit (`object-src 'none'`, `base-uri`, `form-action`, `font-src`), the
  injected config script allowed by a per-request **nonce** instead of `'unsafe-inline'`, and inline `style=""`
  attributes removed so `style-src` is `'self'` only.

* **Member emails in room views (Low).** `GET /api/rooms/{id}` and heartbeat returned every member's email to every
  member. Emails are now included only for the sharer (who approves people) and for the caller's own entry; test
  `test_member_emails_are_only_shown_to_the_sharer`.

## Triaged as false positive (with notes on the platform)
* **Email address in `/api/me`, the caller's own room entry and `/app/` (Low)**: `/api/me` and the room view return the
  signed-in caller's own email by design; `/app/` contains the static placeholder `priya@college.edu`.
* **Anti-CSRF tokens (Medium)** — the `/app/` forms are handled in JavaScript and never submitted; the API uses a custom
  header token, not cookies, which cross-origin pages cannot send.
* **Insecure HTTP method DELETE (Low)** — DELETE is the intended, authenticated data-deletion endpoint (privacy feature F68).

## Not covered
* Room routes were scanned as a dev identity (`MEETBRIEF_ROOMS_DEV_AUTH=1`, throwaway localhost instance only); Google
  token verification is covered by unit tests with a mocked tokeninfo endpoint, not by the scan.
* The connectors' calls to Google / Zoom / Microsoft APIs were not exercised (no real tokens); they use fixed API hosts.
* `/api/data` (delete-all) was excluded so the seeded data survived; it uses the same auth middleware as every route.
* `DELETE /api/meetings/{id}/notes/{note_id}` was not exercised by the scanner.
* The Chrome extension itself is not a DAST target (it has no server surface).

Re-run: see the commands at the top of `stackhawk.yml`.

"""Google Meet REST API v2 transcript connector.

Requires: a Google Workspace edition with Meet transcripts, the host turned on *Transcripts*, and an OAuth
access token with scope ``https://www.googleapis.com/auth/meetings.space.readonly`` for a user allowed to read
the conference record (typically the organiser or a co-host).

Flow: conferenceRecords (filtered by meeting code) → newest record → transcripts → entries (+ participant names).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import httpx

from backend.connectors import ConnectorError, SegmentIn, check, http_client

API = "https://meet.googleapis.com/v2"
CODE_RE = re.compile(r"([a-z]{3}-[a-z]{4}-[a-z]{3})")


def meeting_code(ref: str) -> str:
    m = CODE_RE.search(ref or "")
    if not m:
        raise ConnectorError("Give a Google Meet link or code like abc-defg-hij")
    return m.group(1)


def _ts(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def fetch(ref: str, access_token: str, client: Optional[httpx.Client] = None) -> tuple[str, list[SegmentIn]]:
    http = http_client(client)
    h = {"Authorization": f"Bearer {access_token}"}
    code = meeting_code(ref)
    recs = check(http.get(f"{API}/conferenceRecords", headers=h, params={"filter": f'space.meeting_code="{code}"'}),
                 "Meet conference records").get("conferenceRecords", [])
    if not recs:
        raise ConnectorError("No finished Google Meet conference found for this code (transcripts appear after the meeting ends)")
    rec = max(recs, key=lambda r: r.get("startTime", ""))
    transcripts = check(http.get(f"{API}/{rec['name']}/transcripts", headers=h), "Meet transcripts").get("transcripts", [])
    ready = [t for t in transcripts if t.get("state") in ("FILE_GENERATED", "ENDED")]
    if not ready:
        raise ConnectorError("This meeting has no transcript yet (the host must turn on Transcripts; it is ready a few minutes after the meeting)")
    transcript = max(ready, key=lambda t: t.get("startTime", ""))
    entries, token = [], None
    while True:
        params = {"pageSize": 100, **({"pageToken": token} if token else {})}
        page = check(http.get(f"{API}/{transcript['name']}/entries", headers=h, params=params), "transcript entries")
        entries.extend(page.get("transcriptEntries", []))
        token = page.get("nextPageToken")
        if not token or len(entries) > 20000:
            break
    names: dict[str, str] = {}
    base = _ts(rec.get("startTime")) or (_ts(entries[0].get("startTime")) if entries else 0) or 0
    out = []
    for e in entries:
        pid = e.get("participant", "")
        if pid and pid not in names:
            try:
                p = check(http.get(f"{API}/{pid}", headers=h), "participant")
                user = p.get("signedinUser") or p.get("anonymousUser") or p.get("phoneUser") or {}
                names[pid] = user.get("displayName") or "Unknown participant"
            except ConnectorError:
                names[pid] = "Unknown participant"
        text = (e.get("text") or "").strip()
        if not text:
            continue
        start, end = _ts(e.get("startTime")), _ts(e.get("endTime"))
        out.append(SegmentIn(text=text, speaker_name=names.get(pid), start_time=(start - base) if start else None,
                             end_time=(end - base) if end else None, language=(e.get("languageCode") or "")[:2] or None,
                             source_type="transcript"))
    title = f"Google Meet {code}"
    return title, out

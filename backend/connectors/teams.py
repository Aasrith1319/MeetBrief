"""Microsoft Teams transcript connector (Microsoft Graph).

Requires: Microsoft 365 with Teams transcription turned on in the meeting, and a delegated Graph access token
with ``OnlineMeetingTranscript.Read.All`` (+ ``OnlineMeetings.Read``) for the organiser (some tenants need admin
consent).

Flow: /me/onlineMeetings?$filter=JoinWebUrl eq '<link>' → transcripts → newest → content as WebVTT
("<v Priya Sharma>text</v>" cues) → parse.
"""
from __future__ import annotations

from typing import Optional

import httpx

from backend.capture.transcript_normalizer import parse_transcript
from backend.connectors import ConnectorError, SegmentIn, check, http_client

API = "https://graph.microsoft.com/v1.0"


def fetch(ref: str, access_token: str, client: Optional[httpx.Client] = None) -> tuple[str, list[SegmentIn]]:
    if "teams.microsoft.com" not in (ref or "") and "teams.live.com" not in (ref or ""):
        raise ConnectorError("Give the Teams meeting join link")
    http = http_client(client)
    h = {"Authorization": f"Bearer {access_token}"}
    safe = ref.replace("'", "''")
    meetings = check(http.get(f"{API}/me/onlineMeetings", headers=h, params={"$filter": f"JoinWebUrl eq '{safe}'"}),
                     "Teams meeting").get("value", [])
    if not meetings:
        raise ConnectorError("Teams meeting not found for this link (only the organiser can read its transcripts)")
    meeting = meetings[0]
    transcripts = check(http.get(f"{API}/me/onlineMeetings/{meeting['id']}/transcripts", headers=h),
                        "Teams transcripts").get("value", [])
    if not transcripts:
        raise ConnectorError("This Teams meeting has no transcript (start transcription in the meeting)")
    t = max(transcripts, key=lambda x: x.get("createdDateTime", ""))
    r = http.get(f"{API}/me/onlineMeetings/{meeting['id']}/transcripts/{t['id']}/content", headers=h,
                 params={"$format": "text/vtt"})
    if r.status_code >= 400:
        raise ConnectorError(f"Could not download the Teams transcript ({r.status_code})")
    return meeting.get("subject") or "Teams meeting", parse_transcript(r.text, "vtt")

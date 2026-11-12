"""Zoom Cloud Recording transcript connector.

Requires: Zoom Pro or higher, cloud recording with *Create audio transcript* enabled by the host, and an OAuth
access token (Zoom app with scope ``cloud_recording:read:list_recording_files`` / ``recording:read``).

Flow: GET /meetings/{id}/recordings → the TRANSCRIPT file (WebVTT with speaker names) → download → parse.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

from backend.capture.transcript_normalizer import parse_transcript
from backend.connectors import ConnectorError, SegmentIn, check, http_client

API = "https://api.zoom.us/v2"


def meeting_id(ref: str) -> str:
    ref = (ref or "").strip()
    m = re.search(r"/(?:j|wc(?:/join)?)/(\d{9,12})", ref) or re.fullmatch(r"(\d[\d ]{8,14}\d)", ref)
    if not m:
        raise ConnectorError("Give a Zoom meeting link or numeric meeting ID")
    return m.group(1).replace(" ", "")


def fetch(ref: str, access_token: str, client: Optional[httpx.Client] = None) -> tuple[str, list[SegmentIn]]:
    http = http_client(client)
    h = {"Authorization": f"Bearer {access_token}"}
    mid = meeting_id(ref)
    data = check(http.get(f"{API}/meetings/{mid}/recordings", headers=h), "Zoom recordings")
    files = [f for f in data.get("recording_files", []) if f.get("file_type") == "TRANSCRIPT" and f.get("status", "completed") == "completed"]
    if not files:
        raise ConnectorError("No Zoom audio transcript for this meeting (the host needs cloud recording with 'Create audio transcript')")
    r = http.get(files[0]["download_url"], headers=h)
    if r.status_code >= 400:
        raise ConnectorError(f"Could not download the Zoom transcript ({r.status_code})")
    vtt = r.text
    # Zoom VTT cues look like "12:01:03.123 --> ...\nPriya Sharma: text"
    return data.get("topic") or f"Zoom meeting {mid}", parse_transcript(vtt, "vtt")

"""Official transcript connectors: fetch the platform's own meeting transcript (which covers the whole meeting,
including anything said before any MeetBrief user joined) with the user's OAuth access token.

Each connector returns a list of SegmentIn. Tokens are used for the single request and never stored.
"""
from __future__ import annotations

from typing import Optional

import httpx

from backend.models import SegmentIn


class ConnectorError(Exception):
    """User-facing error (e.g. no transcript yet, not authorised)."""


def http_client(client: Optional[httpx.Client] = None) -> httpx.Client:
    return client or httpx.Client(timeout=20, follow_redirects=True)


def check(r: httpx.Response, what: str) -> dict:
    if r.status_code in (401, 403):
        raise ConnectorError(f"Not authorised to read {what} (sign in again or ask the host for access)")
    if r.status_code == 404:
        raise ConnectorError(f"{what} not found")
    if r.status_code >= 400:
        raise ConnectorError(f"{what}: provider error {r.status_code}")
    try:
        return r.json()
    except ValueError as exc:
        raise ConnectorError(f"{what}: unexpected response") from exc


__all__ = ["ConnectorError", "SegmentIn", "check", "http_client"]

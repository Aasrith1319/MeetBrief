"""Who is calling the API (principal) and what they may access.

Principals:
* **admin** — the person running this MeetBrief server: the local API token (X-MeetBrief-Token).
  Full access, as before.
* **member** — anyone else with the extension, identified by their Google account:
  ``Authorization: Bearer <Google OAuth access token>`` obtained in the extension with
  ``chrome.identity``. The token is verified with Google (``tokeninfo``): it must be issued to *our*
  OAuth client (``MEETBRIEF_GOOGLE_CLIENT_ID``) and carry a verified email. Members can only reach
  rooms (and the meetings behind them) they have joined.
* **dev member** — for testing rooms on one laptop before a Google OAuth client exists:
  ``X-MeetBrief-Dev-User: Name <email>``, accepted only when ``MEETBRIEF_ROOMS_DEV_AUTH=1``. Never enable it
  on a server other people can reach.

An admin may also send an identity header so the person running the server appears in rooms
under their own name.
"""
from __future__ import annotations

import contextvars
import re
import secrets
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from backend.config import settings


@dataclass(frozen=True)
class Principal:
    admin: bool
    email: Optional[str] = None
    name: Optional[str] = None
    verified: bool = False

    @property
    def is_member(self) -> bool:
        return self.email is not None


ADMIN = Principal(admin=True, email=None, name="MeetBrief owner")
NOBODY = Principal(admin=False, email=None, name=None)
# Fail closed: if the request context were ever lost, the caller is treated as nobody, never as the owner.
current: contextvars.ContextVar[Principal] = contextvars.ContextVar("meetbrief_principal", default=NOBODY)

_token_cache: dict[str, tuple[float, dict]] = {}
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
DEV_USER_RE = re.compile(r"^\s*(?P<name>[^<>]{1,80}?)\s*<(?P<email>[^<>@\s]{1,64}@[^<>@\s]{1,190})>\s*$")


def verify_google_token(token: str, client: Optional[httpx.Client] = None) -> Optional[dict]:
    """Return {email, name} for a valid Google access token issued to our client, else None (cached 5 min)."""
    if not settings.google_client_id or not token or len(token) > 4096:
        return None
    hit = _token_cache.get(token)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        http = client or httpx.Client(timeout=8)
        r = http.get(TOKENINFO_URL, params={"access_token": token})
        if r.status_code != 200:
            return None
        info = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    audience = info.get("aud") or info.get("azp")
    if audience != settings.google_client_id or str(info.get("email_verified")).lower() != "true" or not info.get("email"):
        return None
    if int(info.get("expires_in", "0") or 0) <= 0:
        return None
    ident = {"email": info["email"].lower(), "name": info.get("name") or info["email"].split("@")[0]}
    _token_cache[token] = (time.time() + min(300, int(info["expires_in"])), ident)
    if len(_token_cache) > 5000:
        _token_cache.clear()
    return ident


def identity_from_headers(headers) -> Optional[dict]:
    auth = headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        ident = verify_google_token(auth[7:].strip())
        if ident:
            return {**ident, "verified": True}
    dev = headers.get("X-MeetBrief-Dev-User")
    if dev and settings.rooms_dev_auth:
        m = DEV_USER_RE.match(dev)
        if m:
            return {"email": m.group("email").lower(), "name": m.group("name").strip(), "verified": False}
    return None


def resolve(headers) -> Optional[Principal]:
    """Admin if the local API token matches; member if a valid identity is present; else None."""
    token = headers.get("X-MeetBrief-Token", "")
    is_admin = (not settings.auth_enabled) or (bool(token) and secrets.compare_digest(token, settings.api_token()))
    ident = identity_from_headers(headers)
    if is_admin:
        if ident:
            return Principal(admin=True, email=ident["email"], name=ident["name"], verified=ident["verified"])
        return ADMIN
    if ident:
        return Principal(admin=False, email=ident["email"], name=ident["name"], verified=ident["verified"])
    return None


# Routes a non-admin member may call (meeting routes are further checked against room membership).
MEMBER_ROUTES = [
    re.compile(r"^/api/rooms(?:/.*)?$"),
    re.compile(r"^/api/me$"),
    re.compile(r"^/api/meetings$"),
    re.compile(r"^/api/meetings/[^/]+$"),
    re.compile(r"^/api/meetings/[^/]+/(summary|ask|explain|memory|segments(?:/translations)?|speakers|decisions|tasks(?:/[^/]+)?|"
               r"timeline|notes(?:/[^/]+)?|export|final-summary)$"),
    re.compile(r"^/api/(explain|translate|detect-language|preferences)$"),
    re.compile(r"^/api/import/(google_meet|zoom|teams)$"),
]
MEMBER_FORBIDDEN_METHODS = {("DELETE", re.compile(r"^/api/meetings/[^/]+$")),
                            ("PATCH", re.compile(r"^/api/meetings/[^/]+$")),
                            ("PUT", re.compile(r"^/api/preferences$")),
                            # members write transcript only through /api/rooms/{id}/segments (capturer check)
                            ("POST", re.compile(r"^/api/meetings/[^/]+/segments$"))}


def member_route_allowed(method: str, path: str) -> bool:
    if any(m == method and rx.match(path) for m, rx in MEMBER_FORBIDDEN_METHODS):
        return False
    return any(rx.match(path) for rx in MEMBER_ROUTES)

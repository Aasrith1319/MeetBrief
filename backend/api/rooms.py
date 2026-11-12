"""Shared meeting rooms: late joiners get everything that was said before they arrived.

The first member in a meeting who clicks **Share** registers the meeting link as a room. Every other
member whose extension is in the same meeting (same meeting key from the link) joins the room
automatically and gets:
* a personalised "what you missed" catch-up (everything before *their* join time), then
* the same live recap, decisions and tasks as everyone else.

Only one member captures at a time (the *capturer*); the others stand by and take over automatically
if the capturer leaves or stops sending heartbeats, so the transcript has no duplicates and no gaps.

Access rules (all enforced server-side):
* caller must be signed in (Google, verified by the server; or a dev identity in test mode);
* the extension must report being *in the call* (the link alone is not enough);
* optional: same email domain as the sharer chose, and/or approval by the sharer.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend import auth
from backend.api import service
from backend.config import settings
from backend.database.db import get_db
from backend.models import SegmentIn
from backend.nlp.summarization import summarize

router = APIRouter(prefix="/api/rooms")
_share_lock = threading.Lock()  # two members sharing the same meeting at the same moment must get one room
KEY_RE = re.compile(r"^[a-z_]{2,20}:[\w\-.@]{3,120}$")
DOMAIN_RE = re.compile(r"^[a-z0-9.-]{3,190}$")


class ShareIn(BaseModel):
    meeting_key: str = Field(max_length=150)
    platform: str = Field("unknown", max_length=40)
    title: str = Field("Meeting", max_length=200)
    url: Optional[str] = Field(None, max_length=500)
    in_call: bool = False
    allowed_domain: Optional[str] = Field(None, max_length=190)
    require_approval: bool = False


class JoinIn(BaseModel):
    in_call: bool = False


class HeartbeatIn(BaseModel):
    in_call: bool = True
    captions_visible: bool = False


class RoomSegmentsIn(BaseModel):
    segments: list[SegmentIn] = Field(max_length=500)


class ApproveIn(BaseModel):
    email: str = Field(max_length=254)


def _who() -> auth.Principal:
    p = auth.current.get()
    if not p.email:
        raise HTTPException(401, "Sign in (Google) to use shared rooms")
    return p


def _room(room_id: str) -> dict:
    room = get_db().get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return room


def _member(room: dict, p: auth.Principal, approved: bool = True) -> dict:
    m = get_db().get_member(room["id"], p.email or "")
    if not m or (approved and m["status"] != "approved"):
        raise HTTPException(404, "Room not found")  # same answer as a missing room: no probing
    return m


ROOM_IDLE_SECONDS = 15 * 60  # no member seen this long → the meeting is over (Chrome quit without "leave")


def _final_summary(room: dict) -> str:
    """Final summary of a room's meeting. Runs with server rights: the caller may be a member who is
    not (or no longer) approved, but the room's own summary must still be built and stored."""
    token = auth.current.set(auth.ADMIN)
    try:
        meeting, segments, memory, _ = service.load(room["meeting_id"])
        result = summarize(segments, memory, "catchup", "en")
    finally:
        auth.current.reset(token)
    db = get_db()
    db.cache_set(room["meeting_id"], "final_summary", json.dumps({"summary": result["summary"], "time": time.time()}))
    db.update_meeting(room["meeting_id"], capture_state="ended")
    return result["summary"]


def _live_room(key: str) -> Optional[dict]:
    """Active room for a meeting key, ending it first if it went idle. Meeting links are reused (weekly
    classes, recurring calls), so an old room must not swallow a new meeting on the same link."""
    db = get_db()
    room = db.active_room_for_key(key)
    if not room:
        return None
    seen = [m["last_seen"] or 0 for m in db.room_members(room["id"])]
    last = max(seen + [room["capturer_seen"] or 0, room["created_at"] or 0])
    if time.time() - last > ROOM_IDLE_SECONDS:
        db.update_room(room["id"], status="ended", capturer=None)
        _final_summary(room)
        return None
    return room


def _check_key(key: str) -> str:
    key = key.strip().lower()
    if not KEY_RE.match(key):
        raise HTTPException(400, "Invalid meeting key")
    return key


def _public(room: dict, me: Optional[dict] = None) -> dict:
    db = get_db()
    members = db.room_members(room["id"])
    now = time.time()
    by_email = {m["email"]: m for m in members}
    cap = by_email.get(room["capturer"] or "")
    out = {
        "id": room["id"], "title": room["title"], "platform": room["platform"], "status": room["status"],
        "meeting_id": room["meeting_id"], "created_at": room["created_at"], "shared_by": room["created_by_name"],
        "capturer": cap["name"] if cap else None,
        "capturing": bool(cap and now - (room["capturer_seen"] or 0) <= settings.room_capturer_timeout),
        "allowed_domain": room["allowed_domain"], "require_approval": bool(room["require_approval"]),
        "members": [{"name": m["name"], "role": m["role"], "status": m["status"],
                     "joined_at": m["joined_at"], "in_call": bool(m["in_call"]) and now - (m["last_seen"] or 0) < 60,
                     "verified": bool(m["verified"])} for m in members],
    }
    # emails are personal data: only the sharer (who approves people) sees them; everyone sees their own
    for entry, m in zip(out["members"], members):
        if me and (me["role"] == "sharer" or me["email"] == m["email"]):
            entry["email"] = m["email"]
    if me:
        out["me"] = {"role": me["role"], "status": me["status"], "joined_at": me["joined_at"],
                     "missed_seconds": max(0.0, (me["joined_at"] or 0) - room["created_at"]),
                     "capturer": room["capturer"] == me["email"]}
    return out


def _admit(room: dict, p: auth.Principal) -> str:
    """Enforce the room's rules for a joining member → 'approved' or 'pending'."""
    if room["allowed_domain"] and not (p.email or "").endswith("@" + room["allowed_domain"]):
        raise HTTPException(403, f"This room is limited to @{room['allowed_domain']} accounts")
    if room["require_approval"] and p.email != room["created_by"]:
        existing = get_db().get_member(room["id"], p.email or "")
        return existing["status"] if existing else "pending"
    return "approved"


# ------------------------------------------------------------------ routes
@router.post("/share")
def share(body: ShareIn):
    """First member asks to share the meeting: creates the room (or joins it if someone already shared)."""
    p = _who()
    if not body.in_call:
        raise HTTPException(400, "Join the meeting first: rooms can only be shared from inside the call")
    key = _check_key(body.meeting_key)
    with _share_lock:
        return _share_locked(p, body, key)


def _share_locked(p: auth.Principal, body: ShareIn, key: str):
    db = get_db()
    room = _live_room(key)
    if room:
        return join(room["id"], JoinIn(in_call=True))
    domain = (body.allowed_domain or "").strip().lower().lstrip("@") or None
    if domain and (not DOMAIN_RE.match(domain) or not (p.email or "").endswith("@" + domain)):
        raise HTTPException(400, "Domain restriction must match your own email domain")
    meeting = db.create_meeting(f"{body.title} (shared room)"[:200], body.platform, "room", False, body.url)
    room = db.create_room(key, body.platform, body.title[:200], body.url, meeting["id"], p.email or "", p.name or "",
                          domain, body.require_approval)
    me = db.upsert_member(room["id"], p.email or "", p.name or "", "sharer", "approved", p.verified)
    return _public(db.get_room(room["id"]), me)


@router.get("/lookup")
def lookup(key: str):
    """Is there an active room for the meeting this tab is in? (Minimal info until the caller joins.)"""
    p = _who()
    room = _live_room(_check_key(key))
    if not room:
        return {"exists": False}
    me = get_db().get_member(room["id"], p.email or "")
    return {"exists": True, "id": room["id"], "title": room["title"], "shared_by": room["created_by_name"],
            "member": bool(me), "status": me["status"] if me else None,
            "allowed_domain": room["allowed_domain"], "require_approval": bool(room["require_approval"])}


@router.post("/{room_id}/join")
def join(room_id: str, body: JoinIn):
    p = _who()
    room = _room(room_id)
    if room["status"] != "active":
        raise HTTPException(409, "This room has ended")
    if not body.in_call:
        raise HTTPException(400, "You must be in the meeting to join its room")
    status = _admit(room, p)
    role = "sharer" if p.email == room["created_by"] else "member"
    me = get_db().upsert_member(room_id, p.email or "", p.name or "", role, status, p.verified)
    return _public(get_db().get_room(room_id), me)


@router.get("")
def my_rooms():
    p = _who()
    return [{"id": r["id"], "title": r["title"], "status": r["status"], "meeting_id": r["meeting_id"],
             "created_at": r["created_at"], "shared_by": r["created_by_name"]} for r in get_db().rooms_for_member(p.email or "")]


@router.get("/{room_id}")
def room_info(room_id: str):
    p = _who()
    room = _room(room_id)
    me = _member(room, p, approved=False)
    info = _public(room, me)
    if me["status"] != "approved":  # pending members only see that they are waiting
        return {"id": room["id"], "title": room["title"], "status": room["status"], "shared_by": room["created_by_name"],
                "me": info["me"]}
    return info


@router.post("/{room_id}/heartbeat")
def heartbeat(room_id: str, body: HeartbeatIn):
    """Members ping every ~10 s. Elects the capturer: the current one while alive, otherwise the next member in the
    call (preferring someone whose captions are visible)."""
    p = _who()
    room = _room(room_id)
    me = _member(room, p, approved=False)
    db = get_db()
    now = time.time()
    db.update_member(room_id, p.email or "", last_seen=now, in_call=int(body.in_call), captions=int(body.captions_visible))
    if me["status"] != "approved":  # waiting for the sharer: no capture duties, no room content
        return {"role": "pending", "room": {"id": room["id"], "title": room["title"], "status": room["status"],
                                            "shared_by": room["created_by_name"], "members": []}}
    if room["status"] != "active":
        return {"role": "ended", "room": _public(room, db.get_member(room_id, p.email or ""))}
    cap_email = room["capturer"]
    cap = db.get_member(room_id, cap_email) if cap_email else None
    alive = bool(cap and cap["in_call"] and now - (room["capturer_seen"] or 0) <= settings.room_capturer_timeout)
    if cap_email == p.email:
        if body.in_call:
            db.update_room(room_id, capturer_seen=now)
        else:
            db.update_room(room_id, capturer=None)
    # take over if the capturer is gone, or if it explicitly reported captions off while ours are on
    # (captions IS NULL = not reported yet → no switch)
    elif body.in_call and (not alive or (cap and cap["captions"] == 0 and body.captions_visible)):
        db.update_room(room_id, capturer=p.email, capturer_seen=now)
    room = db.get_room(room_id)
    me = db.get_member(room_id, p.email or "")
    return {"role": "capturer" if room["capturer"] == p.email else "standby", "room": _public(room, me)}


@router.post("/{room_id}/segments")
def room_segments(room_id: str, body: RoomSegmentsIn):
    """Live transcript from the current capturer only. Times are put on the room's shared clock."""
    p = _who()
    room = _room(room_id)
    _member(room, p)
    if room["status"] != "active":
        raise HTTPException(409, "This room has ended")
    if room["capturer"] != p.email:
        raise HTTPException(409, "Another member is capturing this room")
    now = time.time()
    get_db().update_room(room_id, capturer_seen=now)
    ends = [s.end_time for s in body.segments if s.end_time is not None]
    last_end = max(ends) if ends else None
    elapsed = now - room["created_at"]
    items = []
    for s in body.segments:
        lag = (last_end - (s.start_time or last_end)) if last_end is not None else 0.0
        start = max(0.0, elapsed - max(0.0, lag))
        dur = max(0.0, (s.end_time or 0) - (s.start_time or 0)) if s.end_time is not None and s.start_time is not None else 0.0
        items.append(s.model_copy(update={"start_time": start, "end_time": start + dur}))
    added = service.ingest(room["meeting_id"], items, live=True)
    return {"added": len(added)}


@router.post("/{room_id}/audio")
async def room_audio(room_id: str, file: UploadFile = File(...)):
    """Tab-audio backup from the current capturer, merged with the room's captions on the room clock."""
    from backend.api.routes import transcribe_chunk
    p = _who()
    room = _room(room_id)
    _member(room, p)
    if room["status"] != "active":
        raise HTTPException(409, "This room has ended")
    if room["capturer"] != p.email:
        raise HTTPException(409, "Another member is capturing this room")
    data = await file.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(413, "Audio chunk too large")
    received = time.time()
    get_db().update_room(room_id, capturer_seen=received)
    suffix = "." + (file.filename or "chunk.webm").rsplit(".", 1)[-1][:5]
    # the chunk ended when it was received: place it on the room clock
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(transcribe_chunk, room["meeting_id"], data, suffix,
                                   lambda dur: max(0.0, received - room["created_at"] - dur))


@router.get("/{room_id}/catchup")
def catchup(room_id: str, language: str = "en"):
    """'What you missed': everything said before *this member* joined, plus the latest context."""
    p = _who()
    room = _room(room_id)
    me = _member(room, p)
    meeting, segments, memory, _ = service.load(room["meeting_id"])
    missed = max(0.0, (me["joined_at"] or 0) - room["created_at"])
    language = language[:10]
    if missed < 30:
        result = summarize(segments, memory, "catchup", language)
        result["note"] = "You were here from the start — this is the live recap."
    else:
        result = summarize(segments, memory, "catchup", language, to_time=missed)
        result["note"] = (f"What you missed before you joined ({int(missed // 60)} min {int(missed % 60)} s after "
                          f"{room['created_by_name']} shared the room). Live updates continue below.")
    result["missed_seconds"] = missed
    result["room"] = {"title": room["title"], "shared_by": room["created_by_name"]}
    return result


@router.post("/{room_id}/leave")
def leave(room_id: str):
    p = _who()
    room = _room(room_id)
    _member(room, p, approved=False)
    db = get_db()
    db.update_member(room_id, p.email or "", in_call=0, last_seen=time.time())
    if room["capturer"] == p.email:
        db.update_room(room_id, capturer=None)  # next heartbeat from another member takes over
    now = time.time()
    still_in = [m for m in db.room_members(room_id)
                if m["status"] == "approved" and m["in_call"] and now - (m["last_seen"] or 0) < 60]
    if room["status"] == "active" and not still_in:
        # last member left → the meeting is over for MeetBrief: end the room and build the final summary
        db.update_room(room_id, status="ended", capturer=None)
        return {"ok": True, "room_ended": True, "summary": _final_summary(room)}
    return {"ok": True, "room_ended": False}


@router.post("/{room_id}/approve")
def approve(room_id: str, body: ApproveIn):
    p = _who()
    room = _room(room_id)
    if room["created_by"] != p.email and not p.admin:
        raise HTTPException(403, "Only the member who shared the room can approve others")
    if not get_db().get_member(room_id, body.email.lower()):
        raise HTTPException(404, "No such member request")
    get_db().update_member(room_id, body.email.lower(), status="approved")
    return _public(get_db().get_room(room_id), get_db().get_member(room_id, p.email or ""))


@router.post("/{room_id}/end")
def end(room_id: str):
    """The sharer (or the server owner) ends the room: capture stops and the final summary is built."""
    p = _who()
    room = _room(room_id)
    if room["created_by"] != p.email and not p.admin:
        raise HTTPException(403, "Only the member who shared the room can end it")
    get_db().update_room(room_id, status="ended", capturer=None)
    return {"ended": True, "summary": _final_summary(room)}

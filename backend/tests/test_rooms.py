"""Shared rooms: late joiners, capturer handover, and per-room access control (BOLA checks)."""
import time

import pytest

from backend.config import settings

KEY = "google_meet:abc-defg-hij"


@pytest.fixture
def rooms(client, monkeypatch):
    monkeypatch.setattr(settings, "rooms_dev_auth", True)
    monkeypatch.setattr(settings, "room_capturer_timeout", 25.0)

    def as_user(name, email):
        h = {"X-MeetBrief-Dev-User": f"{name} <{email}>", "X-MeetBrief-Token": ""}
        return lambda method, url, **kw: client.request(method, url, headers=h, **kw)
    return client, as_user


def share(u, **extra):
    r = u("POST", "/api/rooms/share", json={"meeting_key": KEY, "platform": "google_meet", "title": "Sprint planning",
                                             "in_call": True, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def lines(*pairs):
    return {"segments": [{"text": t, "speaker_name": s, "start_time": i * 5.0, "end_time": i * 5.0 + 4} for i, (s, t) in enumerate(pairs)]}


def test_late_joiner_gets_what_they_missed(rooms, monkeypatch):
    client, as_user = rooms
    priya = as_user("Priya", "priya@college.edu")
    room = share(priya)
    assert room["me"]["role"] == "sharer" and room["me"]["capturer"]
    r = priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(
        ("Priya", "The database queries are slow."), ("Rahul", "Let's implement indexing first."),
        ("Rahul", "Priya, please complete the indexing changes by Friday.")))
    assert r.json()["added"] == 3

    # you join 10 minutes later (simulate by moving the room's start back)
    from backend.database.db import get_db
    db = get_db()
    db.disk.execute("UPDATE rooms SET created_at = created_at - 600 WHERE id=?", (room["id"],))
    db.disk.execute("UPDATE segments SET start_time = start_time WHERE meeting_id=?", (room["meeting_id"],))
    you = as_user("You", "you@college.edu")
    look = you("GET", f"/api/rooms/lookup?key={KEY}").json()
    assert look["exists"] and look["shared_by"] == "Priya" and not look["member"]
    joined = you("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).json()
    assert joined["me"]["missed_seconds"] > 500 and joined["me"]["role"] == "member"
    cu = you("GET", f"/api/rooms/{room['id']}/catchup").json()
    assert "What you missed" in cu["note"] and "Priya" in cu["summary"] and "Friday" in cu["summary"]
    # members use the normal meeting APIs for the room's meeting
    a = you("POST", f"/api/meetings/{room['meeting_id']}/ask", json={"question": "Who will complete the indexing changes?"})
    assert a.status_code == 200 and "Priya" in a.json()["answer"]


def test_link_alone_is_not_enough_and_rules_are_enforced(rooms):
    client, as_user = rooms
    priya = as_user("Priya", "priya@college.edu")
    room = share(priya, allowed_domain="college.edu", require_approval=True)
    # not in the call
    assert as_user("X", "x@college.edu")("POST", f"/api/rooms/{room['id']}/join", json={"in_call": False}).status_code == 400
    # wrong domain
    assert as_user("Eve", "eve@evil.com")("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).status_code == 403
    # right domain → pending until the sharer approves
    rahul = as_user("Rahul", "rahul@college.edu")
    j = rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).json()
    assert j["me"]["status"] == "pending"
    assert rahul("GET", f"/api/rooms/{room['id']}/catchup").status_code == 404
    assert rahul("GET", f"/api/meetings/{room['meeting_id']}/memory").status_code == 404
    info = rahul("GET", f"/api/rooms/{room['id']}").json()
    assert "members" not in info  # pending members don't see the member list
    # only the sharer may approve
    assert rahul("POST", f"/api/rooms/{room['id']}/approve", json={"email": "rahul@college.edu"}).status_code == 403
    assert priya("POST", f"/api/rooms/{room['id']}/approve", json={"email": "rahul@college.edu"}).status_code == 200
    assert rahul("GET", f"/api/meetings/{room['meeting_id']}/memory").status_code == 200
    # sharing domain must match the sharer's own domain
    other = as_user("Mallory", "m@other.org")
    r = other("POST", "/api/rooms/share", json={"meeting_key": "google_meet:zzz-zzzz-zzz", "in_call": True, "allowed_domain": "college.edu"})
    assert r.status_code == 400


def test_bola_members_cannot_reach_other_meetings(rooms):
    client, as_user = rooms
    # the server owner's own (non-room) meeting
    owner_mid = client.post("/api/meetings", json={"title": "Owner private"}).json()["id"]
    priya = as_user("Priya", "priya@college.edu")
    room = share(priya)
    eve = as_user("Eve", "eve@evil.com")
    for path in [f"/api/meetings/{owner_mid}/memory", f"/api/meetings/{room['meeting_id']}/memory",
                 f"/api/meetings/{room['meeting_id']}/export?format=md", f"/api/rooms/{room['id']}",
                 f"/api/rooms/{room['id']}/catchup"]:
        assert eve("GET", path).status_code == 404, path
    assert eve("POST", f"/api/rooms/{room['id']}/segments", json=lines(("Eve", "injected text here"))).status_code == 404
    assert priya("GET", f"/api/meetings/{owner_mid}/memory").status_code == 404
    # members only list their own rooms' meetings and cannot use owner-only routes
    assert [m["id"] for m in priya("GET", "/api/meetings").json()] == [room["meeting_id"]]
    for method, path in [("DELETE", "/api/data"), ("GET", "/api/search?q=abc"), ("PUT", "/api/preferences"),
                         ("DELETE", f"/api/meetings/{room['meeting_id']}"), ("POST", "/api/upload"),
                         ("POST", f"/api/meetings/{room['meeting_id']}/segments")]:
        assert priya(method, path).status_code == 403, (method, path)
    # no identity at all
    assert client.get("/api/rooms/lookup?key=" + KEY, headers={"X-MeetBrief-Token": ""}).status_code == 401


def test_dev_identities_refused_unless_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "rooms_dev_auth", False)
    r = client.get("/api/me", headers={"X-MeetBrief-Token": "", "X-MeetBrief-Dev-User": "Eve <eve@evil.com>"})
    assert r.status_code == 401


def test_capturer_handover_and_no_duplicates(rooms, monkeypatch):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    assert rahul("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True}).json()["role"] == "standby"
    # standby members cannot push segments (prevents duplicates)
    assert rahul("POST", f"/api/rooms/{room['id']}/segments", json=lines(("Rahul", "duplicate line"))).status_code == 409
    # Priya leaves → Rahul takes over on his next heartbeat
    priya("POST", f"/api/rooms/{room['id']}/leave")
    hb = rahul("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True}).json()
    assert hb["role"] == "capturer" and hb["room"]["capturer"] == "Rahul"
    # a silent capturer (no heartbeat) is replaced after the timeout
    monkeypatch.setattr(settings, "room_capturer_timeout", 0.0)
    time.sleep(0.01)
    assert priya("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).status_code == 200
    assert priya("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True}).json()["role"] == "capturer"


def test_prefers_member_with_captions(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    priya("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True, "captions_visible": False})
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    hb = rahul("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True, "captions_visible": True}).json()
    assert hb["role"] == "capturer"


def test_second_share_joins_existing_room_and_end(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    again = share(rahul)
    assert again["id"] == room["id"] and again["me"]["role"] == "member"
    assert rahul("POST", f"/api/rooms/{room['id']}/end").status_code == 403
    assert priya("POST", f"/api/rooms/{room['id']}/end").json()["ended"]
    assert rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).status_code == 409
    assert as_user("New", "new@college.edu")("GET", f"/api/rooms/lookup?key={KEY}").json() == {"exists": False}


def test_personal_notes_are_private(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    mid = room["meeting_id"]
    priya("POST", f"/api/meetings/{mid}/notes", json={"text": "Priya private note"})
    rahul("POST", f"/api/meetings/{mid}/notes", json={"text": "Rahul private note"})
    assert [n["text"] for n in priya("GET", f"/api/meetings/{mid}/notes").json()] == ["Priya private note"]
    assert [n["text"] for n in rahul("GET", f"/api/meetings/{mid}/notes").json()] == ["Rahul private note"]


def test_google_token_verification(monkeypatch):
    """Tokens must be issued to OUR client id and carry a verified email (tokeninfo mocked)."""
    import httpx

    from backend import auth

    monkeypatch.setattr(settings, "google_client_id", "ours.apps.googleusercontent.com")
    auth._token_cache.clear()

    def handler(request):
        tok = request.url.params["access_token"]
        data = {"good": {"aud": "ours.apps.googleusercontent.com", "email": "Priya@College.edu", "email_verified": "true", "expires_in": "3000"},
                "other": {"aud": "someone-else", "email": "p@x.com", "email_verified": "true", "expires_in": "3000"},
                "unverified": {"aud": "ours.apps.googleusercontent.com", "email": "p@x.com", "email_verified": "false", "expires_in": "3000"}}
        return httpx.Response(200, json=data[tok]) if tok in data else httpx.Response(400, json={"error": "invalid"})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert auth.verify_google_token("good", http)["email"] == "priya@college.edu"
    assert auth.verify_google_token("other", http) is None
    assert auth.verify_google_token("unverified", http) is None
    assert auth.verify_google_token("garbage", http) is None


def test_room_ends_when_last_member_leaves(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(("Priya", "Let's ship the release on Friday.")))
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    assert priya("POST", f"/api/rooms/{room['id']}/leave").json()["room_ended"] is False
    last = rahul("POST", f"/api/rooms/{room['id']}/leave").json()
    assert last["room_ended"] and "Friday" in last["summary"]
    assert "Friday" in rahul("GET", f"/api/meetings/{room['meeting_id']}/final-summary").json()["summary"]


def test_member_emails_are_only_shown_to_the_sharer(rooms):
    client, as_user = rooms
    priya, rahul, asha = (as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu"),
                          as_user("Asha", "asha@college.edu"))
    room = share(priya)
    for u in (rahul, asha):
        assert u("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).status_code == 200
    seen = {m["name"]: m.get("email") for m in rahul("GET", f"/api/rooms/{room['id']}").json()["members"]}
    assert seen == {"Priya": None, "Rahul": "rahul@college.edu", "Asha": None}
    seen = {m["name"]: m.get("email") for m in priya("GET", f"/api/rooms/{room['id']}").json()["members"]}
    assert seen["Asha"] == "asha@college.edu" and seen["Rahul"] == "rahul@college.edu"


def test_idle_room_is_not_reused_for_the_next_meeting_on_the_same_link(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    old = share(priya)
    # everyone vanished without "leave" (Chrome quit) and the link is reused next week
    from backend.database.db import get_db
    db = get_db()
    db.disk.execute("UPDATE rooms SET created_at = created_at - 7*86400, capturer_seen = 0 WHERE id=?", (old["id"],))
    db.disk.execute("UPDATE room_members SET last_seen = last_seen - 7*86400 WHERE room_id=?", (old["id"],))
    assert rahul("GET", f"/api/rooms/lookup?key={KEY}").json() == {"exists": False}
    assert db.get_room(old["id"])["status"] == "ended"
    new = share(rahul)
    assert new["id"] != old["id"] and new["me"]["missed_seconds"] < 5


def test_pending_member_learns_about_approval_through_heartbeat(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya, require_approval=True)
    assert rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True}).json()["me"]["status"] == "pending"
    hb = rahul("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True, "captions_visible": True})
    assert hb.status_code == 200 and hb.json()["role"] == "pending" and hb.json()["room"]["members"] == []
    assert priya("POST", f"/api/rooms/{room['id']}/approve", json={"email": "rahul@college.edu"}).status_code == 200
    hb = rahul("POST", f"/api/rooms/{room['id']}/heartbeat", json={"in_call": True, "captions_visible": True})
    assert hb.json()["role"] in ("standby", "capturer")


def test_pending_member_leaving_last_still_builds_the_final_summary(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya, require_approval=True)
    priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(("Priya", "We will ship on Friday.")))
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    assert priya("POST", f"/api/rooms/{room['id']}/leave").json()["room_ended"] is True  # only approved members count
    r = rahul("POST", f"/api/rooms/{room['id']}/leave")
    assert r.status_code == 200


def test_capturers_own_speech_is_named_not_you(rooms):
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(("You", "Let us ship on Friday."), ("Rahul", "Sounds good.")))
    segs = rahul("GET", f"/api/meetings/{room['meeting_id']}/segments").json()["segments"]
    assert [s["speaker_name"] for s in segs] == ["Priya", "Rahul"]


def test_two_members_sharing_at_the_same_time_get_one_room(rooms):
    import concurrent.futures
    client, as_user = rooms
    users = [as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")]
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        ids = list(ex.map(lambda u: share(u)["id"], users))
    assert ids[0] == ids[1]


def test_auto_share_is_on_by_default(client):
    assert client.get("/api/preferences").json()["auto_share"] is True


def test_redrawn_captions_are_not_stored_twice(rooms):
    client, as_user = rooms
    priya = as_user("Priya", "priya@college.edu")
    room = share(priya)
    batch = lines(("Rahul", "I am going to tell you about my NLP project today."), ("Priya", "Can you elaborate everything?"))
    priya("POST", f"/api/rooms/{room['id']}/segments", json=batch)
    priya("POST", f"/api/rooms/{room['id']}/segments", json=batch)  # caption area redrawn → same lines again
    priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(("Rahul", "Yes."), ("Rahul", "Yes.")))
    segs = priya("GET", f"/api/meetings/{room['meeting_id']}/segments").json()["segments"]
    assert [s["text"] for s in segs].count("I am going to tell you about my NLP project today.") == 1
    assert len(segs) == 3 or len(segs) == 4  # short "Yes." lines are not treated as duplicates


def test_tab_audio_fills_what_captions_missed(rooms, monkeypatch):
    """Hybrid capture: captions first; the audio backup only adds lines the captions do not already contain."""
    import backend.api.routes as routes
    client, as_user = rooms
    priya, rahul = as_user("Priya", "priya@college.edu"), as_user("Rahul", "rahul@college.edu")
    room = share(priya)
    rahul("POST", f"/api/rooms/{room['id']}/join", json={"in_call": True})
    priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(("Rahul", "We decided to use BART for the summaries.")))
    fake = {"language": "en", "audio": None, "segments": [
        {"start": 0.0, "end": 3.0, "text": "we decided to use bart for the summaries"},      # captions have it
        {"start": 3.0, "end": 6.0, "text": "Ravi will finish the slides by Friday."}]}       # captions missed it
    monkeypatch.setattr(routes, "transcribe_bytes", lambda *a, **k: dict(fake))
    monkeypatch.setattr(routes, "diarization_available", lambda: {"available": False, "reason": "off in tests"})
    r = rahul("POST", f"/api/rooms/{room['id']}/audio", files={"file": ("chunk.webm", b"x" * 3000, "audio/webm")})
    assert r.status_code == 409  # only the capturer records
    r = priya("POST", f"/api/rooms/{room['id']}/audio", files={"file": ("chunk.webm", b"x" * 3000, "audio/webm")})
    assert r.status_code == 200 and r.json()["covered_by_captions"] == 1
    texts = [s["text"] for s in rahul("GET", f"/api/meetings/{room['meeting_id']}/segments").json()["segments"]]
    assert texts == ["We decided to use BART for the summaries.", "Ravi will finish the slides by Friday."]


def test_audio_only_meeting_keeps_every_line():
    from backend.api.service import merge_audio_with_captions
    from backend.models import SegmentIn
    items = [SegmentIn(text="Hello everyone, let us start.", source_type="audio")]
    kept, dropped = merge_audio_with_captions([], items)
    assert kept == items and dropped == 0


def test_audio_segment_mixing_known_and_new_sentences_keeps_only_the_new_one():
    from backend.api.service import merge_audio_with_captions
    from backend.models import Segment, SegmentIn
    caps = [Segment(segment_id="S1", idx=0, meeting_id="m", text="We decided to use BART for the summaries.",
                    start_time=0, end_time=3, speaker_name="Rahul", source_type="caption")]
    audio = [SegmentIn(text="We decided to use BART for the summaries. Ravi will finish the slides by Friday.", source_type="audio")]
    kept, dropped = merge_audio_with_captions(caps, audio)
    assert dropped == 1 and [k.text for k in kept] == ["Ravi will finish the slides by Friday."]


def test_audio_voices_learn_names_from_matching_caption_lines(rooms, monkeypatch):
    """Speaker 2's audio duplicates Rahul's caption lines twice → Speaker 2 = Rahul, also for audio-only lines."""
    import backend.api.routes as routes
    client, as_user = rooms
    priya = as_user("Priya", "priya@college.edu")
    room = share(priya)
    priya("POST", f"/api/rooms/{room['id']}/segments", json=lines(
        ("Rahul", "The database queries are really slow today."), ("Rahul", "We should add an index on the orders table.")))
    chunks = iter([
        [("The database queries are really slow today.", "SPEAKER_00")],  # duplicate of Rahul's caption
        [("We should add an index on the orders table.", "SPEAKER_00"),                    # duplicate of Rahul's caption
         ("I will benchmark the queries tomorrow morning.", "SPEAKER_00")],                  # missed by captions
    ])
    def fake_transcribe(*a, **k):
        segs = next(chunks)
        return {"language": "en", "audio": [0.0] * 16000, "segments": [
            {"start": i * 3.0, "end": i * 3.0 + 3, "text": t, "_spk": spk} for i, (t, spk) in enumerate(segs)]}
    monkeypatch.setattr(routes, "transcribe_bytes", fake_transcribe)
    monkeypatch.setattr(routes, "diarization_available", lambda: {"available": True, "reason": None})
    monkeypatch.setattr(routes, "diarize", lambda audio, segs, cents: ([s["_spk"] for s in segs], cents))
    up = lambda: priya("POST", f"/api/rooms/{room['id']}/audio", files={"file": ("c.webm", b"x" * 3000, "audio/webm")}).json()
    first, second = up(), up()
    assert first["voices_named"] == {} and second["voices_named"] == {"Speaker 1": "Rahul"}
    segs = priya("GET", f"/api/meetings/{room['meeting_id']}/segments").json()["segments"]
    audio_line = next(s for s in segs if s["text"].startswith("I will benchmark"))
    assert audio_line["speaker_name"] == "Rahul"


def test_late_audio_lines_are_read_in_speaking_order():
    from backend.api.service import time_order
    from backend.models import Segment
    mk = lambda i, t, src: Segment(segment_id=f"S{i}", idx=i, meeting_id="m", text=f"line {i}", start_time=t, end_time=t + 2,
                                   source_type=src)
    segs = [mk(0, 0, "caption"), mk(1, 20, "caption"), mk(2, 10, "audio")]  # audio line arrived late
    assert [s.segment_id for s in time_order(segs)] == ["S0", "S2", "S1"]
    captions_only = [mk(0, 5, "caption"), mk(1, 1, "caption")]
    assert time_order(captions_only) == captions_only  # untouched without audio

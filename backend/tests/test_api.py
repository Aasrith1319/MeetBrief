"""End-to-end API tests (FastAPI TestClient)."""
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / "datasets" / "sample_transcripts"


def upload(client, name="demo_indexing.txt", private=False):
    with open(SAMPLES / name, "rb") as fh:
        r = client.post("/api/upload", files={"file": (name, fh, "text/plain")}, data={"private": str(private).lower()})
    assert r.status_code == 200, r.text
    return r.json()["meeting"]


def test_auth_required(client):
    r = client.get("/api/meetings", headers={"X-MeetBrief-Token": "wrong"})
    assert r.status_code == 401
    assert client.get("/api/health", headers={"X-MeetBrief-Token": ""}).status_code == 200


def test_full_flow(client):
    m = upload(client)
    mid = m["id"]
    assert m["segment_count"] == 5
    mem = client.get(f"/api/meetings/{mid}/memory").json()["memory"]
    assert mem["participants"] == ["Rahul", "Priya", "Arjun"]

    s = client.post(f"/api/meetings/{mid}/summary", json={"mode": "catchup"}).json()
    assert "Priya" in s["summary"] and s["evidence"]

    a = client.post(f"/api/meetings/{mid}/ask", json={"question": "Why did the team choose indexing first?"}).json()
    assert a["insufficient_evidence"]

    e = client.post(f"/api/meetings/{mid}/explain", json={"text": "database indexing", "style": "example"}).json()
    assert "Example" in e["explanation"]

    sp = client.get(f"/api/meetings/{mid}/speakers").json()["speakers"]
    rahul = next(x for x in sp if x["speaker"] == "Rahul")
    assert rahul["decisions"] and rahul["tasks_assigned"]

    tasks = client.get(f"/api/meetings/{mid}/tasks").json()["tasks"]
    tid = tasks[0]["task_id"]
    t = client.patch(f"/api/meetings/{mid}/tasks/{tid}", json={"status": "completed"}).json()
    assert t["status"] == "completed"
    # user correction survives re-analysis
    assert client.get(f"/api/meetings/{mid}/tasks").json()["tasks"][0]["status"] == "completed"

    tl = client.get(f"/api/meetings/{mid}/timeline").json()
    assert {e["type"] for e in tl["events"]} >= {"topic", "decision", "task"}

    hits = client.get(f"/api/meetings/{mid}/segments", params={"q": "slow database"}).json()
    assert hits["semantic"] and "database" in hits["segments"][0]["text"].lower()

    n = client.post(f"/api/meetings/{mid}/notes", json={"text": "Ask Priya about benchmarks"}).json()
    assert client.get(f"/api/meetings/{mid}/notes").json()[0]["id"] == n["id"]

    for fmt in ["md", "json", "txt", "pdf"]:
        r = client.get(f"/api/meetings/{mid}/export", params={"format": fmt})
        assert r.status_code == 200 and len(r.content) > 100
    md = client.get(f"/api/meetings/{mid}/export", params={"format": "md"}).text
    assert "Personal notes (user-written)" in md and "Ask Priya" in md

    assert client.get("/api/search", params={"q": "caching"}).json()


def test_live_caption_ingest_dedupes(client):
    mid = client.post("/api/meetings", json={"title": "Live", "platform": "google_meet"}).json()["id"]
    client.post(f"/api/meetings/{mid}/segments", json={"segments": [{"text": "We need", "speaker_name": "Rahul"}]})
    client.post(f"/api/meetings/{mid}/segments", json={"segments": [{"text": "We need to improve the response time.", "speaker_name": "Rahul"}]})
    client.post(f"/api/meetings/{mid}/segments", json={"segments": [{"text": "We need to improve the response time.", "speaker_name": "Rahul"}]})
    client.post(f"/api/meetings/{mid}/segments", json={"segments": [{"text": "Agreed.", "speaker_name": "Priya"}]})
    segs = client.get(f"/api/meetings/{mid}/segments").json()["segments"]
    assert [s["text"] for s in segs] == ["We need to improve the response time.", "Agreed."]


def test_speaker_mapping(client):
    mid = upload(client, "unlabeled_speakers.vtt")["id"]
    sp = client.get(f"/api/meetings/{mid}/speakers").json()["speakers"]
    assert all(not s["identity_known"] for s in sp)
    client.put(f"/api/meetings/{mid}/speakers", json={"speaker_id": "Speaker 2", "speaker_name": "Nikhil"})
    sp = client.get(f"/api/meetings/{mid}/speakers").json()["speakers"]
    assert any(s["speaker"] == "Nikhil" and s["identity_known"] for s in sp)
    assert client.get(f"/api/meetings/{mid}/tasks").json()["tasks"][0]["owner"] == "Nikhil"


def test_private_mode_not_on_disk(client):
    from backend.database.db import get_db

    m = upload(client, private=True)
    assert m["private"]
    db = get_db()
    assert db.disk.execute("SELECT COUNT(*) FROM meetings WHERE id=?", (m["id"],)).fetchone()[0] == 0
    assert db.disk.execute("SELECT COUNT(*) FROM segments WHERE meeting_id=?", (m["id"],)).fetchone()[0] == 0
    assert client.get(f"/api/meetings/{m['id']}/memory").status_code == 200


def test_deletion_and_retention(client):
    import time

    from backend.database.db import get_db

    mid = upload(client)["id"]
    assert client.delete(f"/api/meetings/{mid}/transcript").status_code == 200
    assert client.get(f"/api/meetings/{mid}").json()["segment_count"] == 0
    assert client.delete(f"/api/meetings/{mid}").status_code == 200
    assert client.get(f"/api/meetings/{mid}").status_code == 404

    old = upload(client)["id"]
    get_db().disk.execute("UPDATE meetings SET updated_at=? WHERE id=?", (time.time() - 40 * 86400, old))
    client.put("/api/preferences", json={"values": {"retention_days": 30}})
    assert client.get(f"/api/meetings/{old}").status_code == 404

    upload(client)
    assert client.delete("/api/data").json()["deleted_meetings"] >= 1
    assert client.get("/api/meetings").json() == []


def test_upload_validation(client):
    r = client.post("/api/upload", files={"file": ("x.txt", b"", "text/plain")})
    assert r.status_code == 400
    r = client.post("/api/upload", files={"file": ("x.json", b"{not json", "application/json")})
    assert r.status_code == 400


def test_audio_without_asr_or_bad_audio(client):
    mid = client.post("/api/meetings", json={"title": "Audio"}).json()["id"]
    r = client.post(f"/api/meetings/{mid}/audio", files={"file": ("chunk.webm", b"not audio" * 400, "audio/webm")})
    assert r.status_code in (422, 501)


def test_models_fallback_is_reported(client):
    h = client.get("/api/health").json()
    assert h["models"]["enabled"] is False and "MEETBRIEF_MODELS=off" in h["models"]["reason"]
    assert set(h["models"]["tasks"]) == {"summary", "mt", "gen", "qa", "embedding", "nli", "ner", "speaker"}
    assert client.get("/api/privacy").json()["external_processing"] is False


def test_pdf_export_with_indic_text(client):
    mid = upload(client, "telugu_english.txt")["id"]
    r = client.get(f"/api/meetings/{mid}/export", params={"format": "pdf"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    from backend.export import fonts
    assert "te" in fonts.registered()  # bundled Noto Sans Telugu


def test_concurrent_db_access_is_serialized(tmp_path):
    """Regression for the HawkScan finding: concurrent reads on the shared sqlite connection returned HTTP 500."""
    import threading

    from backend.database.db import Database

    db = Database(str(tmp_path / "c.sqlite3"))
    m = db.create_meeting("t", "x", "x", False)
    errors = []

    def work():
        try:
            for _ in range(200):
                db.get_meeting(m["id"])
                db.get_meeting("000000000000")
                db.list_meetings()
                db.add_note(m["id"], "n", None)
        except Exception as exc:  # pragma: no cover - only on regression
            errors.append(repr(exc))

    threads = [threading.Thread(target=work) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_unhandled_errors_do_not_leak_details():
    from fastapi.testclient import TestClient

    from backend.main import app

    def boom():
        raise RuntimeError("secret internal detail")

    app.add_api_route("/api/__boom", boom)
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/api/__boom", headers={"X-MeetBrief-Token": "test-token"})
        assert r.status_code == 500 and r.json() == {"detail": "Internal error"}
        assert "secret" not in r.text
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/api/__boom"]


def _docx_bytes(paragraphs):
    import io
    import zipfile

    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_docx_meet_transcript_import(client):
    """Google Meet transcript docs put timestamps on their own lines before each turn."""
    doc = _docx_bytes(["00:00:05", "Priya Sharma: The database queries are slow.", "00:00:20",
                       "Rahul: Let's implement indexing first.", "00:00:31", "Rahul: Priya, please finish it by Friday."])
    r = client.post("/api/upload", files={"file": ("meet.docx", doc, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 200, r.text
    mid = r.json()["meeting"]["id"]
    segs = client.get(f"/api/meetings/{mid}/segments").json()["segments"]
    assert [s["speaker_name"] for s in segs] == ["Priya Sharma", "Rahul", "Rahul"]
    assert segs[1]["start_time"] == 20
    tasks = client.get(f"/api/meetings/{mid}/tasks").json()["tasks"]
    assert tasks[0]["owner"] == "Priya" and tasks[0]["deadline"] == "Friday"
    bad = client.post("/api/upload", files={"file": ("x.docx", b"not a zip", "application/octet-stream")})
    assert bad.status_code == 400


def test_finalize_builds_final_summary(client):
    mid = upload(client)["id"]
    assert client.get(f"/api/meetings/{mid}/final-summary").status_code == 404
    r = client.post(f"/api/meetings/{mid}/finalize", json={}).json()
    assert r["counts"]["action_items"] == 1 and "Priya" in r["summary"]
    assert client.get(f"/api/meetings/{mid}").json()["capture_state"] == "ended"
    assert "Priya" in client.get(f"/api/meetings/{mid}/final-summary").json()["summary"]


def test_upload_recording_validation(client):
    r = client.post("/api/upload-recording", files={"file": ("notes.exe", b"x" * 100, "application/octet-stream")})
    assert r.status_code in (400, 501)


def test_upload_recording_transcribes_in_background(client):
    import time

    import pytest

    pytest.importorskip("faster_whisper")
    wav = Path(__file__).resolve().parents[2] / "datasets" / "evaluation_data" / "audio" / "three_speakers.wav"
    with open(wav, "rb") as fh:
        r = client.post("/api/upload-recording", files={"file": ("standup.wav", fh, "audio/wav")}, data={"title": "Recorded standup"})
    assert r.status_code == 200, r.text
    mid = r.json()["meeting"]["id"]
    for _ in range(60):  # TestClient runs background tasks before returning, but poll defensively
        m = client.get(f"/api/meetings/{mid}").json()
        if m["capture_state"] in ("ready",) or m["capture_state"].startswith("error"):
            break
        time.sleep(1)
    assert m["capture_state"] == "ready" and m["segment_count"] >= 6
    tasks = client.get(f"/api/meetings/{mid}/tasks").json()["tasks"]
    assert any("compress" in t["task_text"].lower() for t in tasks)


def test_auto_mode_preferences(client):
    p = client.get("/api/preferences").json()
    assert p["auto_capture"] is False and p["auto_enable_captions"] is True
    p = client.put("/api/preferences", json={"values": {"auto_capture": True, "consent_acknowledged": True}}).json()
    assert p["auto_capture"] is True

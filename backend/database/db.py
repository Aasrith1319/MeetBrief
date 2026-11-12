"""SQLite storage with private mode and retention (F60, F64, F67, F68, F72).

Two connections share one schema:
* the on-disk database for normal meetings;
* an in-memory database for *private-mode* meetings, which are never written
  to disk and disappear when the session ends or the server stops.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Optional

from backend.config import settings
from backend.models import Segment

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY, title TEXT, platform TEXT, url TEXT, source_type TEXT,
    private INTEGER DEFAULT 0, created_at REAL, updated_at REAL, capture_state TEXT DEFAULT 'idle'
);
CREATE TABLE IF NOT EXISTS segments (
    meeting_id TEXT, segment_id TEXT, idx INTEGER, start_time REAL, end_time REAL, text TEXT,
    language TEXT, language_confidence REAL, speaker_id TEXT, speaker_name TEXT, source_type TEXT,
    confidence REAL, flags TEXT, PRIMARY KEY (meeting_id, segment_id)
);
CREATE INDEX IF NOT EXISTS idx_segments_meeting ON segments(meeting_id, idx);
CREATE TABLE IF NOT EXISTS task_overrides (
    meeting_id TEXT, task_id TEXT, status TEXT, owner TEXT, deadline TEXT, updated_at REAL,
    PRIMARY KEY (meeting_id, task_id)
);
CREATE TABLE IF NOT EXISTS speaker_map (
    meeting_id TEXT, speaker_id TEXT, speaker_name TEXT, source TEXT, PRIMARY KEY (meeting_id, speaker_id)
);
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY, meeting_id TEXT, text TEXT, segment_id TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS cache (
    meeting_id TEXT, key TEXT, value TEXT, created_at REAL, PRIMARY KEY (meeting_id, key)
);
CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY, meeting_key TEXT, platform TEXT, title TEXT, url TEXT, meeting_id TEXT,
    created_by TEXT, created_by_name TEXT, created_at REAL, status TEXT DEFAULT 'active',
    capturer TEXT, capturer_seen REAL, allowed_domain TEXT, require_approval INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rooms_key ON rooms(meeting_key, status);
CREATE TABLE IF NOT EXISTS room_members (
    room_id TEXT, email TEXT, name TEXT, role TEXT, status TEXT, joined_at REAL, last_seen REAL,
    in_call INTEGER DEFAULT 1, captions INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, PRIMARY KEY (room_id, email)
);
"""

DEFAULT_PREFS = {
    "summary_language": "en", "explanation_language": "en", "detail_level": "quick", "difficulty": "beginner",
    "retention_days": settings.default_retention_days, "private_mode_default": False, "consent_acknowledged": False,
    # automatic mode (opt-in): start caption capture when you join a call, switch Meet captions on,
    # stop + build the final summary when you leave
    "auto_capture": False, "auto_enable_captions": True,
    # shared rooms: share every meeting you join without asking (default: ask with a notification)
    "auto_share": True,  # first participant with MeetBrief shares the meeting automatically
    "audio_backup": True,  # record tab audio alongside captions; audio fills what captions miss
}


class Database:
    def __init__(self, path: Optional[str] = None):
        settings.ensure_dirs()
        self._lock = threading.RLock()
        self.disk = sqlite3.connect(path or str(settings.db_path), check_same_thread=False)
        self.mem = sqlite3.connect(":memory:", check_same_thread=False)
        for conn in (self.disk, self.mem):
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA foreign_keys=ON")
            cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
            if "owner" not in cols:  # migration: personal notes are private to their author
                conn.execute("ALTER TABLE notes ADD COLUMN owner TEXT")
            if "text_en" not in {r[1] for r in conn.execute("PRAGMA table_info(segments)")}:
                conn.execute("ALTER TABLE segments ADD COLUMN text_en TEXT")  # migration: English of non-English lines
        self.disk.execute("PRAGMA journal_mode=WAL")

    # ------------------------------------------------------------- routing
    def _conn(self, meeting_id: str) -> sqlite3.Connection:
        row = self.mem.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        return self.mem if row else self.disk

    # ------------------------------------------------------------ meetings
    def create_meeting(self, title: str, platform: str, source_type: str, private: bool, url: Optional[str] = None) -> dict:
        mid = uuid.uuid4().hex[:12]
        now = time.time()
        conn = self.mem if private else self.disk
        with self._lock, conn:
            conn.execute("INSERT INTO meetings (id, title, platform, url, source_type, private, created_at, updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?)", (mid, title, platform, url, source_type, int(private), now, now))
        return self.get_meeting(mid)  # type: ignore[return-value]

    def get_meeting(self, meeting_id: str) -> Optional[dict]:
        conn = self._conn(meeting_id)
        row = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["private"] = bool(d["private"])
        d["segment_count"] = conn.execute("SELECT COUNT(*) FROM segments WHERE meeting_id=?", (meeting_id,)).fetchone()[0]
        return d

    def list_meetings(self, query: Optional[str] = None) -> list[dict]:
        out = []
        for conn in (self.mem, self.disk):
            if query:
                rows = conn.execute(
                    "SELECT DISTINCT m.* FROM meetings m LEFT JOIN segments s ON s.meeting_id=m.id "
                    "WHERE m.title LIKE ? OR s.text LIKE ? ORDER BY m.updated_at DESC", (f"%{query}%", f"%{query}%")).fetchall()
            else:
                rows = conn.execute("SELECT * FROM meetings ORDER BY updated_at DESC").fetchall()
            for r in rows:
                d = dict(r)
                d["private"] = bool(d["private"])
                d["segment_count"] = conn.execute("SELECT COUNT(*) FROM segments WHERE meeting_id=?", (d["id"],)).fetchone()[0]
                out.append(d)
        return sorted(out, key=lambda d: -d["updated_at"])

    def search_history(self, query: str, limit: int = 30) -> list[dict]:
        """F64: search retained meeting records."""
        out = []
        for conn in (self.mem, self.disk):
            rows = conn.execute(
                "SELECT s.*, m.title FROM segments s JOIN meetings m ON m.id=s.meeting_id WHERE s.text LIKE ? "
                "ORDER BY m.updated_at DESC, s.idx LIMIT ?", (f"%{query}%", limit)).fetchall()
            out.extend(dict(r) for r in rows)
        return out[:limit]

    def update_meeting(self, meeting_id: str, **fields: Any) -> None:
        allowed = {k: v for k, v in fields.items() if k in {"title", "capture_state", "platform", "url", "source_type"}}
        allowed["updated_at"] = time.time()
        conn = self._conn(meeting_id)
        cols = ", ".join(f"{k}=?" for k in allowed)
        with self._lock, conn:
            conn.execute(f"UPDATE meetings SET {cols} WHERE id=?", (*allowed.values(), meeting_id))

    def delete_meeting(self, meeting_id: str) -> bool:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            cur = conn.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
            for rid in [r[0] for r in conn.execute("SELECT id FROM rooms WHERE meeting_id=?", (meeting_id,))]:
                conn.execute("DELETE FROM room_members WHERE room_id=?", (rid,))
            conn.execute("DELETE FROM rooms WHERE meeting_id=?", (meeting_id,))
            for table in ("segments", "task_overrides", "speaker_map", "notes", "cache"):
                conn.execute(f"DELETE FROM {table} WHERE meeting_id=?", (meeting_id,))
        if conn is self.disk:
            self.disk.execute("VACUUM") if cur.rowcount else None
        return cur.rowcount > 0

    def delete_transcript(self, meeting_id: str) -> None:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            for table in ("segments", "task_overrides", "speaker_map", "cache"):
                conn.execute(f"DELETE FROM {table} WHERE meeting_id=?", (meeting_id,))
        self.update_meeting(meeting_id)

    def delete_all(self) -> int:
        n = 0
        for conn in (self.mem, self.disk):
            with self._lock, conn:
                n += conn.execute("DELETE FROM meetings").rowcount
                conn.execute("DELETE FROM rooms")
                conn.execute("DELETE FROM room_members")
                for table in ("segments", "task_overrides", "speaker_map", "notes", "cache"):
                    conn.execute(f"DELETE FROM {table}")
        self.disk.execute("VACUUM")
        return n

    def purge_expired(self) -> int:
        days = int(self.get_preferences().get("retention_days") or 0)
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        ids = [r[0] for r in self.disk.execute("SELECT id FROM meetings WHERE updated_at < ?", (cutoff,)).fetchall()]
        for mid in ids:
            self.delete_meeting(mid)
        return len(ids)

    # ------------------------------------------------------------ segments
    def add_segments(self, meeting_id: str, segments: list[Segment]) -> None:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            conn.executemany(
                "INSERT OR REPLACE INTO segments (meeting_id, segment_id, idx, start_time, end_time, text, language, "
                "language_confidence, speaker_id, speaker_name, source_type, confidence, flags, text_en) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(meeting_id, s.segment_id, s.idx, s.start_time, s.end_time, s.text, s.language, s.language_confidence,
                  s.speaker_id, s.speaker_name, s.source_type, s.confidence, json.dumps(s.flags), s.text_en)
                 for s in segments])
            conn.execute("UPDATE meetings SET updated_at=? WHERE id=?", (time.time(), meeting_id))

    def get_segments(self, meeting_id: str) -> list[Segment]:
        rows = self._conn(meeting_id).execute("SELECT * FROM segments WHERE meeting_id=? ORDER BY idx", (meeting_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["flags"] = json.loads(d["flags"] or "[]")
            out.append(Segment(**d))
        return out

    def next_index(self, meeting_id: str) -> int:
        row = self._conn(meeting_id).execute("SELECT MAX(idx) FROM segments WHERE meeting_id=?", (meeting_id,)).fetchone()
        return (row[0] + 1) if row and row[0] is not None else 0

    def last_segment(self, meeting_id: str) -> Optional[Segment]:
        segs = self._conn(meeting_id).execute(
            "SELECT * FROM segments WHERE meeting_id=? ORDER BY idx DESC LIMIT 1", (meeting_id,)).fetchall()
        if not segs:
            return None
        d = dict(segs[0])
        d["flags"] = json.loads(d["flags"] or "[]")
        return Segment(**d)

    def update_segment_text(self, meeting_id: str, segment_id: str, text: str, end_time: Optional[float]) -> None:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            conn.execute("UPDATE segments SET text=?, end_time=COALESCE(?, end_time) WHERE meeting_id=? AND segment_id=?",
                         (text, end_time, meeting_id, segment_id))

    # ---------------------------------------------------- user corrections
    def set_task_override(self, meeting_id: str, task_id: str, status=None, owner=None, deadline=None) -> None:
        conn = self._conn(meeting_id)
        existing = self.task_overrides(meeting_id).get(task_id, {})
        with self._lock, conn:
            conn.execute("INSERT OR REPLACE INTO task_overrides VALUES (?,?,?,?,?,?)",
                         (meeting_id, task_id, status or existing.get("status"), owner or existing.get("owner"),
                          deadline or existing.get("deadline"), time.time()))

    def task_overrides(self, meeting_id: str) -> dict[str, dict]:
        rows = self._conn(meeting_id).execute("SELECT * FROM task_overrides WHERE meeting_id=?", (meeting_id,)).fetchall()
        return {r["task_id"]: dict(r) for r in rows}

    def set_speaker(self, meeting_id: str, speaker_id: str, name: str, source: str = "user") -> None:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            conn.execute("INSERT OR REPLACE INTO speaker_map VALUES (?,?,?,?)", (meeting_id, speaker_id, name, source))

    def speaker_sources(self, meeting_id: str) -> dict[str, str]:
        """speaker_id -> how the name was set ("user" or "voice-match")."""
        rows = self._conn(meeting_id).execute("SELECT speaker_id, source FROM speaker_map WHERE meeting_id=?",
                                              (meeting_id,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def speaker_map(self, meeting_id: str) -> dict[str, str]:
        rows = self._conn(meeting_id).execute("SELECT speaker_id, speaker_name FROM speaker_map WHERE meeting_id=?",
                                              (meeting_id,)).fetchall()
        return {r[0]: r[1] for r in rows}

    # --------------------------------------------------------------- notes
    def add_note(self, meeting_id: str, text: str, segment_id: Optional[str], owner: Optional[str] = None) -> dict:
        nid = uuid.uuid4().hex[:10]
        conn = self._conn(meeting_id)
        with self._lock, conn:
            conn.execute("INSERT INTO notes (id, meeting_id, text, segment_id, created_at, owner) VALUES (?,?,?,?,?,?)",
                         (nid, meeting_id, text, segment_id, time.time(), owner))
        return {"id": nid, "meeting_id": meeting_id, "text": text, "segment_id": segment_id}

    def notes(self, meeting_id: str, owner: Optional[str] = None) -> list[dict]:
        """Personal notes: each member sees only their own (owner=None is the server owner's notes)."""
        rows = self._conn(meeting_id).execute(
            "SELECT id, meeting_id, text, segment_id, created_at FROM notes WHERE meeting_id=? AND owner IS ? "
            "ORDER BY created_at", (meeting_id, owner)).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, meeting_id: str, note_id: str, owner: Optional[str] = None) -> None:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            conn.execute("DELETE FROM notes WHERE meeting_id=? AND id=? AND owner IS ?", (meeting_id, note_id, owner))

    # --------------------------------------------------------------- cache
    def cache_get(self, meeting_id: str, key: str) -> Optional[str]:
        row = self._conn(meeting_id).execute("SELECT value FROM cache WHERE meeting_id=? AND key=?", (meeting_id, key)).fetchone()
        return row[0] if row else None

    def cache_set(self, meeting_id: str, key: str, value: str) -> None:
        conn = self._conn(meeting_id)
        with self._lock, conn:
            conn.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (meeting_id, key, value, time.time()))

    # --------------------------------------------------------------- rooms
    def create_room(self, meeting_key: str, platform: str, title: str, url: Optional[str], meeting_id: str,
                    email: str, name: str, allowed_domain: Optional[str], require_approval: bool) -> dict:
        rid = uuid.uuid4().hex[:12]
        with self._lock, self.disk:
            self.disk.execute(
                "INSERT INTO rooms (id, meeting_key, platform, title, url, meeting_id, created_by, created_by_name, "
                "created_at, status, capturer, capturer_seen, allowed_domain, require_approval) "
                "VALUES (?,?,?,?,?,?,?,?,?, 'active', ?, ?, ?, ?)",
                (rid, meeting_key, platform, title, url, meeting_id, email, name, time.time(), email, time.time(),
                 allowed_domain, int(require_approval)))
        return self.get_room(rid)  # type: ignore[return-value]

    def get_room(self, room_id: str) -> Optional[dict]:
        row = self.disk.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        return dict(row) if row else None

    def active_room_for_key(self, meeting_key: str) -> Optional[dict]:
        row = self.disk.execute("SELECT * FROM rooms WHERE meeting_key=? AND status='active' ORDER BY created_at DESC LIMIT 1",
                                (meeting_key,)).fetchone()
        return dict(row) if row else None

    def room_for_meeting(self, meeting_id: str) -> Optional[dict]:
        row = self.disk.execute("SELECT * FROM rooms WHERE meeting_id=? ORDER BY created_at DESC LIMIT 1", (meeting_id,)).fetchone()
        return dict(row) if row else None

    def update_room(self, room_id: str, **fields) -> None:
        allowed = {k: v for k, v in fields.items() if k in {"status", "capturer", "capturer_seen", "title"}}
        if not allowed:
            return
        cols = ", ".join(f"{k}=?" for k in allowed)
        with self._lock, self.disk:
            self.disk.execute(f"UPDATE rooms SET {cols} WHERE id=?", (*allowed.values(), room_id))

    def upsert_member(self, room_id: str, email: str, name: str, role: str, status: str, verified: bool) -> dict:
        now = time.time()
        with self._lock, self.disk:
            existing = self.disk.execute("SELECT * FROM room_members WHERE room_id=? AND email=?", (room_id, email)).fetchone()
            if existing:  # keep the first join time: it defines what this member missed
                self.disk.execute("UPDATE room_members SET name=?, last_seen=?, in_call=1, verified=? WHERE room_id=? AND email=?",
                                  (name, now, int(verified), room_id, email))
            else:
                # captions = NULL until the member's first heartbeat says whether captions are visible
                self.disk.execute("INSERT INTO room_members VALUES (?,?,?,?,?,?,?,1,NULL,?)",
                                  (room_id, email, name, role, status, now, now, int(verified)))
        return self.get_member(room_id, email)  # type: ignore[return-value]

    def get_member(self, room_id: str, email: str) -> Optional[dict]:
        row = self.disk.execute("SELECT * FROM room_members WHERE room_id=? AND email=?", (room_id, email)).fetchone()
        return dict(row) if row else None

    def update_member(self, room_id: str, email: str, **fields) -> None:
        allowed = {k: v for k, v in fields.items() if k in {"status", "last_seen", "in_call", "captions", "role"}}
        if not allowed:
            return
        cols = ", ".join(f"{k}=?" for k in allowed)
        with self._lock, self.disk:
            self.disk.execute(f"UPDATE room_members SET {cols} WHERE room_id=? AND email=?", (*allowed.values(), room_id, email))

    def room_members(self, room_id: str) -> list[dict]:
        rows = self.disk.execute("SELECT * FROM room_members WHERE room_id=? ORDER BY joined_at", (room_id,)).fetchall()
        return [dict(r) for r in rows]

    def rooms_for_member(self, email: str) -> list[dict]:
        rows = self.disk.execute("SELECT r.* FROM rooms r JOIN room_members m ON m.room_id=r.id WHERE m.email=? "
                                 "AND m.status='approved' ORDER BY r.created_at DESC", (email,)).fetchall()
        return [dict(r) for r in rows]

    def is_room_member(self, meeting_id: str, email: str) -> bool:
        row = self.disk.execute("SELECT 1 FROM rooms r JOIN room_members m ON m.room_id=r.id WHERE r.meeting_id=? "
                                "AND m.email=? AND m.status='approved'", (meeting_id, email)).fetchone()
        return row is not None

    # --------------------------------------------------------- preferences
    def get_preferences(self) -> dict:
        prefs = dict(DEFAULT_PREFS)
        for k, v in self.disk.execute("SELECT key, value FROM preferences").fetchall():
            prefs[k] = json.loads(v)
        return prefs

    def set_preferences(self, values: dict) -> dict:
        with self._lock, self.disk:
            for k, v in values.items():
                if k in DEFAULT_PREFS:
                    self.disk.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", (k, json.dumps(v)))
        return self.get_preferences()


def _serialized(fn):
    """sqlite3 connections are not safe for concurrent use. FastAPI runs sync endpoints in a thread pool, and the
    in-memory (private-mode) database can only be shared through one connection, so every public method —
    reads included — takes the re-entrant lock. (Found by the HawkScan DAST run: concurrent reads raised
    "sqlite3.InterfaceError: bad parameter or other API misuse" and returned HTTP 500.)"""
    import functools

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)
    return wrapper


for _name, _fn in list(vars(Database).items()):
    if callable(_fn) and not _name.startswith("__"):
        setattr(Database, _name, _serialized(_fn))


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def set_db(db: Database) -> None:
    global _db
    _db = db

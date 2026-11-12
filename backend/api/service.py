"""Service layer: loads a meeting's transcript + memory with caching, ingests segments."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Optional

from fastapi import HTTPException

from backend import auth
from backend.capture.transcript_normalizer import dedupe_caption_updates, normalize_text, to_segments
from backend.database.db import get_db
from backend.memory.meeting_state import build_memory
from backend.models import MeetingMemory, Segment, SegmentIn
from backend.nlp.language_detection import detect_language
from backend.nlp.speakers import apply_speaker_map
from backend.rag.retrieval import MeetingRetriever

_cache: dict[str, tuple[str, list[Segment], MeetingMemory, MeetingRetriever]] = {}
_lock = threading.Lock()


def require_meeting(meeting_id: str) -> dict:
    """Return the meeting if it exists AND the caller may access it.

    The server owner (admin token) sees everything; a member only sees meetings behind rooms they joined.
    Non-members get the same 404 as a missing meeting, so meeting ids cannot be probed."""
    meeting = get_db().get_meeting(meeting_id)
    principal = auth.current.get()
    if not meeting or (not principal.admin and not get_db().is_room_member(meeting_id, principal.email or "")):
        raise HTTPException(404, "Meeting not found")
    return meeting


def notes_owner():
    """Personal notes belong to their author: None = the server owner, else the member's email."""
    p = auth.current.get()
    return None if p.admin else p.email


def time_order(segments: list[Segment]) -> list[Segment]:
    """Hybrid capture stores tab-audio lines 15-20 s after the captions around them; read the meeting in the order
    things were said (stable: same-time lines keep their arrival order). Only applied when audio is mixed with other
    sources and every line has a time."""
    kinds = {s.source_type for s in segments}
    if "audio" not in kinds or len(kinds) < 2 or any(s.start_time is None for s in segments):
        return segments
    return sorted(segments, key=lambda s: (s.start_time, s.idx))


def _fingerprint(meeting_id: str, segments: list[Segment]) -> str:
    db = get_db()
    payload = json.dumps([len(segments), segments[-1].segment_id if segments else None,
                          segments[-1].text if segments else None, db.task_overrides(meeting_id),
                          db.speaker_map(meeting_id)], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


def load(meeting_id: str) -> tuple[dict, list[Segment], MeetingMemory, MeetingRetriever]:
    meeting = require_meeting(meeting_id)
    db = get_db()
    segments = time_order(apply_speaker_map(db.get_segments(meeting_id), db.speaker_map(meeting_id)))
    # the English models (summaries, Q&A, decisions, tasks) read the English of non-English speech
    segments = [s.model_copy(update={"text": s.text_en, "original_text": s.text}) if s.text_en and s.text_en != s.text
                else s for s in segments]
    fp = _fingerprint(meeting_id, segments)
    with _lock:
        hit = _cache.get(meeting_id)
        if hit and hit[0] == fp:
            return meeting, hit[1], hit[2], hit[3]
    memory = build_memory(meeting_id, segments, db.task_overrides(meeting_id),
                          cache_get=lambda k: db.cache_get(meeting_id, k),
                          cache_set=lambda k, v: db.cache_set(meeting_id, k, v))
    retriever = MeetingRetriever(segments)
    with _lock:
        _cache[meeting_id] = (fp, segments, memory, retriever)
    return meeting, segments, memory, retriever


def invalidate(meeting_id: str) -> None:
    with _lock:
        _cache.pop(meeting_id, None)


# How Meet / Zoom / Teams label the capturing user's own speech in captions (English, Hindi, Telugu UIs)
SELF_LABELS = {"you", "you (presenting)", "you (presentation)", "me", "आप", "మీరు"}


def name_self_speaker(items: list[SegmentIn]) -> list[SegmentIn]:
    """Captions call the capturing person "You". In a shared transcript that is ambiguous (it means whoever was
    capturing), so replace it with the signed-in capturer's name when we know it."""
    name = (auth.current.get().name or "").strip()
    if not name or name == "MeetBrief owner":
        return items
    out = []
    for it in items:
        if (it.speaker_name or "").strip().lower() in SELF_LABELS:
            it = it.model_copy(update={"speaker_name": name, "speaker_id": None})
        out.append(it)
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^\w ]+", "", re.sub(r"\s+", " ", text or "")).strip().lower()


def drop_repeats(recent: list[Segment], items: list[SegmentIn], min_chars: int = 15) -> list[SegmentIn]:
    """Live captions can arrive twice: the meeting app redraws its caption area (e.g. when someone leaves) and the
    same lines are read again. Skip an incoming line whose text the same speaker already said in the recent
    transcript. Short lines ("yes", "okay") are kept, since people really do repeat them."""
    seen = [((r.speaker_name or r.speaker_id or "").lower(), _norm(r.text)) for r in recent]
    out = []
    for it in items:
        spk, t = (it.speaker_name or it.speaker_id or "").lower(), _norm(it.text)
        if len(t) >= min_chars and any(spk == s2 and (t == t2 or t in t2) for s2, t2 in seen):
            continue
        out.append(it)
        seen.append((spk, t))
    return out


_WORD = re.compile(r"[\w']+", re.UNICODE)


_STOP = set("the and for with that this will have has are was were you your they them our not but can from all about "
            "what when then than there their here just also into over some any been being would could should shall "
            "its it's let's lets yes okay".split())


def _content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if len(w) >= 3 and w not in _STOP]


def merge_audio_with_captions(existing: list[Segment], audio_items: list[SegmentIn], window: int = 40,
                              threshold: float = 0.6, matches: Optional[list] = None) -> tuple[list[SegmentIn], int]:
    """Hybrid capture: captions are the primary transcript (real names, includes the capturer's own voice); tab
    audio is a backup. An audio sentence whose content words are mostly (>= 60 %) in ONE recent caption line is a
    duplicate of something the captions have and is dropped; anything else was missed by the captions and is kept.
    If the meeting has no captions at all, every audio line is kept. Returns (kept, number_dropped)."""
    captions = [s for s in existing if (s.source_type or "caption") != "audio"][-window:]
    if not captions:
        return audio_items, 0
    cap_words = [(c, set(_content_words(c.text))) for c in captions]
    def best_match(sent: str):
        ws = set(_content_words(sent))
        best, overlap = None, 0.0
        for c, cw in cap_words:
            o = len(ws & cw) / len(ws) if ws else 0.0
            if o > overlap:
                best, overlap = c, o
        return (best if ws and overlap >= threshold else None)

    kept, dropped = [], 0
    for it in audio_items:
        # speech in another language whose English matches English captions (e.g. Meet's translated captions)
        en_sents = [x for x in re.split(r"(?<=[.!?])\s+", (it.text_en or "").strip()) if x]
        if en_sents and all(best_match(x) is not None for x in en_sents):
            dropped += 1
            continue
        # Whisper may merge several sentences into one segment: judge each sentence on its own, and compare it with
        # ONE caption line at a time (words scattered over different lines are not a duplicate)
        sentences = [x for x in re.split(r"(?<=[.!?।])\s+", (it.text or "").strip()) if x]
        new_parts = []
        for sent in sentences:
            best = best_match(sent)
            if best is not None:
                dropped += 1
                if matches is not None and it.speaker_id and best is not None and best.speaker_name:
                    matches.append((it.speaker_id, best.speaker_name))  # this voice said that caption line
            else:
                new_parts.append(sent)
        if len(new_parts) == len(sentences):
            kept.append(it)
        elif new_parts:
            kept.append(it.model_copy(update={"text": " ".join(new_parts), "text_en": None}))
    return kept, dropped


VOICE_MIN_VOTES = 2


def learn_voice_names(meeting_id: str, matches: list) -> dict[str, str]:
    """Voice → name: when an audio line duplicates a caption line, the caption's speaker name belongs to that
    audio speaker id (e.g. "Speaker 2" = "Priya"). After VOICE_MIN_VOTES agreeing matches (and a 2/3 majority) the
    name is stored as an automatic speaker mapping, so later audio-only lines of that voice show the real name.
    A name the user set by hand is never overwritten."""
    db = get_db()
    if not matches:
        return {}
    try:
        votes = json.loads(db.cache_get(meeting_id, "voice_votes") or "{}")
    except ValueError:
        votes = {}
    for spk, name in matches:
        votes.setdefault(spk, {})
        votes[spk][name] = votes[spk].get(name, 0) + 1
    db.cache_set(meeting_id, "voice_votes", json.dumps(votes))
    sources, learned = db.speaker_sources(meeting_id), {}
    for spk, counts in votes.items():
        name, n = max(counts.items(), key=lambda kv: kv[1])
        if n >= VOICE_MIN_VOTES and n * 3 >= 2 * sum(counts.values()) and sources.get(spk) != "user":
            if db.speaker_map(meeting_id).get(spk) != name:
                db.set_speaker(meeting_id, spk, name, source="voice-match")
                learned[spk] = name
    if learned:
        invalidate(meeting_id)
    return learned


def ingest(meeting_id: str, items: list[SegmentIn], live: bool = False) -> list[Segment]:
    """Store new segments. Live caption updates are de-duplicated against the last stored segment."""
    items = name_self_speaker(items)
    db = get_db()
    last: Optional[Segment] = db.last_segment(meeting_id) if live else None
    if live:
        items = dedupe_caption_updates(items, previous=None)
        if last and items:
            first = items[0]
            same_speaker = (first.speaker_name or first.speaker_id) == (last.speaker_name or last.speaker_id)
            new_text = normalize_text(first.text)
            if same_speaker and new_text.lower().startswith(last.text.lower()) and len(new_text) > len(last.text):
                db.update_segment_text(meeting_id, last.segment_id, new_text, first.end_time)  # caption grew
                items = items[1:]
            elif same_speaker and last.text.lower().endswith(new_text.lower()):
                items = items[1:]  # duplicate update
        items = drop_repeats(db.get_segments(meeting_id)[-30:], items)
    segments = to_segments(meeting_id, items, start_idx=db.next_index(meeting_id))
    if segments:
        db.add_segments(meeting_id, segments)
    invalidate(meeting_id)
    return segments


def detect(text: str) -> dict:
    return detect_language(text).as_dict()

"""REST API consumed by the Chrome extension side panel."""
from __future__ import annotations

import json
import re
import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.concurrency import run_in_threadpool

from backend.api import service
from backend.capture.transcript_normalizer import parse_transcript
from backend.config import settings
from backend.database.db import get_db
from backend.export import exporter
from backend import auth
from backend.hf import models as hf
from backend.memory.decision_history import decision_chains
from pydantic import BaseModel, Field

from backend.models import (AskRequest, ExplainRequest, MeetingCreate, NoteIn, PreferencesIn, SegmentIn, SegmentsIn,
                            SpeakerMapping, SummaryRequest, TaskUpdate, TranscriptText, TranslateRequest)
from backend.nlp.decision_extraction import decision_changes
from backend.nlp.simplification import explain
from backend.nlp.speakers import speaker_statements, who_said_what
from backend.nlp.summarization import summarize
from backend.nlp.language_detection import language_name
from backend.nlp.translation import translate
from backend.rag.answer_generation import answer_question
from backend.rag.embeddings import dense_available
from backend.speech.alignment import friendly_label
from backend.speech.diarization import diarization_available, diarize
from backend.speech.speech_recognition import ASRUnavailable, asr_available, transcribe_bytes, transcribe_path

router = APIRouter(prefix="/api")

CONSENT_GUIDANCE = {
    "summary": "Only capture meetings you are allowed to capture. Tell participants when MeetBrief AI is processing the meeting.",
    "points": [
        "MeetBrief reads accessible captions/transcripts, or meeting-tab audio only after you explicitly start tab capture.",
        "No separate microphone permission is requested; only the meeting tab you choose is captured.",
        "A capture indicator is always visible while capture is active; you can pause or stop at any time.",
        "Raw audio chunks are deleted as soon as they are transcribed.",
        "Private mode keeps the meeting in memory only — nothing is written to disk.",
        "Retention: meetings older than the configured number of days are deleted automatically; you can delete any meeting or all data at any time.",
        "All processing runs on this machine: Hugging Face models are downloaded once and executed locally; no transcript or audio is sent to any external AI service.",
        "Recording or transcribing others may require their consent under local law and your organisation's or platform's policies.",
    ],
}


# ---------------------------------------------------------------- status
@router.get("/health")
def health():
    return {"status": "ok", "time": time.time(), "models": hf.status(), "asr": asr_available(),
            "diarization": diarization_available(), "dense_embeddings": dense_available(),
            "auth_required": settings.auth_enabled,
            "rooms": {"google_client_id": settings.google_client_id or None, "dev_identities": settings.rooms_dev_auth}}


@router.get("/privacy")
def privacy():
    return {**CONSENT_GUIDANCE, "external_processing": False}


@router.get("/preferences")
def get_preferences():
    return get_db().get_preferences()


@router.put("/preferences")
def put_preferences(body: PreferencesIn):
    prefs = get_db().set_preferences(body.values)
    get_db().purge_expired()
    return prefs


# -------------------------------------------------------------- meetings
@router.get("/meetings")
def list_meetings(q: Optional[str] = None):
    p = auth.current.get()
    if p.admin:
        return get_db().list_meetings(q)
    ids = {r["meeting_id"] for r in get_db().rooms_for_member(p.email or "")}
    return [m for m in get_db().list_meetings(q) if m["id"] in ids]


@router.get("/me")
def me():
    p = auth.current.get()
    return {"admin": p.admin, "email": p.email, "name": p.name, "verified": p.verified,
            "rooms_enabled": bool(settings.google_client_id) or settings.rooms_dev_auth,
            "google_sign_in": bool(settings.google_client_id), "dev_identities": settings.rooms_dev_auth}


@router.post("/meetings")
def create_meeting(body: MeetingCreate):
    return get_db().create_meeting(body.title[:200], body.platform, body.source_type, body.private, body.url)


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: str):
    return service.require_meeting(meeting_id)


@router.patch("/meetings/{meeting_id}")
def update_meeting(meeting_id: str, body: dict):
    service.require_meeting(meeting_id)
    get_db().update_meeting(meeting_id, **{k: str(v)[:200] for k, v in body.items()})
    return service.require_meeting(meeting_id)


@router.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: str):
    service.require_meeting(meeting_id)
    get_db().delete_meeting(meeting_id)
    service.invalidate(meeting_id)
    return {"deleted": meeting_id}


@router.delete("/meetings/{meeting_id}/transcript")
def delete_transcript(meeting_id: str):
    service.require_meeting(meeting_id)
    get_db().delete_transcript(meeting_id)
    service.invalidate(meeting_id)
    return {"deleted_transcript": meeting_id}


@router.delete("/data")
def delete_all_data():
    n = get_db().delete_all()
    service._cache.clear()
    return {"deleted_meetings": n}


@router.get("/search")
def search_history(q: str = Query(..., min_length=2, max_length=200)):
    return get_db().search_history(q)


# ------------------------------------------------------------- ingestion
@router.post("/meetings/{meeting_id}/segments")
def add_segments(meeting_id: str, body: SegmentsIn):
    service.require_meeting(meeting_id)
    added = service.ingest(meeting_id, body.segments, live=True)
    return {"added": [s.model_dump() for s in added], "count": get_db().get_meeting(meeting_id)["segment_count"]}


@router.post("/meetings/{meeting_id}/transcript")
def add_transcript(meeting_id: str, body: TranscriptText):
    service.require_meeting(meeting_id)
    if len(body.text.encode()) > settings.max_upload_bytes:
        raise HTTPException(413, "Transcript too large")
    try:
        items = parse_transcript(body.text, body.format)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"Could not parse transcript: {exc}")
    added = service.ingest(meeting_id, items)
    return {"added": len(added), "meeting": get_db().get_meeting(meeting_id)}


@router.post("/upload")
async def upload_transcript(file: UploadFile = File(...), title: Optional[str] = Form(None),
                            private: bool = Form(False), meeting_id: Optional[str] = Form(None)):
    """F05: upload an existing transcript (.txt, .vtt, .srt, .json, or .docx such as a Google Meet transcript doc)."""
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "Transcript too large")
    if (file.filename or "").lower().endswith(".docx"):
        try:
            content = docx_text(raw)
        except ValueError as exc:
            raise HTTPException(400, f"Could not read .docx: {exc}")
    else:
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "Transcript must be UTF-8 text (or a .docx file)")
    try:
        items = parse_transcript(content, filename=file.filename)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"Could not parse transcript: {exc}")
    if not items:
        raise HTTPException(400, "No transcript lines found")
    if meeting_id:
        meeting = service.require_meeting(meeting_id)
    else:
        name = title or re.sub(r"\.[a-z0-9]+$", "", file.filename or "Uploaded transcript", flags=re.I)
        meeting = get_db().create_meeting(name[:200], "upload", "upload", private)
    added = service.ingest(meeting["id"], items)
    return {"meeting": get_db().get_meeting(meeting["id"]), "added": len(added)}


def docx_text(raw: bytes) -> str:
    """Plain text of a .docx (one line per paragraph) using only the standard library."""
    import io
    import zipfile
    from xml.etree import ElementTree as ET

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 50 * 1024 * 1024:  # zip-bomb guard
                raise ValueError("document too large")
            xml = z.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("not a Word document") from exc
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ET.fromstring(xml)
    lines = []
    for p in root.iter(f"{ns}p"):
        text = "".join(t.text or "" for t in p.iter(f"{ns}t")).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


RECORDING_EXT = {".mp3", ".m4a", ".mp4", ".wav", ".webm", ".ogg", ".oga", ".opus", ".mkv", ".mov", ".aac", ".flac"}


def _process_recording(meeting_id: str, path: str, language: Optional[str]) -> None:
    """Background job: transcribe a whole uploaded recording, separate speakers, store segments, delete the file."""
    import os

    db = get_db()
    try:
        db.update_meeting(meeting_id, capture_state="processing_recording")
        asr = transcribe_path(path, language or None)
        labels: list = [None] * len(asr["segments"])
        order: dict = {}
        if diarization_available()["available"]:
            labels, _ = diarize(asr["audio"], asr["segments"], [])
        asr["audio"] = None
        items = [SegmentIn(text=seg["text"], text_en=seg.get("text_en"), start_time=seg["start"], end_time=seg["end"],
                           speaker_id=friendly_label(raw, order), language=seg.get("language") or asr["language"],
                           source_type="audio", confidence=seg.get("confidence"))
                 for seg, raw in zip(asr["segments"], labels)]
        service.ingest(meeting_id, items)
        db.update_meeting(meeting_id, capture_state="ready")
    except Exception as exc:  # report in the meeting state; details only in the log
        import logging
        logging.getLogger("meetbrief").exception("Recording processing failed")
        db.update_meeting(meeting_id, capture_state="error: could not transcribe recording"
                          if not isinstance(exc, ASRUnavailable) else "error: speech recognition not installed")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@router.post("/upload-recording")
async def upload_recording(background: BackgroundTasks, file: UploadFile = File(...), title: Optional[str] = Form(None),
                           private: bool = Form(False), language: Optional[str] = Form(None)):
    """Late-joiner support: import a full meeting recording (e.g. the host's Google Meet recording) and transcribe it
    in the background. Poll GET /api/meetings/{id} until capture_state is "ready"."""
    import os
    import tempfile

    if not asr_available()["available"]:
        raise HTTPException(501, "Speech recognition requires faster-whisper: pip install -r requirements-audio.txt")
    ext = os.path.splitext((file.filename or "").lower())[1]
    if ext not in RECORDING_EXT:
        raise HTTPException(400, f"Unsupported recording type {ext or '(none)'}; use one of {', '.join(sorted(RECORDING_EXT))}")
    fd, path = tempfile.mkstemp(suffix=ext, prefix="meetbrief_rec_")
    size = 0
    with os.fdopen(fd, "wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_recording_bytes:
                fh.close()
                os.remove(path)
                raise HTTPException(413, "Recording too large")
            fh.write(chunk)
    name = title or re.sub(r"\.[a-z0-9]+$", "", file.filename or "Recording", flags=re.I)
    meeting = get_db().create_meeting(name[:200], "recording", "audio", private)
    get_db().update_meeting(meeting["id"], capture_state="processing_recording")
    background.add_task(_process_recording, meeting["id"], path, language)
    return {"meeting": get_db().get_meeting(meeting["id"]), "status": "processing"}


class ImportIn(BaseModel):
    meeting_ref: str = Field(max_length=500)        # meeting link or code / ID
    access_token: str = Field(min_length=10, max_length=4096)  # user's OAuth token for the provider; never stored
    meeting_id: Optional[str] = Field(None, max_length=40)   # replace the transcript of this meeting (e.g. a room)
    title: Optional[str] = Field(None, max_length=200)
    private: bool = False


@router.post("/import/{provider}")
def import_official_transcript(provider: str, body: ImportIn):
    """Late-joiner fix that needs nobody to have captured anything: pull the platform's own transcript
    (Google Meet API, Zoom cloud recording, Microsoft Teams via Graph). It replaces any live-captured
    transcript of `meeting_id`, because the official one is complete from the first minute."""
    from backend.connectors import ConnectorError, google_meet, teams, zoom

    connectors = {"google_meet": google_meet.fetch, "zoom": zoom.fetch, "teams": teams.fetch}
    if provider not in connectors:
        raise HTTPException(404, "Unknown provider; use google_meet, zoom or teams")
    p = auth.current.get()
    if not p.admin and not body.meeting_id:
        raise HTTPException(400, "Members can only import into a shared room's meeting (meeting_id)")
    if body.meeting_id:
        service.require_meeting(body.meeting_id)
    try:
        title, items = connectors[provider](body.meeting_ref, body.access_token)
    except ConnectorError as exc:
        raise HTTPException(422, str(exc))
    if not items:
        raise HTTPException(422, "The transcript is empty")
    db = get_db()
    if body.meeting_id:
        meeting_id = body.meeting_id
        db.delete_transcript(meeting_id)
    else:
        meeting_id = db.create_meeting((body.title or title)[:200], provider, "official_transcript", body.private)["id"]
    added = service.ingest(meeting_id, items)
    db.update_meeting(meeting_id, source_type="official_transcript")
    return {"meeting": db.get_meeting(meeting_id), "added": len(added), "provider": provider}


@router.post("/meetings/{meeting_id}/finalize")
def finalize_meeting(meeting_id: str, body: Optional[dict] = None):
    """Called when the meeting ends (user left / tab closed): build and store the final catch-up summary."""
    meeting, segments, memory, _ = service.load(meeting_id)
    language = str((body or {}).get("language") or get_db().get_preferences().get("summary_language") or "en")[:10]
    result = summarize(segments, memory, "catchup", language)
    get_db().update_meeting(meeting_id, capture_state="ended")
    get_db().cache_set(meeting_id, "final_summary", json.dumps({"summary": result["summary"], "time": time.time(),
                                                               "language": language}))
    return {"summary": result["summary"], "engine": result["engine"],
            "counts": {"segments": len(segments), "decisions": len([d for d in memory.decisions if d.status != "proposed"]),
                       "action_items": len(memory.action_items),
                       "open_questions": len([q for q in memory.open_questions if q.status != "answered"])}}


@router.get("/meetings/{meeting_id}/final-summary")
def final_summary(meeting_id: str):
    service.require_meeting(meeting_id)
    raw = get_db().cache_get(meeting_id, "final_summary")
    if not raw:
        raise HTTPException(404, "No final summary yet")
    return json.loads(raw)


@router.post("/meetings/{meeting_id}/audio")
async def add_audio(meeting_id: str, file: UploadFile = File(...), offset: float = Form(0.0),
                    language: Optional[str] = Form(None)):
    """F04 / workflow L: transcribe an authorised meeting-tab audio chunk (deleted after processing)."""
    service.require_meeting(meeting_id)
    data = await file.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(413, "Audio chunk too large")
    suffix = "." + (file.filename or "chunk.webm").rsplit(".", 1)[-1][:5]
    # Whisper takes seconds: run it in a worker thread so heartbeats and live captions are not blocked meanwhile
    return await run_in_threadpool(transcribe_chunk, meeting_id, data, suffix, offset, language)


def transcribe_chunk(meeting_id: str, data: bytes, suffix: str, offset, language: Optional[str] = None) -> dict:
    """Whisper + diarization for one audio chunk, then merge with captions: lines the captions already have are
    dropped, lines the captions missed are added. `offset` may be a callable(duration_s) -> start offset."""
    try:
        asr = transcribe_bytes(data, suffix=suffix, language=language or None)
    except ASRUnavailable as exc:
        raise HTTPException(501, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Could not decode/transcribe audio chunk: {exc}")
    if callable(offset):
        audio = asr.get("audio")
        offset = offset(len(audio) / 16000.0 if audio is not None else 15.0)
    segments = asr["segments"]
    db = get_db()
    try:
        state = json.loads(db.cache_get(meeting_id, "diarization") or "{}")
    except ValueError:
        state = {}
    centroids, order = state.get("centroids", []), state.get("order", {})
    diar = diarization_available()
    labels: list = [None] * len(segments)
    if diar["available"]:
        labels, centroids = diarize(asr["audio"], segments, centroids)
    asr["audio"] = None  # drop the raw waveform as soon as it is no longer needed
    items = []
    for seg, raw in zip(segments, labels):
        items.append(SegmentIn(text=seg["text"], text_en=seg.get("text_en"), start_time=offset + seg["start"],
                               end_time=offset + seg["end"], speaker_id=friendly_label(raw, order),
                               language=seg.get("language") or asr["language"], source_type="audio",
                               confidence=seg.get("confidence")))
    db.cache_set(meeting_id, "diarization", json.dumps({"centroids": centroids, "order": order}))
    diar_note = None if diar["available"] else diar["reason"]
    matches: list = []
    kept, covered = service.merge_audio_with_captions(db.get_segments(meeting_id), items, matches=matches)
    learned = service.learn_voice_names(meeting_id, matches)
    added = service.ingest(meeting_id, kept)
    return {"added": [s.model_dump() for s in added], "language": asr["language"], "diarization": diar_note,
            "covered_by_captions": covered, "voices_named": learned}


# --------------------------------------------------------------- reading
@router.get("/meetings/{meeting_id}/segments")
def get_segments(meeting_id: str, speaker: Optional[str] = None, q: Optional[str] = None, since_idx: int = -1):
    _, segments, _, retriever = service.load(meeting_id)
    if speaker:
        segments = speaker_statements(segments, speaker)
    if q:
        hits = retriever.retrieve(q, k=15, speaker=speaker)
        return {"segments": [h.model_dump() for h in hits], "semantic": True}
    return {"segments": [s.model_dump() for s in segments if s.idx > since_idx], "semantic": False}


@router.get("/meetings/{meeting_id}/memory")
def get_memory(meeting_id: str):
    meeting, segments, memory, _ = service.load(meeting_id)
    return {"meeting": meeting, "memory": memory.model_dump()}


@router.post("/meetings/{meeting_id}/summary")
def post_summary(meeting_id: str, body: SummaryRequest):
    meeting, segments, memory, _ = service.load(meeting_id)
    t0 = time.perf_counter()
    result = summarize(segments, memory, body.mode, body.language, body.focus, body.from_time, body.to_time)
    result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


@router.post("/meetings/{meeting_id}/explain")
def post_explain(meeting_id: str, body: ExplainRequest):
    _, segments, _, _ = service.load(meeting_id)
    return explain(body.text, segments, body.style, body.difficulty, body.language, body.segment_id,
                   body.previous_explanation)


@router.post("/explain")
def post_explain_free(body: ExplainRequest):
    """Explain Again without a meeting (e.g. selected text on any page)."""
    return explain(body.text, [], body.style, body.difficulty, body.language, None, body.previous_explanation)


@router.post("/meetings/{meeting_id}/ask")
def post_ask(meeting_id: str, body: AskRequest):
    _, segments, memory, retriever = service.load(meeting_id)
    t0 = time.perf_counter()
    res = answer_question(body.question, segments, memory, [h.model_dump() for h in body.history], body.language,
                          body.speaker, body.from_time, body.to_time, retriever)
    res["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return res


class SegmentTranslations(BaseModel):
    target: str = Field(max_length=10)
    segment_ids: Optional[list[str]] = Field(default=None, max_length=300)


@router.post("/meetings/{meeting_id}/segments/translations")
def segment_translations(meeting_id: str, body: SegmentTranslations):
    """Each viewer reads the transcript in their own language: every line spoken in another language comes back
    translated into `target`, labelled with the language it was translated from. English comes from Whisper's speech
    translation when there is one; other targets are translated with NLLB (from that English when available, as it is
    more reliable than Whisper's Telugu/Kannada text) and cached per line, so each line is translated only once."""
    _, segments, _, _ = service.load(meeting_id)
    target = body.target.split("-")[0].lower()
    wanted = set(body.segment_ids or [])
    segments = [s for s in segments if s.segment_id in wanted] if wanted else segments[-200:]
    db = get_db()
    out = {}
    for s in segments:
        spoken_lang = (s.language or "und").split("-")[0].lower()
        only_english = "original_unavailable" in (s.flags or [])  # e.g. Telugu speech we could only write in English
        if spoken_lang in (target, "und") and not (only_english and target != "en"):
            continue  # already in the viewer's language (or too short to tell)
        if target == "en" and only_english:
            out[s.segment_id] = {"text": s.text, "from": spoken_lang, "from_name": language_name(spoken_lang),
                                 "engine": "whisper speech translation"}
            continue
        if target == "en" and s.original_text:  # s.text is Whisper's English of the speech
            text, engine = s.text, "whisper speech translation"
        else:
            key = f"tr:{target}:{s.segment_id}"
            text, engine = db.cache_get(meeting_id, key), "nllb"
            if not text:
                tr = translate(s.text, target, source="en" if (s.original_text or only_english) else spoken_lang)
                if not tr["translated"]:
                    out[s.segment_id] = {"text": None, "from": spoken_lang, "from_name": language_name(spoken_lang),
                                         "error": (tr["warnings"] or ["translation unavailable"])[0]}
                    continue
                text = tr["text"]
                db.cache_set(meeting_id, key, text)
        out[s.segment_id] = {"text": text, "from": spoken_lang, "from_name": language_name(spoken_lang),
                             "engine": engine}
    return {"target": target, "target_name": language_name(target), "translations": out}


@router.post("/translate")
def post_translate(body: TranslateRequest):
    return translate(body.text, body.target_language, body.source_language)


@router.post("/detect-language")
def post_detect(body: dict):
    return service.detect(str(body.get("text", ""))[:5000])


@router.get("/meetings/{meeting_id}/speakers")
def get_speakers(meeting_id: str):
    _, segments, memory, _ = service.load(meeting_id)
    return {"speakers": who_said_what(segments, memory.decisions, memory.action_items, memory.open_questions),
            "mapping": get_db().speaker_map(meeting_id)}


@router.put("/meetings/{meeting_id}/speakers")
def map_speaker(meeting_id: str, body: SpeakerMapping):
    service.require_meeting(meeting_id)
    name = body.speaker_name.strip()[:80]
    if not name:
        raise HTTPException(400, "speaker_name required")
    get_db().set_speaker(meeting_id, body.speaker_id, name, "user")
    service.invalidate(meeting_id)
    return {"mapping": get_db().speaker_map(meeting_id)}


@router.get("/meetings/{meeting_id}/decisions")
def get_decisions(meeting_id: str):
    _, _, memory, _ = service.load(meeting_id)
    return {"decisions": [d.model_dump() for d in memory.decisions],
            "history": [[d.model_dump() for d in chain] for chain in decision_chains(memory.decisions)],
            "changes": decision_changes(memory.decisions),
            "open_questions": [q.model_dump() for q in memory.open_questions],
            "contradictions": [c.model_dump() for c in memory.contradictions]}


@router.get("/meetings/{meeting_id}/tasks")
def get_tasks(meeting_id: str):
    _, _, memory, _ = service.load(meeting_id)
    return {"tasks": [t.model_dump() for t in memory.action_items]}


@router.patch("/meetings/{meeting_id}/tasks/{task_id}")
def update_task(meeting_id: str, task_id: str, body: TaskUpdate):
    service.require_meeting(meeting_id)
    get_db().set_task_override(meeting_id, task_id, body.status, body.owner, body.deadline)
    service.invalidate(meeting_id)
    _, _, memory, _ = service.load(meeting_id)
    task = next((t for t in memory.action_items if t.task_id == task_id), None)
    if not task:
        raise HTTPException(404, "Task not found")
    return task.model_dump()


@router.get("/meetings/{meeting_id}/timeline")
def get_timeline(meeting_id: str):
    _, segments, memory, _ = service.load(meeting_id)
    events = []
    for t in memory.topics:
        events.append({"type": "topic", "time": t.start_time, "label": t.label, "text": t.summary, "segment_id": t.segment_ids[0]})
    for d in memory.decisions:
        events.append({"type": "decision", "time": d.timestamp, "label": d.status, "text": d.summary, "segment_id": d.evidence_segments[0]})
    for a in memory.action_items:
        events.append({"type": "task", "time": a.timestamp, "label": a.owner, "text": a.task_text, "segment_id": a.evidence_segments[0]})
    for q in memory.open_questions:
        events.append({"type": "question", "time": q.timestamp, "label": q.status, "text": q.text, "segment_id": q.evidence_segments[0]})
    order = {s.segment_id: s.idx for s in segments}
    events.sort(key=lambda e: (order.get(e["segment_id"], 0), e["type"] != "topic"))
    return {"events": events, "topics": [t.model_dump() for t in memory.topics],
            "current_topic": memory.current_topic.model_dump() if memory.current_topic else None}


# ----------------------------------------------------------------- notes
@router.get("/meetings/{meeting_id}/notes")
def get_notes(meeting_id: str):
    service.require_meeting(meeting_id)
    return get_db().notes(meeting_id, service.notes_owner())


@router.post("/meetings/{meeting_id}/notes")
def add_note(meeting_id: str, body: NoteIn):
    service.require_meeting(meeting_id)
    return get_db().add_note(meeting_id, body.text, body.segment_id, service.notes_owner())


@router.delete("/meetings/{meeting_id}/notes/{note_id}")
def delete_note(meeting_id: str, note_id: str):
    service.require_meeting(meeting_id)
    get_db().delete_note(meeting_id, note_id, service.notes_owner())
    return {"deleted": note_id}


# ---------------------------------------------------------------- export
@router.get("/meetings/{meeting_id}/export")
def export(meeting_id: str, format: str = Query("md", pattern="^(md|json|txt|pdf)$"), language: str = "en",
           transcript: bool = True):
    meeting, segments, memory, _ = service.load(meeting_id)
    summary = summarize(segments, memory, "detailed", language)["summary"]
    notes = get_db().notes(meeting_id, service.notes_owner())
    safe = re.sub(r"[^\w\-]+", "_", meeting["title"])[:60] or "meeting"
    if format == "json":
        body = exporter.to_json(meeting, segments, memory, summary, notes)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.json"'})
    md = exporter.to_markdown(meeting, segments, memory, summary, notes, transcript)
    if format == "md":
        return PlainTextResponse(md, media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{safe}.md"'})
    if format == "txt":
        return PlainTextResponse(exporter.to_text(md), headers={"Content-Disposition": f'attachment; filename="{safe}.txt"'})
    return Response(exporter.to_pdf(md), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'})

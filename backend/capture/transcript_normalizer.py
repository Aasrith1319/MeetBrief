"""Normalise captions / transcripts from any source into common Segment objects.

Supported upload formats (auto-detected):
* WebVTT (.vtt), including ``<v Speaker>`` voice tags and ``Speaker: text`` cues
* SubRip (.srt)
* JSON: a list of segments or {"segments": [...]} with text/speaker/start fields
* Plain text lines, e.g.
    ``10:00 — Rahul: We need to improve response time.``
    ``[00:01:23] Priya: The queries are slow.``
    ``Arjun: We could also consider caching.``
    ``(continuation lines without a speaker are appended to the previous turn)``

Live captions often arrive as progressively growing updates of the same line;
:func:`dedupe_caption_updates` collapses those into final segments.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable, Optional

from backend.models import Segment, SegmentIn
from backend.nlp.language_detection import detect_language

TIME_RE = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?(?:\s?[AaPp][Mm])?"
LINE_RE = re.compile(
    rf"^\s*(?:\[?\(?(?P<time>{TIME_RE})\)?\]?\s*(?:[-–—|:]\s*)?)?"
    r"(?P<speaker>[A-Zऀ-෿][\w .'\-ऀ-෿]{0,40}?|Speaker[ _]?\d+|SPEAKER_\d+)\s*[:：]\s+"
    r"(?P<text>.+)$"
)
TIME_ONLY_RE = re.compile(rf"^\s*\[?\(?(?P<time>{TIME_RE})\)?\]?\s*(?:[-–—|:]\s*)?(?P<text>.+)$")
VTT_TS = re.compile(r"(?P<start>[\d:.,]+)\s*-->\s*(?P<end>[\d:.,]+)")
NOT_SPEAKERS = {"note", "action item", "todo", "decision", "agenda", "question", "update", "summary", "http", "https"}


def parse_timestamp(value: str) -> Optional[float]:
    """'10:02' -> 602s (mm:ss or hh:mm clock), '00:01:23.5' -> 83.5, '10:02 AM' -> clock seconds."""
    if value is None:
        return None
    v = value.strip().replace(",", ".")
    ampm = None
    m = re.search(r"\s?([AaPp][Mm])$", v)
    if m:
        ampm = m.group(1).lower()
        v = v[: m.start()].strip()
    parts = v.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        h, mnt, s = nums
    elif len(nums) == 2:
        if ampm:
            h, mnt, s = nums[0], nums[1], 0.0
        else:
            h, mnt, s = 0.0, nums[0], nums[1]
    else:
        return nums[0]
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    return h * 3600 + mnt * 60 + s


def _clock_style(times: list[str]) -> bool:
    """Heuristic: '10:00, 10:02, 10:04' are wall-clock hh:mm, not mm:ss."""
    two_part = [t for t in times if t and t.count(":") == 1 and not re.search(r"[.,]", t)]
    if len(two_part) < 2 or len(two_part) != len([t for t in times if t]):
        return False
    vals = []
    for t in two_part:
        a, b = t.split(":")[:2]
        vals.append((int(re.sub(r"\D", "", a) or 0), int(re.sub(r"\D", "", b) or 0)))
    # mm:ss transcripts usually start near 00:00; clock times start at e.g. 9/10/14 o'clock
    return vals[0][0] >= 7 and all(v[0] < 24 for v in vals)


def segment_id_for(meeting_id: str, idx: int, text: str) -> str:
    digest = hashlib.sha1(f"{meeting_id}:{idx}:{text}".encode()).hexdigest()[:6]
    return f"S{idx + 1}-{digest}"


def detect_format(content: str, filename: str | None = None) -> str:
    name = (filename or "").lower()
    stripped = content.lstrip("﻿ \n\r\t")
    if name.endswith(".vtt") or stripped.startswith("WEBVTT"):
        return "vtt"
    if name.endswith(".json"):
        return "json"
    if stripped[:1] in "[{":
        try:
            json.loads(stripped)
            return "json"
        except ValueError:
            pass
    if name.endswith(".srt") or re.match(r"^\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", stripped):
        return "srt"
    return "text"


def _split_speaker(cue: str) -> tuple[Optional[str], str]:
    m = re.match(r"^<v(?:\.[\w.]+)?\s+([^>]+)>(.*?)(?:</v>)?$", cue.strip(), flags=re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^([A-Z][\w .'\-]{0,40}?|Speaker[ _]?\d+|SPEAKER_\d+)\s*:\s+(.+)$", cue.strip(), flags=re.S)
    if m and m.group(1).strip().lower() not in NOT_SPEAKERS:
        return m.group(1).strip(), m.group(2).strip()
    return None, cue.strip()


def parse_vtt_or_srt(content: str) -> list[SegmentIn]:
    out: list[SegmentIn] = []
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").replace("﻿", ""))
    for block in blocks:
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        ts_idx = next((i for i, ln in enumerate(lines) if VTT_TS.search(ln)), None)
        if ts_idx is None:
            continue
        m = VTT_TS.search(lines[ts_idx])
        text = " ".join(lines[ts_idx + 1:])
        text = re.sub(r"<(?!v[ .])[^>]+>", "", text)  # strip styling tags but keep voice tags
        speaker, text = _split_speaker(text)
        text = re.sub(r"<[^>]+>", "", text).strip()
        if not text:
            continue
        out.append(SegmentIn(text=text, start_time=parse_timestamp(m.group("start")),
                             end_time=parse_timestamp(m.group("end")), speaker_name=speaker,
                             source_type="transcript"))
    return out


def parse_json_transcript(content: str) -> list[SegmentIn]:
    data = json.loads(content)
    items = data.get("segments") or data.get("transcript") or data.get("results") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("JSON transcript must be a list of segments or contain a 'segments' list")
    out = []
    for item in items:
        if isinstance(item, str):
            out.append(SegmentIn(text=item, source_type="transcript"))
            continue
        text = item.get("text") or item.get("content") or item.get("transcript") or ""
        if not str(text).strip():
            continue
        start = item.get("start_time", item.get("start", item.get("startTime")))
        end = item.get("end_time", item.get("end", item.get("endTime")))
        out.append(SegmentIn(
            text=str(text).strip(),
            start_time=parse_timestamp(start) if isinstance(start, str) else start,
            end_time=parse_timestamp(end) if isinstance(end, str) else end,
            speaker_name=item.get("speaker_name") or item.get("speaker") or item.get("name"),
            speaker_id=item.get("speaker_id"),
            language=item.get("language"),
            source_type=item.get("source_type", "transcript"),
        ))
    return out


def parse_plain_text(content: str) -> list[SegmentIn]:
    raw_lines = [ln.strip() for ln in content.replace("\r\n", "\n").split("\n")]
    parsed: list[dict] = []
    pending_time = None
    for line in raw_lines:
        if not line:
            continue
        line = line.strip("•*- ").strip()
        line = re.sub(r"^[\"“]|[\"”]$", "", line)
        if re.fullmatch(rf"\(?\[?{TIME_RE}\]?\)?", line):
            # timestamp on its own line (Google Meet transcript docs) — applies to the next turn
            pending_time = line.strip("[]()")
            continue
        m = LINE_RE.match(line)
        if m and m.group("speaker").strip().lower() not in NOT_SPEAKERS:
            text = m.group("text").strip().strip("\"“”")
            parsed.append({"time": m.group("time") or pending_time, "speaker": m.group("speaker").strip(), "text": text})
            pending_time = None
            continue
        m = TIME_ONLY_RE.match(line)
        if m and m.group("time"):
            parsed.append({"time": m.group("time"), "speaker": None, "text": m.group("text").strip()})
            continue
        if parsed:
            parsed[-1]["text"] += " " + line  # continuation of previous turn
        else:
            parsed.append({"time": None, "speaker": None, "text": line})

    clock = _clock_style([p["time"] for p in parsed if p["time"]])
    out = []
    for p in parsed:
        start = None
        if p["time"]:
            if clock:
                h, mnt = p["time"].split(":")[:2]
                start = int(re.sub(r"\D", "", h)) * 3600 + int(re.sub(r"\D", "", mnt)) * 60
                if re.search(r"[Pp][Mm]", p["time"]) and int(re.sub(r"\D", "", h)) < 12:
                    start += 12 * 3600
            else:
                start = parse_timestamp(p["time"])
            # clock-style times (10:00, 10:02 ...) are kept as seconds-of-day so the UI
            # can show the original wall-clock time; mm:ss times are already relative.
        out.append(SegmentIn(text=p["text"], start_time=start, speaker_name=p["speaker"], source_type="transcript"))
    # fill end times from next start
    for a, b in zip(out, out[1:]):
        if a.start_time is not None and b.start_time is not None and a.end_time is None:
            a.end_time = b.start_time
    return out


def parse_transcript(content: str, fmt: str | None = None, filename: str | None = None) -> list[SegmentIn]:
    fmt = fmt or detect_format(content, filename)
    if fmt in ("vtt", "srt"):
        segs = parse_vtt_or_srt(content)
    elif fmt == "json":
        segs = parse_json_transcript(content)
    else:
        segs = parse_plain_text(content)
    return merge_fragments(segs)


def merge_fragments(segs: list[SegmentIn], max_gap: float = 1.5) -> list[SegmentIn]:
    """Merge consecutive subtitle fragments from the same speaker that split a sentence."""
    out: list[SegmentIn] = []
    for seg in segs:
        if out:
            prev = out[-1]
            same = (prev.speaker_name or prev.speaker_id) == (seg.speaker_name or seg.speaker_id)
            close = (prev.end_time is not None and seg.start_time is not None and seg.start_time - prev.end_time <= max_gap)
            unfinished = not re.search(r"[.!?।…]$", prev.text.strip())
            if same and close and unfinished and len(prev.text) < 400:
                prev.text = f"{prev.text} {seg.text}".strip()
                prev.end_time = seg.end_time or prev.end_time
                continue
        out.append(seg.model_copy())
    return out


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b(um+|uh+|erm+|hmm+)\b[,.]?\s*", "", text, flags=re.I)
    text = re.sub(r"\b(\w+)( \1\b)+", r"\1", text, flags=re.I)  # "the the" -> "the"
    return text.strip()


def dedupe_caption_updates(incoming: Iterable[SegmentIn], previous: Optional[Segment] = None) -> list[SegmentIn]:
    """Collapse progressively-updated caption lines (F02 / workflow B step 3).

    "We need" -> "We need to" -> "We need to improve" becomes a single segment.
    If an update merely repeats text already stored in ``previous`` it is dropped;
    if it extends it, only the new suffix is kept.
    """
    result: list[SegmentIn] = []
    last_text = previous.text if previous else ""
    last_speaker = previous.speaker_label if previous else None
    for seg in incoming:
        text = normalize_text(seg.text)
        if not text:
            continue
        speaker = seg.speaker_name or seg.speaker_id
        prior = result[-1] if result else None
        prior_text = prior.text if prior else last_text
        prior_speaker = (prior.speaker_name or prior.speaker_id) if prior else last_speaker
        if speaker == prior_speaker and prior_text:
            low, plow = text.lower(), prior_text.lower()
            if low == plow or plow.endswith(low):
                continue  # exact repeat
            if low.startswith(plow):
                suffix = text[len(prior_text):].strip()
                if prior is not None:
                    prior.text = text
                    prior.end_time = seg.end_time or prior.end_time
                    continue
                if not suffix:
                    continue
                text = suffix
        result.append(seg.model_copy(update={"text": text}))
    return result


def to_segments(meeting_id: str, items: list[SegmentIn], start_idx: int = 0) -> list[Segment]:
    segments = []
    for offset, item in enumerate(items):
        idx = start_idx + offset
        text = normalize_text(item.text)
        if not text:
            continue
        lang = detect_language(text)
        flags = []
        if lang.code_switched:
            flags.append("code_switched")
        if item.text_en and normalize_text(item.text_en) == text and (item.language or "en") != "en":
            flags.append("original_unavailable")  # only the English translation of the speech could be written
        speaker_name = (item.speaker_name or "").strip() or None
        speaker_id = (item.speaker_id or "").strip() or None
        if speaker_name and re.fullmatch(r"(speaker[ _]?\d+|spk_?\d+|unknown)", speaker_name, flags=re.I):
            # generic diarization labels are ids, not real participant names
            speaker_id, speaker_name = speaker_name, None
        if not speaker_name and not speaker_id:
            flags.append("speaker_unknown")
        segments.append(Segment(
            meeting_id=meeting_id, segment_id=segment_id_for(meeting_id, idx, text), idx=idx,
            start_time=item.start_time, end_time=item.end_time, text=text,
            text_en=normalize_text(item.text_en) if item.text_en else None,
            language=item.language or lang.language, language_confidence=lang.confidence,
            speaker_id=speaker_id or (speaker_name.lower().replace(" ", "_") if speaker_name else None),
            speaker_name=speaker_name, source_type=item.source_type, confidence=item.confidence, flags=flags,
        ))
    return segments

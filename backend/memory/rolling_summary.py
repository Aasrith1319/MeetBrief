"""Rolling summary (F42; workflow G).

Transcript segments are grouped into fixed-size chunks. Each completed chunk is
summarised once with the abstractive dialogue model (cached by a content hash);
the newest, still-growing chunk uses a fast extractive summary, so live updates
stay cheap.
"""
from __future__ import annotations

import hashlib
from typing import Callable, Optional

from backend.hf import models as hf
from backend.models import Segment
from backend.nlp import evidence_alignment
from backend.nlp.summarization import key_sentences
from backend.nlp.text_utils import format_time

CHUNK = 20


def chunk_key(chunk: list[Segment]) -> str:
    return hashlib.sha1("|".join(s.segment_id for s in chunk).encode()).hexdigest()[:16]


def summarize_chunk(chunk: list[Segment], abstractive: bool) -> str:
    if abstractive and hf.enabled("summary"):
        out = hf.summarize_dialogue("\n".join(f"{s.speaker_label}: {s.text}" for s in chunk), max_new_tokens=120)
        if out:
            return evidence_alignment.render(evidence_alignment.align(out, chunk))
    pts = key_sentences(chunk, 2)
    return " ".join(f"{seg.speaker_label}: {sent} [{seg.segment_id}]" for sent, seg in pts)


def rolling_summary(segments: list[Segment], cache_get: Callable[[str], Optional[str]],
                    cache_set: Callable[[str, str], None]) -> str:
    parts = []
    for start in range(0, len(segments), CHUNK):
        chunk = segments[start:start + CHUNK]
        complete = len(chunk) == CHUNK
        key = f"rolling:{chunk_key(chunk)}:{hf.MODELS['summary'] if hf.enabled('summary') else 'extractive'}"
        summary = cache_get(key) if complete else None
        if summary is None:
            summary = summarize_chunk(chunk, abstractive=complete)
            if complete:
                cache_set(key, summary)
        parts.append(f"({format_time(chunk[0].start_time)}) {summary}")
    return "\n".join(parts)

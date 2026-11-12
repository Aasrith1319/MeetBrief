"""Evidence retrieval over a meeting's transcript (F49-F53; workflow E).

Chunks are individual segments embedded together with their neighbours'
text (a small context window) so short replies like "Yes, by Friday" remain
retrievable. Results can be filtered by speaker or time range.
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np

from backend.models import Evidence, Segment
from backend.rag.embeddings import HybridIndex

PRONOUN_FOLLOWUP = re.compile(r"\b(?:it|that|this|they|them|those|he|she|his|her|their|why|and|also)\b", re.I)


class MeetingRetriever:
    def __init__(self, segments: list[Segment], context: int = 1):
        self.segments = segments
        docs = []
        for i, seg in enumerate(segments):
            lo, hi = max(0, i - context), min(len(segments), i + context + 1)
            neighbours = " ".join(segments[j].text for j in range(lo, hi) if j != i)
            # repeat the segment's own text so it dominates its neighbours
            docs.append(f"{seg.speaker_label}: {seg.text} {seg.text} {neighbours}")
        self.index = HybridIndex(docs) if docs else None

    def retrieve(self, query: str, k: int = 5, speaker: Optional[str] = None, from_time: Optional[float] = None,
                 to_time: Optional[float] = None) -> list[Evidence]:
        if not self.index:
            return []
        mask = np.ones(len(self.segments), dtype=bool)
        if speaker:
            sp = speaker.lower()
            mask &= np.array([sp in {(s.speaker_name or "").lower(), (s.speaker_id or "").lower()} for s in self.segments])
        if from_time is not None:
            mask &= np.array([(s.start_time or 0) >= from_time for s in self.segments])
        if to_time is not None:
            mask &= np.array([(s.start_time or 0) <= to_time for s in self.segments])
        hits = self.index.search(query, k=k, mask=mask)
        return [Evidence(segment_id=self.segments[i].segment_id, start_time=self.segments[i].start_time,
                         speaker=self.segments[i].speaker_label, text=self.segments[i].text, score=round(score, 4))
                for i, score in hits]

    def neighbours(self, segment_id: str, radius: int = 2) -> list[Segment]:
        for i, s in enumerate(self.segments):
            if s.segment_id == segment_id:
                return self.segments[max(0, i - radius): i + radius + 1]
        return []


def contextualize_query(question: str, history: list[dict]) -> str:
    """For short follow-ups ("why?", "and who owns it?") prepend the previous user question (F50)."""
    prev = [h["content"] for h in history if h.get("role") == "user"]
    if prev and (len(question.split()) <= 7 or PRONOUN_FOLLOWUP.search(question)):
        return f"{prev[-1]} {question}"
    return question

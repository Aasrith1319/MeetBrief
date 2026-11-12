"""Speaker intelligence: Who Said What? (F33-F40).

Identity rules:
* Participant names are used only when the source supplied them or the user
  mapped a generic label (Speaker 1 -> Priya) explicitly.
* Generic labels stay generic and are flagged ``identity_known=False``.
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np

from backend.models import ActionItem, Decision, OpenQuestion, Segment
from backend.nlp.decision_extraction import classify_statement
from backend.nlp.text_utils import split_sentences, textrank


def apply_speaker_map(segments: list[Segment], mapping: dict[str, str]) -> list[Segment]:
    """Apply user-confirmed speaker-id -> participant-name mappings (F35)."""
    if not mapping:
        return segments
    out = []
    for s in segments:
        if s.speaker_id and s.speaker_id in mapping and not s.speaker_name:
            s = s.model_copy(update={"speaker_name": mapping[s.speaker_id], "flags": [*s.flags, "speaker_mapped_by_user"]})
        out.append(s)
    return out


def participants(segments: list[Segment]) -> list[str]:
    seen: "OrderedDict[str, None]" = OrderedDict()
    for s in segments:
        if s.speaker_name:
            seen[s.speaker_name] = None
    return list(seen)


def who_said_what(segments: list[Segment], decisions: list[Decision], tasks: list[ActionItem],
                  questions: list[OpenQuestion]) -> list[dict]:
    groups: "OrderedDict[str, list[Segment]]" = OrderedDict()
    for s in segments:
        groups.setdefault(s.speaker_label, []).append(s)
    total_words = sum(len(s.text.split()) for s in segments) or 1
    result = []
    for label, segs in groups.items():
        known = any(s.speaker_name for s in segs)
        sentences, sent_seg = [], []
        for s in segs:
            for sent in split_sentences(s.text):
                sentences.append(sent)
                sent_seg.append(s)
        scores = textrank(sentences) if sentences else np.zeros(0)
        top = sorted(np.argsort(-scores)[: min(3, len(sentences))]) if len(sentences) else []
        key_points = [{"text": sentences[i], "segment_id": sent_seg[i].segment_id, "start_time": sent_seg[i].start_time}
                      for i in top]
        suggestions = [{"text": sent, "segment_id": seg.segment_id, "start_time": seg.start_time}
                       for sent, seg in zip(sentences, sent_seg) if classify_statement(sent) == "proposed"]
        speaker_keys = {label}
        if segs[0].speaker_id:
            speaker_keys.add(segs[0].speaker_id)
        result.append({
            "speaker": label,
            "speaker_id": segs[0].speaker_id,
            "identity_known": known,
            "identity_note": None if known else "Identity unknown: generic label kept; map it in Who Said What if you know who this is.",
            "segment_count": len(segs),
            "word_share": round(sum(len(s.text.split()) for s in segs) / total_words, 3),
            "first_time": segs[0].start_time,
            "key_points": key_points,
            "suggestions": suggestions,
            "decisions": [d.model_dump() for d in decisions if d.speaker in speaker_keys],
            "tasks_owned": [t.model_dump() for t in tasks if t.owner in speaker_keys],
            "tasks_assigned": [t.model_dump() for t in tasks if t.assigned_by in speaker_keys and t.owner not in speaker_keys],
            "questions": [q.model_dump() for q in questions if q.asked_by in speaker_keys],
        })
    return result


def speaker_statements(segments: list[Segment], speaker: str) -> list[Segment]:
    """Speaker-specific search (F37)."""
    sp = speaker.strip().lower()
    return [s for s in segments if sp in {(s.speaker_name or "").lower(), (s.speaker_id or "").lower()}]

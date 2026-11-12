"""Builds and merges the structured meeting memory (7.4; workflow G).

The memory is recomputed from the stored transcript (deterministic and cheap
for the rule-based extractors) and then merged with user corrections
(task status/owner/deadline edits, speaker mappings), which always win.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Optional

from backend.hf import models as hf
from backend.models import MeetingMemory, Segment
from backend.memory.rolling_summary import rolling_summary
from backend.nlp.action_extraction import extract_action_items
from backend.nlp.contradiction import find_contradictions
from backend.nlp.decision_extraction import extract_decisions
from backend.nlp.glossary import terms_in
from backend.nlp.question_tracking import extract_questions
from backend.nlp.speakers import participants
from backend.nlp.topic_detection import detect_topics

import re


def _entities(segments: list[Segment]) -> tuple[list[str], dict[str, str], dict[str, set]]:
    """Named entities (BERT-NER, local Hugging Face model) with a capitalisation heuristic as fallback.

    Returns (top entities, entity -> type, segment_id -> set of PER names).
    """
    if hf.enabled("ner"):
        counts: Counter = Counter()
        types: dict[str, str] = {}
        persons: dict[str, set] = {}
        for s in segments:
            ents = hf.ner(s.text)
            if ents is None:
                break
            for e in ents:
                counts[e["text"]] += 1
                types[e["text"]] = e["type"]
                if e["type"] == "PER":
                    persons.setdefault(s.segment_id, set()).add(e["text"].lower())
        else:
            top = [w for w, _ in counts.most_common(20)]
            return top, {w: types[w] for w in top}, persons
    counts = Counter()
    for s in segments:
        for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z0-9]+(?:\s[A-Z][a-zA-Z0-9]+)*)\b", s.text):
            word = m.group(1)
            if word not in {"I", "I'm", "I'll", "OK", "Okay", "Let", "We", "So", "Yes", "No"}:
                counts[word] += 1
    return [w for w, _ in counts.most_common(15)], {}, {}


def suggest_questions(memory: MeetingMemory) -> list[str]:
    """F62: helpful follow-up questions derived from gaps in the memory."""
    out = []
    for t in memory.action_items:
        if t.owner == "unknown":
            out.append(f"Who is responsible for “{t.task_text}”?")
        elif t.deadline == "unspecified":
            out.append(f"When is “{t.task_text}” due?")
    for d in memory.decisions:
        if d.status == "confirmed":
            core = re.split(r",?\s+\b(?:because|since|so that|so|as)\b", d.summary)[0]
            out.append(f"Why was “{core}” decided?")
            break
    for q in memory.open_questions:
        if q.status == "unresolved":
            out.append(q.text)
    for term in memory.terms[:2]:
        out.append(f"What does “{term}” mean in this meeting?")
    if memory.decisions:
        out.append("What was decided?")
    if memory.action_items:
        out.append("What are the action items?")
    return list(dict.fromkeys(out))[:8]


def build_memory(meeting_id: str, segments: list[Segment], overrides: dict[str, dict],
                 cache_get: Optional[Callable[[str], Optional[str]]] = None,
                 cache_set: Optional[Callable[[str, str], None]] = None) -> MeetingMemory:
    people = participants(segments)
    decisions = extract_decisions(segments)
    tasks = extract_action_items(segments, people)
    for t in tasks:
        o = overrides.get(t.task_id)
        if o:
            if o.get("status"):
                t.status = o["status"]
            if o.get("owner"):
                t.owner, t.owner_source = o["owner"], "user"
                t.flags = [f for f in t.flags if f != "owner_unknown"]
            if o.get("deadline"):
                t.deadline = o["deadline"]
                t.flags = [f for f in t.flags if f != "deadline_unspecified"]
    entities, entity_types, persons = _entities(segments)
    if persons or entity_types:
        known = {p.lower() for p in people}
        for t in tasks:
            # an explicit owner who is neither a known participant nor recognised as a person is suspicious
            if t.owner_source == "explicit" and t.owner.lower() not in known and \
                    not any(t.owner.lower() in persons.get(sid, set()) for sid in t.evidence_segments):
                t.flags.append("owner_not_verified")
                t.confidence = min(t.confidence, 0.5)
    questions = extract_questions(segments)
    topics = detect_topics(segments)
    for d in decisions:
        for tp in topics:
            if d.evidence_segments and d.evidence_segments[0] in tp.segment_ids:
                d.topic = tp.label
    langs = Counter(s.language or "und" for s in segments)
    memory = MeetingMemory(
        meeting_id=meeting_id, segment_count=len(segments), participants=people, languages=dict(langs),
        topics=topics, current_topic=topics[-1] if topics else None, decisions=decisions, action_items=tasks,
        open_questions=questions, contradictions=find_contradictions(segments, decisions),
        entities=entities, entity_types=entity_types, terms=sorted({t for s in segments for t in terms_in(s.text)}),
    )
    if cache_get and cache_set:
        memory.rolling_summary = rolling_summary(segments, cache_get, cache_set)
    memory.suggested_questions = suggest_questions(memory)
    return memory

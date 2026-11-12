"""Action-item, owner and deadline extraction (F39, F57, F58; workflow F).

Owners are only filled in when the transcript states them explicitly:
* addressed assignment  — "Priya, please complete the indexing by Friday"
* named assignment      — "Arjun will update the docs", "Arjun to update the docs"
* self-commitment       — "I'll send the report" (owner = the speaker, when known)
Anything else keeps ``owner="unknown"`` and is flagged, never guessed.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from backend.models import ActionItem, Segment
from backend.nlp.text_utils import split_sentences

WEEKDAYS = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DEADLINE_RE = re.compile(
    r"\b(?:(?:by|before|until|till|due|on|no later than|latest by)\s+)?"
    r"(?:(?:this|next|coming)\s+)?"
    r"(?:" + WEEKDAYS + r"(?:\s+(?:morning|afternoon|evening|night|eod))?"
    r"|tomorrow(?:\s+(?:morning|afternoon|evening))?|today|tonight|eod|eow|end of (?:the )?(?:day|week|month|sprint|quarter)"
    r"|next (?:week|month|sprint|quarter)|this (?:week|month|sprint)"
    r"|" + MONTHS + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + MONTHS + r"(?:\s+\d{4})?"
    r"|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r"|(?:the )?\d{1,2}(?:st|nd|rd|th)"
    r"|in (?:a|one|two|three|\d+) (?:days?|weeks?)"
    r"|kal|parso|repu|ellundi)\b",
    re.I,
)
REQUEST_VERBS = r"(?:please|pls|can you|could you|would you|will you|kindly|make sure (?:you|to)|i need you to|you need to|you should)"
SELF_COMMIT = re.compile(r"\b(?:i(?:'ll| will| can| am going to|'m going to)|let me|i'll take|i will take|main karunga|nenu chestanu)\s+(?!be\b|think\b|say\b|guess\b|admit\b|try to remember\b)(?P<task>.+)", re.I)
EXPLICIT_MARK = re.compile(r"^\s*(?:action item|todo|to-do|task|ai)\s*[:\-]\s*(?P<task>.+)", re.I)


def _clean_task(task: str) -> str:
    task = task.strip().strip("\"“”").rstrip(".!?")
    task = re.sub(r"^(?:to|please|also|go ahead and|just)\s+", "", task, flags=re.I)
    task = re.sub(r"\s*,?\s*(?:ok|okay|alright|right)\??$", "", task, flags=re.I)
    return (task[:1].upper() + task[1:]) if task else task


def find_deadline(text: str) -> Optional[str]:
    matches = [m.group(0).strip() for m in DEADLINE_RE.finditer(text)]
    # ignore bare "on <weekday>" inside meeting-scheduling chatter only if nothing else exists
    if not matches:
        return None
    best = max(matches, key=len)
    return re.sub(r"^(?:by|before|until|till|due|on|no later than|latest by)\s+", "", best, flags=re.I) if len(best) > 3 else best


def _strip_deadline(task: str, deadline: Optional[str]) -> str:
    if not deadline:
        return task
    pattern = r"\s*,?\s*(?:by|before|until|till|due|on|no later than|latest by)?\s*(?:this |next |coming )?" + re.escape(deadline) + r"\b"
    return re.sub(pattern, "", task, flags=re.I).strip()


def _task_id(seg_id: str, text: str) -> str:
    return "T-" + hashlib.sha1(f"{seg_id}:{text.lower()}".encode()).hexdigest()[:8]


def extract_action_items(segments: list[Segment], participants: list[str] | None = None) -> list[ActionItem]:
    known = {p.lower(): p for p in (participants or []) if p}
    items: list[ActionItem] = []
    for seg in segments:
        # a generic diarization label ("Speaker 2") is kept as-is and flagged, never turned into a guessed name
        speaker = seg.speaker_name or seg.speaker_id
        generic_speaker = not seg.speaker_name
        for sentence in split_sentences(seg.text):
            item = _extract_from_sentence(sentence, speaker, known)
            if not item:
                continue
            task, owner, owner_source, flags = item
            if owner_source == "speaker_self" and generic_speaker:
                flags.append("owner_identity_unknown")
            deadline = find_deadline(sentence)
            task = _strip_deadline(task, deadline)
            if len(task.split()) < 2:
                continue
            if not deadline:
                flags.append("deadline_unspecified")
            if owner == "unknown":
                flags.append("owner_unknown")
            status = "open" if owner != "unknown" else "uncertain"
            items.append(ActionItem(
                task_id=_task_id(seg.segment_id, task), task_text=_clean_task(task), owner=owner,
                owner_source=owner_source, deadline=deadline or "unspecified", status=status,
                evidence_segments=[seg.segment_id], timestamp=seg.start_time,
                assigned_by=seg.speaker_name or seg.speaker_id, confidence=0.8 if owner != "unknown" else 0.5,
                flags=flags,
            ))
    return _dedupe(_resolve_vague(items, segments))


VAGUE_RE = re.compile(r"^(?:do|handle|finish|complete|take care of|fix|look into|send|get) (?:that|it|this|those|them)$", re.I)


def _resolve_vague(items: list[ActionItem], segments: list[Segment]) -> list[ActionItem]:
    """Tiny coreference step: "Sure, I can do that by Friday" refers back to the request just made
    ("Rishi, please compress the images by Friday"). Merge it into that task as the owner's confirmation
    instead of creating a separate, meaningless "Do that" task."""
    pos = {s.segment_id: i for i, s in enumerate(segments)}
    out: list[ActionItem] = []
    for it in items:
        if VAGUE_RE.match(it.task_text.strip(" .")):
            here = pos.get(it.evidence_segments[0], 0)
            antecedent = next((p for p in reversed(out) if 0 <= here - pos.get(p.evidence_segments[0], -99) <= 3), None)
            if antecedent is not None:
                antecedent.evidence_segments.append(it.evidence_segments[0])
                if antecedent.owner != it.owner and it.owner_source == "speaker_self" and "owner_identity_unknown" in it.flags:
                    # "Rishi, please …" answered by Speaker 3 with "I can do that" hints that Speaker 3 is Rishi
                    antecedent.flags.append(f"confirmed_by:{it.owner}")
                if antecedent.owner == "unknown" and it.owner != "unknown":
                    antecedent.owner, antecedent.owner_source = it.owner, it.owner_source
                if antecedent.deadline == "unspecified" and it.deadline != "unspecified":
                    antecedent.deadline = it.deadline
                antecedent.flags = [f for f in antecedent.flags if f not in ("owner_unknown", "deadline_unspecified")]
                antecedent.flags.append("confirmed_by_owner")
                antecedent.confidence = min(0.95, antecedent.confidence + 0.1)
                continue
            it.flags.append("vague_reference")
        out.append(it)
    return out


def _extract_from_sentence(sentence: str, speaker: Optional[str], known: dict[str, str]):
    s = sentence.strip().strip("\"“”")
    if s.endswith("?") and not re.search(REQUEST_VERBS, s, re.I):
        return None

    m = EXPLICIT_MARK.match(s)
    if m:
        task = m.group("task")
        owner_m = re.match(r"(?P<name>[A-Z][a-z]+)\s+(?:will|to|should|must)\s+(?P<rest>.+)", task)
        if owner_m:
            return owner_m.group("rest"), owner_m.group("name"), "explicit", []
        return task, "unknown", "unknown", []

    # "Priya, please complete ..." / "Priya, can you ..."
    m = re.match(r"^(?:(?i:ok(?:ay)?|so|and|also|alright|yes|yeah|sure|right|great|then)[, ]+)?(?P<name>[A-Z][\w\-]+(?: [A-Z][\w\-]+)?)\s*,\s*" + REQUEST_VERBS + r"\s+(?P<task>.+)", s)
    if m and m.group("name").lower() not in {"we", "so", "ok", "okay", "also", "everyone", "team", "guys", "folks", "all"}:
        return m.group("task"), m.group("name"), "explicit", []

    # "please X, Priya" / "can you X, Priya?"
    m = re.match(r"^" + REQUEST_VERBS + r"\s+(?P<task>.+?),\s*(?P<name>[A-Z][\w\-]+)\s*[?.!]?$", s, re.I)
    if m:
        return m.group("task"), m.group("name"), "explicit", []

    # "Arjun will update the docs" / "Arjun to update ..." / "Arjun is going to ..."
    m = re.match(r"^(?:(?i:ok(?:ay)?|so|and|then)[, ]+)?(?P<name>[A-Z][a-z]+)\s+(?:will|is going to|to|needs to|should|has to|can)\s+(?P<task>.+)", s)
    if m and (m.group("name").lower() in known or m.group("name") not in {"We", "It", "This", "That", "There", "They", "You", "He", "She", "Someone", "Everyone", "Nobody"}):
        if m.group("name") not in {"We", "It", "This", "That", "There", "They", "You", "He", "She", "Someone", "Everyone", "Nobody", "Let"}:
            return m.group("task"), known.get(m.group("name").lower(), m.group("name")), "explicit", []

    # "Can you / please ..." addressed to an unnamed person
    m = re.match(r"^(?:(?:ok(?:ay)?|so|and|also)[, ]+)?" + REQUEST_VERBS + r"\s+(?P<task>.+)", s, re.I)
    if m and DEADLINE_RE.search(s):
        return m.group("task"), "unknown", "unknown", ["addressee_unknown"]

    # self commitments
    m = SELF_COMMIT.search(s)
    if m and not s.endswith("?"):
        task = re.sub(r"^(?:also|then|just|quickly|definitely|go ahead and)\s+", "", m.group("task"), flags=re.I)
        if re.match(r"(?:send|share|update|write|fix|create|prepare|review|check|look into|follow up|schedule|set up|draft|"
                    r"finish|complete|test|deploy|investigate|handle|take care|reach out|email|call|document|add|build|"
                    r"implement|book|organize|run|benchmark|merge|ping|talk to|sync|get|do|make|own|work on|start|measure|monitor|"
                    r"compress|migrate|refactor|clean up|plan|coordinate|research|analy[sz]e|design|configure|install|"
                    r"upgrade|test|demo|present|record|publish|release|optimi[sz]e|profile|estimate|evaluate|label)", task, re.I):
            if speaker:
                return task, speaker, "speaker_self", []
            return task, "unknown", "unknown", ["speaker_unknown"]

    # "someone needs to ..." / "we need someone to ..."
    m = re.search(r"\b(?:someone|somebody)\s+(?:needs to|should|has to|must)\s+(?P<task>.+)", s, re.I)
    if m:
        return m.group("task"), "unknown", "unknown", []
    return None


def _dedupe(items: list[ActionItem]) -> list[ActionItem]:
    seen: dict[tuple, ActionItem] = {}
    for it in items:
        key = (it.owner.lower(), re.sub(r"\W+", " ", it.task_text.lower()).strip()[:60])
        if key in seen:
            seen[key].evidence_segments.extend(it.evidence_segments)
            continue
        seen[key] = it
    return list(seen.values())

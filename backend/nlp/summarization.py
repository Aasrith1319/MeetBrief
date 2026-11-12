"""Meeting summarization (F09-F15; workflow A/B).

Modes: quick, detailed, chronological, topic, personalized (focus) and the
"catchup" recap for late joiners (optionally restricted to a time range).

Hybrid design:
* Abstractive overview — a dialogue-summarization model (BART fine-tuned on
  SAMSum, run locally via Hugging Face) summarizes the "Speaker: text" transcript
  in chunks. Each generated sentence is aligned to supporting transcript
  segments and flagged when unsupported (see evidence_alignment).
* Extractive + structured sections — TextRank key sentences and the structured
  memory (decisions, tasks, questions, topics), each with segment references.
Output in other languages is produced by translating with NLLB-200.
Without the models, the extractive/structured parts still work.
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np

from backend.hf import models as hf
from backend.models import MeetingMemory, Segment
from backend.nlp import evidence_alignment
from backend.nlp.glossary import lookup, terms_in
from backend.nlp.text_utils import format_time, split_sentences, textrank
from backend.nlp.translation import translate

REASON_RE = re.compile(r"\b(?:because|since|so that|due to|reason|in order to|to avoid|otherwise|which is why)\b", re.I)
PROBLEM_RE = re.compile(r"\b(?:problem|issue|need to|slow|broken|bug|risk|blocker|concern|goal|improve)\b", re.I)
CHUNK_WORDS = 550  # keeps BART input under its 1024-token limit

MODE_POINTS = {"quick": 3, "catchup": 4, "detailed": 8, "chronological": 8, "topic": 2, "personalized": 4}


def _ref(seg: Segment) -> str:
    return f"[{seg.segment_id}]"


def key_sentences(segments: list[Segment], k: int) -> list[tuple[str, Segment]]:
    sents, owners = [], []
    for s in segments:
        for sent in split_sentences(s.text):
            if len(sent.split()) >= 3:
                sents.append(sent)
                owners.append(s)
    if not sents:
        return []
    scores = textrank(sents)
    # sentences stating the problem, a reason or a conclusion carry more catch-up value
    boost = np.array([1.3 if PROBLEM_RE.search(x) or REASON_RE.search(x) else 1.0 for x in sents])
    scores = scores * boost
    chosen = sorted(np.argsort(-scores)[: min(k, len(sents))])
    return [(sents[i], owners[i]) for i in chosen]


def _filter_range(segments: list[Segment], from_time: Optional[float], to_time: Optional[float]) -> list[Segment]:
    out = segments
    if from_time is not None:
        out = [s for s in out if s.start_time is None or s.start_time >= from_time]
    if to_time is not None:
        out = [s for s in out if s.start_time is None or s.start_time <= to_time]
    return out


def _in_range(seg_ids: list[str], ids: set[str]) -> bool:
    return any(s in ids for s in seg_ids)


def dialogue_chunks(segments: list[Segment], max_words: int = CHUNK_WORDS) -> list[list[Segment]]:
    chunks, cur, words = [], [], 0
    for s in segments:
        n = len(s.text.split()) + 2
        if cur and words + n > max_words:
            chunks.append(cur)
            cur, words = [], 0
        cur.append(s)
        words += n
    if cur:
        chunks.append(cur)
    return chunks


_overview_cache: dict[tuple, str] = {}


def abstractive_overview(segments: list[Segment]) -> Optional[list[dict]]:
    """[{start_time, end_time, text(with citations), aligned}] per chunk, or None if the model is unavailable.

    Generated chunk summaries are cached by (model, dialogue text), so live updates only
    summarise the newest, still-changing chunk."""
    if not segments or not hf.enabled("summary"):
        return None
    out = []
    for chunk in dialogue_chunks(segments):
        dialogue = "\n".join(f"{s.speaker_label}: {s.text}" for s in chunk)
        words = len(dialogue.split())
        key = (hf.MODELS["summary"], dialogue)
        summary = _overview_cache.get(key)
        if summary is None:
            summary = hf.summarize_dialogue(dialogue, max_new_tokens=min(220, max(90, words)),
                                            min_new_tokens=min(30, max(10, words // 8)))
            if summary is None:
                return None
            if len(_overview_cache) > 2000:
                _overview_cache.clear()
            _overview_cache[key] = summary
        aligned = evidence_alignment.align(summary, chunk)
        out.append({"start_time": chunk[0].start_time, "end_time": chunk[-1].end_time or chunk[-1].start_time,
                    "raw": summary, "text": evidence_alignment.render(aligned), "aligned": aligned})
    return out


def local_summary(segments: list[Segment], memory: MeetingMemory, mode: str, focus: Optional[str],
                  abstractive: bool = True) -> dict:
    ids = {s.segment_id for s in segments}
    decisions = [d for d in memory.decisions if _in_range(d.evidence_segments, ids)]
    tasks = [t for t in memory.action_items if _in_range(t.evidence_segments, ids)]
    questions = [q for q in memory.open_questions if _in_range(q.evidence_segments, ids) and q.status != "answered"]
    topics = [t for t in memory.topics if _in_range(t.segment_ids, ids)]
    points = key_sentences(segments, MODE_POINTS.get(mode, 4))
    lines: list[str] = []
    sections: dict[str, list] = {}
    overview = abstractive_overview(segments) if abstractive and mode in ("quick", "catchup", "detailed") else None

    def add_overview():
        if not overview:
            return
        lines.append(f"**Overview** _(abstractive — {hf.MODELS['summary'].split('/')[-1]}, verify ⚠ items)_")
        for part in overview:
            span = f"{format_time(part['start_time'])}–{format_time(part['end_time'])}: " if len(overview) > 1 else ""
            lines.append(f"- {span}{part['text']}")
        sections["overview"] = [{k: v for k, v in p.items()} for p in overview]

    def add_points(title: str = "Main points"):
        if points:
            lines.append(f"**{title}**")
            for sent, seg in points:
                lines.append(f"- {seg.speaker_label}: {sent} {_ref(seg)}")
            sections["main_points"] = [{"text": s, "speaker": g.speaker_label, "segment_id": g.segment_id} for s, g in points]

    def add_decisions():
        confirmed = [d for d in decisions if d.status in ("confirmed", "uncertain")]
        proposals = [d for d in decisions if d.status == "proposed"]
        superseded = [d for d in decisions if d.status == "superseded"]
        if proposals and mode != "quick":
            lines.append("**Options discussed**")
            for d in proposals:
                lines.append(f"- {d.summary} (proposed by {d.speaker or 'unknown'}) [{d.evidence_segments[0]}]")
        if confirmed:
            lines.append("**Decisions**")
            for d in confirmed:
                flag = " ⚠️ uncertain" if d.status == "uncertain" else ""
                lines.append(f"- {d.summary}{flag} (by {d.speaker or 'unknown'}) [{d.evidence_segments[0]}]")
        if superseded:
            lines.append("**Revised / superseded decisions**")
            for d in superseded:
                lines.append(f"- ~~{d.summary}~~ (superseded) [{d.evidence_segments[0]}]")
        sections["decisions"] = [d.model_dump() for d in decisions]

    def add_tasks():
        if tasks:
            lines.append("**Action items**")
            for t in tasks:
                warn = " ⚠️" if t.owner == "unknown" or t.deadline == "unspecified" else ""
                lines.append(f"- {t.task_text} — owner: {t.owner}; deadline: {t.deadline}{warn} [{t.evidence_segments[0]}]")
        sections["action_items"] = [t.model_dump() for t in tasks]

    def add_questions():
        if questions:
            lines.append("**Open questions**")
            for q in questions:
                lines.append(f"- {q.text} (asked by {q.asked_by or 'unknown'}) [{q.evidence_segments[0]}]")
        sections["open_questions"] = [q.model_dump() for q in questions]

    def add_current():
        if segments:
            cur = memory.current_topic
            recent = segments[-2:]
            lines.append("**Current context**")
            if cur:
                lines.append(f"- Likely current topic: {cur.label}")
            for s in recent:
                lines.append(f"- Latest: {s.speaker_label}: {s.text} {_ref(s)}")
            sections["current_context"] = {"topic": cur.label if cur else None,
                                           "recent": [{"speaker": s.speaker_label, "text": s.text, "segment_id": s.segment_id} for s in recent]}

    def add_problem():
        # the first explicit problem/goal statement gives late joiners the "why" of the meeting
        for seg in segments[: max(6, len(segments) // 4)]:
            for sent in split_sentences(seg.text):
                if PROBLEM_RE.search(sent) and not sent.endswith("?"):
                    lines.append("**Main problem / goal**")
                    lines.append(f"- {seg.speaker_label}: {sent} {_ref(seg)}")
                    sections["problem"] = {"text": sent, "segment_id": seg.segment_id}
                    return

    if mode in ("quick", "catchup"):
        add_problem()
        add_overview()
        if mode == "catchup" or not overview:
            add_points("Main points" if mode == "quick" else "Key moments (quoted)")
        add_decisions()
        add_tasks()
        if mode == "catchup":
            add_questions()
            add_current()
    elif mode == "detailed":
        add_overview()
        add_points("Key points")
        reasons = [(s, g) for g in segments for s in split_sentences(g.text) if REASON_RE.search(s)]
        if reasons:
            lines.append("**Reasoning stated in the meeting**")
            for s, g in reasons[:6]:
                lines.append(f"- {g.speaker_label}: {s} {_ref(g)}")
        if topics:
            lines.append("**By topic**")
            for t in topics:
                lines.append(f"- *{t.label}* ({format_time(t.start_time)}): {t.summary}")
        add_decisions()
        add_tasks()
        add_questions()
    elif mode == "chronological":
        events = []
        for t in topics:
            events.append((t.start_time or 0, f"Topic started: {t.label}", t.segment_ids[0]))
        for d in decisions:
            events.append((d.timestamp or 0, f"{'Decision' if d.status != 'proposed' else 'Proposal'} ({d.status}): {d.summary}", d.evidence_segments[0]))
        for tk in tasks:
            events.append((tk.timestamp or 0, f"Task assigned: {tk.task_text} → {tk.owner} (deadline: {tk.deadline})", tk.evidence_segments[0]))
        for q in questions:
            events.append((q.timestamp or 0, f"Open question: {q.text}", q.evidence_segments[0]))
        for sent, seg in points:
            events.append((seg.start_time or 0, f"{seg.speaker_label}: {sent}", seg.segment_id))
        order = {s.segment_id: s.idx for s in segments}
        events.sort(key=lambda e: (e[0], order.get(e[2], 0)))
        lines.append("**Chronological context**")
        seen = set()
        for ts, text, sid in events:
            if (text, sid) in seen:
                continue
            seen.add((text, sid))
            lines.append(f"- {format_time(ts)} — {text} [{sid}]")
        sections["events"] = [{"time": e[0], "text": e[1], "segment_id": e[2]} for e in events]
    elif mode == "topic":
        lines.append("**Topics**")
        for t in topics:
            tsegs = [s for s in segments if s.segment_id in set(t.segment_ids)]
            tp = key_sentences(tsegs, 2)
            lines.append(f"- *{t.label}* ({format_time(t.start_time)}–{format_time(t.end_time)})")
            ov = abstractive_overview(tsegs) if abstractive and len(tsegs) >= 2 else None
            if ov:
                lines.append(f"  - {ov[0]['text']}")
            for sent, seg in tp:
                lines.append(f"  - {seg.speaker_label}: {sent} {_ref(seg)}")
        sections["topics"] = [t.model_dump() for t in topics]
    elif mode == "personalized":
        focus = focus or "general"
        if focus == "decisions":
            add_decisions()
            if not decisions:
                lines.append("No decisions were identified in this range.")
        elif focus == "tasks":
            add_tasks()
            if not tasks:
                lines.append("No action items were identified in this range.")
        elif focus == "technical":
            terms = sorted({t for s in segments for t in terms_in(s.text)})
            lines.append("**Technical concepts mentioned**")
            for term in terms:
                _, entry = lookup(term)
                first = next((s for s in segments if term in terms_in(s.text)), None)
                ref = f" {_ref(first)}" if first else ""
                lines.append(f"- **{term}** — {entry['definition'] if entry else ''}{ref}")
            if not terms:
                lines.append("- No known technical terms detected (Explain Again can still explain any selected text).")
            sections["terms"] = terms
        else:
            add_points()
            add_current()
    text = "\n".join(lines) if lines else "Nothing has been captured in this range yet."
    return {"summary": text, "sections": sections,
            "engine": f"{hf.MODELS['summary']} + extractive" if overview else "extractive (TextRank) + rules"}


def summarize(segments: list[Segment], memory: MeetingMemory, mode: str = "quick", language: str = "en",
              focus: Optional[str] = None, from_time: Optional[float] = None, to_time: Optional[float] = None,
              abstractive: bool = True) -> dict:
    scoped = _filter_range(segments, from_time, to_time)
    result = local_summary(scoped, memory, mode, focus, abstractive)
    if language.split("-")[0] != "en":
        tr = translate(result["summary"], language, source="en")
        result["original"] = result["summary"]
        result["summary"] = tr["text"]
        result["translation"] = {k: tr[k] for k in ("translated", "engine", "warnings")}
    cited = list(dict.fromkeys(re.findall(r"\[(S\d+-[0-9a-f]{6})\]", result["summary"])))
    by_id = {s.segment_id: s for s in segments}
    result["evidence"] = [{"segment_id": c, "start_time": by_id[c].start_time, "speaker": by_id[c].speaker_label,
                           "text": by_id[c].text} for c in cited if c in by_id]
    result.update({"mode": mode, "language": language, "segment_range": [scoped[0].segment_id, scoped[-1].segment_id] if scoped else None,
                   "segments_covered": len(scoped)})
    if not segments:
        result["note"] = ("No transcript has been captured yet. MeetBrief can only recap what it has captured "
                          "or what you upload — it cannot reconstruct earlier conversation.")
    return result

"""Evidence-grounded answer generation (F49, F52-F54; workflows E and K).

Pipeline: hybrid retrieval (sparse TF-IDF + dense multilingual embeddings) →
relevance gate → intent-aware answering from the structured memory (owners,
deadlines, decisions, questions, "why") → extractive QA with a SQuAD 2.0 model
(which can say "no answer") → otherwise quote the best evidence.

Either way the system says when the transcript does not contain the answer
instead of inventing one — e.g. a "why" question whose reason was never stated.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.hf import models as hf
from backend.models import Evidence, MeetingMemory, Segment
from backend.nlp.language_detection import detect_language
from backend.nlp.text_utils import content_tokens, format_time
from backend.nlp.translation import translate
from backend.rag.retrieval import MeetingRetriever, contextualize_query

MIN_SCORE = 0.10
REASON_RE = re.compile(r"\b(?:because|since|so that|due to|the reason|reason is|as it|as they|in order to|to avoid|"
                       r"otherwise|that's why|which is why|given that|caused by|kyunki|endukante)\b", re.I)


def _cite(e: Evidence) -> str:
    return f"[{e.segment_id}]"


QUESTION_WORDS = {"what", "who", "why", "when", "where", "which", "how", "did", "does", "team", "meeting", "said",
                  "say", "tell", "about", "discussed", "mentioned", "talk", "talked", "anyone", "someone"}


def _stems(text: str) -> set[str]:
    nums = set(re.findall(r"\d+(?:\.\d+)+|\d{2,}", text))  # version numbers / figures like 2.4, 20
    return {t[:5] for t in content_tokens(text) if t not in QUESTION_WORDS} | nums


def _overlap(a: str, b: str) -> int:
    """Lexical overlap on 5-char prefixes (cheap stemming: index/indexing, query/queries)."""
    return len(_stems(a) & _stems(b))


def relevant(question: str, evidence: list[Evidence]) -> list[Evidence]:
    """Keep only evidence that shares meaningful vocabulary with the question.

    Character n-gram similarity alone can match unrelated text; requiring
    content-word overlap (or a strong dense score) is what lets the system
    abstain on questions the transcript never addresses.
    """
    from backend.rag.embeddings import dense_available

    q_stems = _stems(question)
    keep = []
    for e in evidence:
        shared = q_stems & _stems(f"{e.speaker or ''} {e.text}")
        coverage = len(shared) / len(q_stems) if q_stems else 0.0
        if (shared and coverage >= 0.5) or (dense_available() and (e.score or 0) >= 0.45):
            keep.append((coverage, e))
    # rank by how much of the question the passage covers, then by retrieval score
    keep.sort(key=lambda ce: (-round(ce[0], 2), -(ce[1].score or 0)))
    return [e for _, e in keep]


def _mentions_speaker(question: str, memory: MeetingMemory) -> Optional[str]:
    for p in memory.participants:
        if re.search(rf"\b{re.escape(p)}\b", question, re.I):
            return p
    return None


def local_answer(question: str, evidence: list[Evidence], memory: MeetingMemory, segments: list[Segment]) -> dict:
    q = question.strip()
    ql = q.lower()
    evidence = relevant(q, evidence)
    best = evidence[0] if evidence else None
    seg_by_id = {s.segment_id: s for s in segments}

    def fmt(e: Evidence) -> str:
        return f"{e.speaker} ({format_time(e.start_time)}): “{e.text}” {_cite(e)}"

    # --- structured intents first (they are backed by evidence ids too)
    if re.search(r"\b(?:action items?|tasks?|to-?dos?|next steps|assignments?)\b", ql) and not re.search(r"\bwho\b", ql):
        items = memory.action_items
        if not items:
            return _abstain("No action items were identified in the captured transcript.")
        lines = [f"- {t.task_text} — owner: {t.owner}, deadline: {t.deadline} [{t.evidence_segments[0]}]" for t in items]
        return _answer("Action items found in the transcript:\n" + "\n".join(lines),
                       [e for t in items for e in t.evidence_segments], seg_by_id, "high")

    if re.search(r"\b(?:what (?:was|were|has been|did (?:we|they|the team)) decid\w*|decisions?|decided|agreed)\b", ql) and not ql.startswith("why"):
        decs = [d for d in memory.decisions if d.status in ("confirmed", "uncertain")]
        terms = set(content_tokens(q)) - {"decided", "decision", "decisions", "agreed", "team", "meeting"}
        if terms:
            focused = [d for d in decs if set(content_tokens(d.summary)) & terms]
            decs = focused or decs
        if not decs:
            return _abstain("No confirmed decision was found in the captured transcript.")
        lines = [f"- {d.summary} ({d.status}{', by ' + d.speaker if d.speaker else ''}) [{d.evidence_segments[0]}]" for d in decs]
        return _answer("Decisions recorded:\n" + "\n".join(lines), [e for d in decs for e in d.evidence_segments], seg_by_id, "high")

    if re.search(r"\b(?:open|unresolved|unanswered|pending) questions?\b", ql):
        qs = [x for x in memory.open_questions if x.status != "answered"]
        if not qs:
            return _abstain("No unresolved questions were detected.")
        lines = [f"- {x.text} (asked by {x.asked_by or 'unknown'}) [{x.evidence_segments[0]}]" for x in qs]
        return _answer("Questions that do not appear to have been answered:\n" + "\n".join(lines),
                       [e for x in qs for e in x.evidence_segments], seg_by_id, "medium")

    if re.search(r"\b(?:when|deadline|due|by when)\b", ql):
        tasks = sorted(memory.action_items, key=lambda t: -_overlap(t.task_text, q))
        need = 1 if re.search(r"\b(?:task|deadline|due|finish|complete|done)\b", ql) else 2
        if tasks and _overlap(tasks[0].task_text, q) >= need:
            t = tasks[0]
            if t.deadline == "unspecified":
                return _answer(f"The transcript records the task “{t.task_text}” (owner: {t.owner}) but no deadline was stated. [{t.evidence_segments[0]}]",
                               t.evidence_segments, seg_by_id, "medium")
            return _answer(f"“{t.task_text}” is due {t.deadline} (owner: {t.owner}). [{t.evidence_segments[0]}]",
                           t.evidence_segments, seg_by_id, "high")

    if re.search(r"\bwho\b", ql) and re.search(r"\b(?:will|going to|responsible|owns?|owner|assigned|handling|doing|working on|take care|update|write|draft)\b", ql):
        tasks = sorted(memory.action_items, key=lambda t: -_overlap(t.task_text, q))
        if tasks and _overlap(tasks[0].task_text, q) > 0:
            t = tasks[0]
            if t.owner == "unknown":
                return _answer(f"The task “{t.task_text}” was mentioned, but no owner was explicitly stated. [{t.evidence_segments[0]}]",
                               t.evidence_segments, seg_by_id, "medium")
            return _answer(f"{t.owner} — “{t.task_text}”{'' if t.deadline == 'unspecified' else ', due ' + t.deadline}. [{t.evidence_segments[0]}]",
                           t.evidence_segments, seg_by_id, "high")

    if not best or best.score is None or best.score < MIN_SCORE:
        return _abstain("I couldn't find anything about this in the captured transcript, so I can't answer it reliably.")

    if re.search(r"\bwho\b", ql) and re.search(r"\b(?:said|say|suggested|proposed|mentioned|asked|raised|recommended|brought up)\b", ql):
        return _answer(f"{best.speaker} — {fmt(best)}", [best.segment_id], seg_by_id, "medium" if best.score < 0.25 else "high")

    if ql.startswith("why") or re.search(r"\b(?:reason|rationale|why)\b", ql):
        with_reason = [e for e in evidence[:4] if REASON_RE.search(e.text) and e.score and e.score >= MIN_SCORE]
        if with_reason:
            e = with_reason[0]
            return _answer(f"The transcript gives this reason: {fmt(e)}", [e.segment_id], seg_by_id, "medium")
        related = [e for e in evidence[1:3] if e.score and e.score >= MIN_SCORE]
        text = (f"The transcript records the relevant statement — {fmt(best)} — but the reason was not explicitly stated. "
                "I won't guess a rationale.")
        if related:
            text += " Related context (not stated as the reason): " + "; ".join(fmt(e) for e in related)
        return _answer(text, [best.segment_id] + [e.segment_id for e in related], seg_by_id, "low", insufficient=True)

    # If the best match is itself a question asked in the meeting, answer from its reply (or say it was unanswered)
    asked = {qq.evidence_segments[0]: qq for qq in memory.open_questions}
    if best.text.strip().endswith("?") and best.segment_id in asked:
        oq = asked[best.segment_id]
        if oq.status in ("answered", "uncertain") and oq.answer_segments:
            reply = seg_by_id.get(oq.answer_segments[0])
            if reply:
                verb = "replied" if oq.status == "answered" else "replied (this may be the answer)"
                return _answer(f"{best.speaker} asked this at {format_time(best.start_time)} {_cite(best)}; "
                               f"{reply.speaker_label} {verb}: “{reply.text}” [{reply.segment_id}]",
                               [best.segment_id, reply.segment_id], seg_by_id,
                               "medium" if oq.status == "answered" else "low")
        return _answer(f"This was asked by {best.speaker} at {format_time(best.start_time)} {_cite(best)}, but no clear answer "
                       "appears in the captured transcript.", [best.segment_id], seg_by_id, "low", insufficient=True)

    speaker = _mentions_speaker(q, memory)
    non_questions = [e for e in evidence if not e.text.strip().endswith("?")]
    if non_questions:
        evidence = non_questions
        best = evidence[0]

    qa = model_answer(q, evidence, segments, memory)
    if qa is not None:
        return qa

    picked = [e for e in evidence[:3] if e.score and e.score >= max(MIN_SCORE, best.score * 0.6)]
    if speaker:
        picked = [e for e in picked if e.speaker == speaker] or picked
    lead = "Based on the transcript:" if len(picked) > 1 else "According to the transcript,"
    text = f"{lead} " + " ".join(fmt(e) for e in picked)
    ids = [e.segment_id for e in picked]
    return _answer(_with_revisions(text, ids, memory), ids, seg_by_id, "high" if best.score >= 0.3 else "medium")


def _with_revisions(text: str, ids: list[str], memory: MeetingMemory) -> str:
    """Flag decisions in the cited evidence that were later revised (F56)."""
    by_id = {d.decision_id: d for d in memory.decisions}
    for d in memory.decisions:
        if d.status == "superseded" and d.superseded_by in by_id and set(d.evidence_segments) & set(ids):
            new = by_id[d.superseded_by]
            if new.evidence_segments[0] not in ids:
                text += f" Note: this was later revised — “{new.summary}” [{new.evidence_segments[0]}]."
                ids.append(new.evidence_segments[0])
    return text


QA_MIN_SCORE = 0.15


def model_answer(question: str, evidence: list[Evidence], segments: list[Segment], memory: MeetingMemory) -> Optional[dict]:
    """Extractive QA (RoBERTa fine-tuned on SQuAD 2.0) over the retrieved passages.

    SQuAD 2.0 models also score "no answer"; a span is only accepted when it beats
    the no-answer score and has enough probability mass. Returns None when the
    model is unavailable or not confident (caller falls back to quoting evidence).
    """
    if not evidence or not hf.enabled("qa") or detect_language(question).language not in ("en", "und"):
        return None
    pos = {s.segment_id: i for i, s in enumerate(segments)}
    windows, owners = [], []
    for e in evidence[:4]:
        i = pos.get(e.segment_id)
        if i is None:
            continue
        win = segments[max(0, i - 1): i + 2]
        windows.append("\n".join(f"{s.speaker_label}: {s.text}" for s in win))
        owners.append(win)
    results = hf.extractive_qa(question, windows)
    if not results:
        return None
    best_i = max(range(len(results)), key=lambda k: results[k]["score"] if results[k]["null_margin"] > 0 else -1)
    r = results[best_i]
    if r["null_margin"] <= 0 or r["score"] < QA_MIN_SCORE or not r["answer"]:
        return None
    span = r["answer"].strip(" .,:;")
    src = next((s for s in owners[best_i] if span.lower() in f"{s.speaker_label}: {s.text}".lower()), owners[best_i][0])
    seg_by_id = {s.segment_id: s for s in segments}
    earlier = None
    # The answer came from a decision that was later revised ("release on Friday" → "postpone to Tuesday"):
    # answer from the revision instead and mention the earlier plan, so the current state leads.
    by_id = {d.decision_id: d for d in memory.decisions}
    old = next((d for d in memory.decisions if d.status == "superseded" and src.segment_id in d.evidence_segments
                and d.superseded_by in by_id), None)
    if old is not None:
        new_sid = by_id[old.superseded_by].evidence_segments[0]
        i = pos.get(new_sid)
        if i is not None:
            win = segments[max(0, i - 1): i + 2]
            again = hf.extractive_qa(question, ["\n".join(f"{s.speaker_label}: {s.text}" for s in win)])
            if again and again[0]["null_margin"] > 0 and again[0]["score"] >= QA_MIN_SCORE and again[0]["answer"]:
                earlier = (span, src)
                span, src = again[0]["answer"].strip(" .,:;"), seg_by_id[new_sid]
    ids = [src.segment_id]
    text = (f"**{span[0].upper() + span[1:] if span else span}** — {src.speaker_label} ({format_time(src.start_time)}): "
            f"“{src.text}” [{src.segment_id}]")
    if earlier:
        text += f" (Earlier plan: {earlier[0]} — revised [{earlier[1].segment_id}].)"
        ids.append(earlier[1].segment_id)
    res = _answer(_with_revisions(text, ids, memory), ids, seg_by_id, "high" if r["score"] >= 0.5 else "medium")
    res["engine"] = hf.MODELS["qa"]
    res["qa_score"] = round(r["score"], 3)
    return res


def _answer(text: str, seg_ids: list[str], seg_by_id: dict, confidence: str, insufficient: bool = False) -> dict:
    ev, seen = [], set()
    for sid in seg_ids:
        if sid in seg_by_id and sid not in seen:
            s = seg_by_id[sid]
            seen.add(sid)
            ev.append(Evidence(segment_id=sid, start_time=s.start_time, speaker=s.speaker_label, text=s.text).model_dump())
    return {"answer": text, "evidence": ev, "confidence": confidence, "insufficient_evidence": insufficient}


def _abstain(text: str) -> dict:
    return {"answer": text, "evidence": [], "confidence": "none", "insufficient_evidence": True}


def answer_question(question: str, segments: list[Segment], memory: MeetingMemory, history: list[dict],
                    language: str = "en", speaker: Optional[str] = None, from_time: Optional[float] = None,
                    to_time: Optional[float] = None, retriever: Optional[MeetingRetriever] = None) -> dict:
    if not segments:
        return _abstain("No transcript has been captured for this meeting yet, so there is nothing to answer from.")
    retriever = retriever or MeetingRetriever(segments)
    query = contextualize_query(question, history)
    speaker = speaker or _mentions_speaker(question, memory)
    evidence = retriever.retrieve(query, k=6, speaker=speaker, from_time=from_time, to_time=to_time)
    if speaker and not evidence:
        evidence = retriever.retrieve(query, k=6, from_time=from_time, to_time=to_time)
    result = local_answer(question, evidence, memory, segments)
    result.setdefault("engine", "retrieval + rules")
    if language and language.split("-")[0] != "en":
        tr = translate(result["answer"], language, source="en")
        result["answer"] = tr["text"]
        result["translation"] = {k: tr[k] for k in ("translated", "engine", "warnings")}
    result["retrieved"] = [e.model_dump() for e in evidence]
    return result

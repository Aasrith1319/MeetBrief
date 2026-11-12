"""Decision extraction, classification and revision detection (F38, F46, F56; workflows F & J).

Each transcript sentence is classified as a *proposal*, a *confirmed decision*,
or neither, using discourse cues. A later decision that explicitly revises an
earlier one on the same subject marks the earlier record ``superseded``; the
history is preserved rather than silently replaced.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from backend.models import Decision, Segment
from backend.nlp.text_utils import content_tokens, cosine_matrix, split_sentences, tfidf_matrix

CONFIRM_CUES = [
    r"\bwe(?:'ve| have)? (?:decided|agreed|chosen|settled on|concluded)\b",
    r"\b(?:it's|it is) decided\b", r"\bdecision is\b", r"\bfinal(?:ly)?,? (?:we|let's)\b",
    r"\bwe(?:'ll| will) go with\b", r"\blet'?s go with\b", r"\bgoing with\b", r"\bwe(?:'re| are) going to go with\b",
    r"\bagreed\b", r"\bapproved\b", r"\bso the plan is\b", r"\bthe plan is\b", r"\bwe will (?:use|implement|ship|move|switch|adopt|launch|keep|drop|postpone|delay)\b",
    r"\blet'?s (?!discuss|talk|move on|start|begin|look|see|take|wrap|go over|review|think|check|meet|come back|circle|recap|get started|continue|hear|ask|focus on the)\w+",
    r"\bwe(?:'ll| will| should)? (?:stick with|switch to|move to)\b", r"\bconfirmed\b", r"\bsign(?:ed)? off\b",
    # Hinglish / Tenglish cues
    r"\b(?:final|decide) (?:hai|hua|ho gaya|chesam|ayyindi)\b", r"\bcheddam\b", r"\bkarte hain\b",
]
PROPOSAL_CUES = [
    r"\bi (?:suggest|propose|recommend|think we should|vote for)\b", r"\bwe (?:could|might|may) (?:also )?\b",
    r"\bhow about\b", r"\bwhat if we\b", r"\bmaybe we (?:should|could)\b", r"\bwhy don't we\b",
    r"\bone option (?:is|would be)\b", r"\b(?:another|an) (?:option|idea|alternative)\b", r"\bwe should consider\b",
    r"\bconsider\b", r"\bshould we\b",
]
REVISION_CUES = [
    r"\binstead\b", r"\bactually\b", r"\bchange of plans?\b", r"\bon second thought\b", r"\bscratch that\b",
    r"\brather than\b", r"\bnot anymore\b", r"\bno longer\b", r"\bchanged? (?:our|the) (?:mind|plan|decision)\b",
    r"\brevis(?:e|ed|ing)\b", r"\bpostpone\b", r"\bdelay\b", r"\bpush (?:it|this|that) (?:back|to)\b",
    r"\blet'?s not\b", r"\bdrop (?:the|that|this)\b", r"\breconsider\b", r"\bupdate:? the plan\b",
]
NOT_DECISION = [r"\?\s*$", r"^\s*(?:ok|okay|sure|yes|yeah|right|thanks)[.!]?\s*$", r"\blet'?s (?:discuss|talk|move on)\b"]


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)


def classify_statement(text: str) -> Optional[str]:
    """Return 'confirmed', 'proposed', or None."""
    t = text.strip()
    if _matches(NOT_DECISION, t):
        # questions are proposals at most ("should we use Redis?")
        return "proposed" if re.match(r"^(?:so,?\s+)?(?:should we|shall we|how about|what if we|why don't we|could we)\b", t, re.I) else None
    if _matches(CONFIRM_CUES, t):
        return "confirmed"
    if _matches(PROPOSAL_CUES, t):
        return "proposed"
    return None


def _summarize(sentence: str, speaker: Optional[str]) -> str:
    s = sentence.strip().strip("\"“”").rstrip(".")
    s = re.sub(r"^(?:(?:ok(?:ay)?|so|alright|right|well|yeah|actually|agreed|great|good|fine|theek hai|thik hai|acha|accha|sare|సరే)[,]?\s+)+", "", s, flags=re.I)
    s = re.sub(r"^let'?s\s+", "", s, flags=re.I)
    s = re.sub(r"^(?:i (?:suggest|propose|recommend|think we should)(?: that)?|we could(?: also)?|how about|maybe we should|we should consider|"
               r"we(?:'ve| have)? (?:decided|agreed)(?: to| that| on)?|we(?:'ll| will) go with|the plan is(?: to)?|"
               r"so the plan is(?: to)?)\s+", "", s, flags=re.I)
    s = s[:1].upper() + s[1:] if s else s
    return s


def _decision_id(seg_id: str, text: str) -> str:
    return "D-" + hashlib.sha1(f"{seg_id}:{text}".encode()).hexdigest()[:8]


def extract_decisions(segments: list[Segment], use_model: bool = True) -> list[Decision]:
    """Rule-based dialogue-act cues, optionally combined with zero-shot NLI (hybrid)."""
    from backend.nlp import dialogue_acts

    pairs = [(seg, sentence) for seg in segments for sentence in split_sentences(seg.text)]
    acts = dialogue_acts.classify([p[1] for p in pairs]) if use_model else None
    decisions: list[Decision] = []
    for k, (seg, sentence) in enumerate(pairs):
        kind = classify_statement(sentence)
        act = acts[k] if acts else None
        # NLI is not allowed to add decisions: on the held-out set that only added false positives
        # (decision precision 0.67 -> 0.50) and its decision recall on labelled sentences was 0/8.
        flags_model = False
        if not kind:
            continue
        uncertain = bool(re.search(r"\b(?:i guess|probably|maybe|tentative(?:ly)?|for now|unless)\b", sentence, re.I))
        if kind == "model":
            status = "uncertain"
        else:
            status = "confirmed" if kind == "confirmed" and not uncertain else ("uncertain" if kind == "confirmed" else "proposed")
        confidence = 0.75 if status == "confirmed" else 0.55
        if act:
            agree = (act["act"] == "decision") if kind == "confirmed" else (act["act"] == "proposal") if kind == "proposed" else True
            if agree:  # agreement raises confidence; disagreement is not penalised (NLI is weak on decisions)
                confidence = round(min(0.95, confidence + 0.15), 2)
        decisions.append(Decision(
            decision_id=_decision_id(seg.segment_id, sentence), summary=_summarize(sentence, seg.speaker_label),
            status=status, speaker=seg.speaker_name or seg.speaker_id, timestamp=seg.start_time,
            evidence_segments=[seg.segment_id], confidence=confidence,
            source="model" if flags_model else ("rules+model" if act else "rules"),
        ))
    link_revisions(decisions, segments)
    return decisions


def link_revisions(decisions: list[Decision], segments: list[Segment]) -> None:
    """Workflow J: mark an earlier decision superseded only when a later one explicitly revises it."""
    if len(decisions) < 2:
        return
    seg_text = {s.segment_id: s.text for s in segments}
    texts = [seg_text.get(d.evidence_segments[0], d.summary) for d in decisions]
    mat, _ = tfidf_matrix([d.summary for d in decisions])
    sim = cosine_matrix(mat)
    for j, later in enumerate(decisions):
        if later.status not in ("confirmed", "uncertain") or not _matches(REVISION_CUES, texts[j]):
            continue
        later_tokens = set(content_tokens(later.summary))
        best, best_score = None, 0.0
        for i in range(j):
            earlier = decisions[i]
            if earlier.status not in ("confirmed", "uncertain") or earlier.superseded_by:
                continue
            overlap = len(later_tokens & set(content_tokens(earlier.summary)))
            score = sim[i, j] + 0.15 * overlap
            if score > best_score:
                best, best_score = earlier, score
        if best is not None and best_score >= 0.2:
            best.status = "superseded"
            best.superseded_by = later.decision_id
            later.supersedes = best.decision_id


def decision_changes(decisions: list[Decision]) -> list[dict]:
    by_id = {d.decision_id: d for d in decisions}
    changes = []
    for d in decisions:
        if d.supersedes and d.supersedes in by_id:
            old = by_id[d.supersedes]
            changes.append({"from": old.summary, "to": d.summary, "from_id": old.decision_id, "to_id": d.decision_id,
                            "evidence_segments": old.evidence_segments + d.evidence_segments})
    return changes

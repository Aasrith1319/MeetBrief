"""Unresolved-question tracker (F47).

A question counts as *answered* only when a different speaker replies soon
after with a non-question statement that is topically related or an explicit
answer cue. Deferrals ("let's come back to that", "I'm not sure") keep it open.
"""
from __future__ import annotations

import hashlib
import re

from backend.models import OpenQuestion, Segment
from backend.nlp.text_utils import content_tokens, split_sentences

DEFER_CUES = re.compile(r"\b(?:not sure|don't know|no idea|let'?s (?:come back|circle back|park|revisit|take (?:it|this) offline)|"
                        r"follow up (?:on|later)|tbd|to be decided|need to check|i'll check|will check|get back to (?:you|us)|"
                        r"pata nahi|teliyadu|someone (?:needs|has) to|nobody knows|no one knows)\b", re.I)
ANSWER_CUES = re.compile(r"^(?:yes|yeah|yep|no|nope|sure|i think|it(?:'s| is)|because|we|the answer|probably|definitely|"
                         r"around|about|maybe|haan|ha|nahi|avunu|ledu)\b", re.I)
REQUEST = re.compile(r"^(?:\w+,\s*)?(?:can|could|would|will) you (?:please )?(?:build|send|share|update|write|fix|"
                     r"create|prepare|review|check|finish|complete|take|handle|look into|draft|own|do)\b", re.I)
RHETORICAL = re.compile(r"^(?:right|ok(?:ay)?|you know|isn't it|correct|makes sense|any questions|anything else|"
                        r"can everyone (?:hear|see) me|is that clear|sounds good|all good)\??$", re.I)


def extract_questions(segments: list[Segment], window: int = 4) -> list[OpenQuestion]:
    out: list[OpenQuestion] = []
    for i, seg in enumerate(segments):
        for sentence in split_sentences(seg.text):
            s = sentence.strip()
            if not s.endswith("?") or RHETORICAL.match(s) or len(s.split()) < 3:
                continue
            if REQUEST.match(s):  # "Omar, can you build X?" is an assignment, tracked as an action item
                continue
            qtokens = set(content_tokens(s))
            status = "unresolved"
            answers: list[str] = []
            for nxt in segments[i + 1:i + 1 + window]:
                same_speaker = (nxt.speaker_label == seg.speaker_label) and seg.speaker_label != "Unknown speaker"
                if DEFER_CUES.search(nxt.text):
                    status = "unresolved"
                    answers = []
                    break
                if same_speaker:
                    continue
                if nxt.text.strip().endswith("?"):
                    continue
                overlap = len(qtokens & set(content_tokens(nxt.text)))
                # a topical reply counts as an answer; any other reply only "possibly" answers it
                status = "answered" if overlap or ANSWER_CUES.match(nxt.text.strip()) else "uncertain"
                answers.append(nxt.segment_id)
                break
            qid = "Q-" + hashlib.sha1(f"{seg.segment_id}:{s}".encode()).hexdigest()[:8]
            out.append(OpenQuestion(question_id=qid, text=s, asked_by=seg.speaker_name or seg.speaker_id,
                                    timestamp=seg.start_time, status=status, evidence_segments=[seg.segment_id],
                                    answer_segments=answers))
    return out

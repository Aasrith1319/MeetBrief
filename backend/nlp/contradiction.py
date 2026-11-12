"""Potential-contradiction detection (F55).

Flags pairs of statements that are about the same subject (high lexical
similarity) but differ in polarity (one negated, one not) or state different
numbers for the same thing. These are *potential* conflicts for the user to
verify, never asserted facts.
"""
from __future__ import annotations

import re

from backend.models import Contradiction, Decision, Segment
from backend.nlp.text_utils import content_tokens, cosine_matrix, has_negation, split_sentences, tfidf_matrix

NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|ms|seconds?|minutes?|hours?|days?|weeks?|users?|gb|mb|k)?\b", re.I)


def find_contradictions(segments: list[Segment], decisions: list[Decision], limit: int = 10) -> list[Contradiction]:
    out: list[Contradiction] = []
    sents, owners = [], []
    for s in segments:
        for sent in split_sentences(s.text):
            if len(content_tokens(sent)) >= 3 and not sent.endswith("?"):
                sents.append(sent)
                owners.append(s)
    if len(sents) >= 2:
        mat, vec = tfidf_matrix(sents)
        if vec is not None:
            sim = cosine_matrix(mat)
            for i in range(len(sents)):
                for j in range(i + 1, len(sents)):
                    if owners[i].segment_id == owners[j].segment_id or sim[i, j] < 0.45:
                        continue
                    shared = set(content_tokens(sents[i])) & set(content_tokens(sents[j]))
                    if len(shared) < 2:
                        continue
                    neg_i, neg_j = has_negation(sents[i]), has_negation(sents[j])
                    nums_i = {n.strip().lower() for n in NUM_RE.findall(sents[i])}
                    nums_j = {n.strip().lower() for n in NUM_RE.findall(sents[j])}
                    reason = None
                    if neg_i != neg_j:
                        reason = "one statement is negated"
                    elif nums_i and nums_j and nums_i.isdisjoint(nums_j):
                        reason = "different figures are stated"
                    if reason:
                        out.append(Contradiction(
                            kind="potential_contradiction",
                            description=f"Possible conflict ({reason}): “{sents[i]}” ({owners[i].speaker_label}) vs “{sents[j]}” ({owners[j].speaker_label})",
                            evidence_segments=[owners[i].segment_id, owners[j].segment_id]))
                        if len(out) >= limit:
                            break
                if len(out) >= limit:
                    break
    by_id = {d.decision_id: d for d in decisions}
    for d in decisions:
        if d.supersedes and d.supersedes in by_id:
            old = by_id[d.supersedes]
            out.append(Contradiction(kind="decision_change",
                                     description=f"Decision revised: “{old.summary}” → “{d.summary}”",
                                     evidence_segments=old.evidence_segments + d.evidence_segments))
    return out

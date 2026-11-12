"""Topic segmentation and labelling (F14, F44, F48; workflow H).

TextTiling-style segmentation (TF-IDF): compare TF-IDF vectors of adjacent windows of
segments; deep similarity valleys and explicit transition phrases
("moving on to", "next item") mark likely topic boundaries. Each topic gets a
KeyBERT-style keyphrase label (multilingual embeddings + MMR) and an extractive summary. Topic boundaries are *likely shifts*,
never confirmed decisions.
"""
from __future__ import annotations

import re

import numpy as np

from backend.models import Segment, Topic
from backend.nlp.text_utils import textrank, tfidf_matrix, top_keywords

TRANSITION_RE = re.compile(
    r"\b(?:moving on|move on to|next (?:topic|item|point|up)|let'?s (?:talk|discuss|move) (?:about|on|to)|"
    r"switching (?:gears|to)|another (?:topic|thing)|the other thing|now (?:let'?s|for)|on to the|"
    r"agenda item|item (?:two|three|four|\d)|last (?:topic|item|thing))\b", re.I)


def _window_vec(mat: np.ndarray, lo: int, hi: int) -> np.ndarray:
    return mat[max(lo, 0):max(hi, 0)].sum(axis=0)


def detect_boundaries(segments: list[Segment], window: int = 3, min_len: int = 3) -> list[int]:
    n = len(segments)
    boundaries = {0}
    for i, seg in enumerate(segments):
        if i >= 2 and TRANSITION_RE.search(seg.text):
            boundaries.add(i)
    if n >= 2 * window + min_len:
        mat, vec = tfidf_matrix([s.text for s in segments])
        if vec is not None:
            gaps = []
            for i in range(1, n):
                a = _window_vec(mat, i - window, i)
                b = _window_vec(mat, i, i + window)
                denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
                gaps.append(float(a @ b / denom))
            gaps_arr = np.array(gaps)
            depth = np.zeros_like(gaps_arr)
            for g in range(len(gaps_arr)):
                left = gaps_arr[: g + 1].max()
                right = gaps_arr[g:].max()
                depth[g] = (left - gaps_arr[g]) + (right - gaps_arr[g])
            cutoff = depth.mean() + depth.std()
            for g in np.argsort(-depth):
                if depth[g] < cutoff or depth[g] < 0.35:
                    break
                idx = g + 1
                if all(abs(idx - b) >= min_len for b in boundaries):
                    boundaries.add(int(idx))
    # enforce minimum length (keep explicit transitions preferentially)
    ordered = sorted(boundaries)
    cleaned = [0]
    for b in ordered[1:]:
        if b - cleaned[-1] >= 2 and n - b >= 1:
            cleaned.append(b)
    return cleaned


def _label(texts: list[str]) -> tuple[str, list[str]]:
    for t in texts[:2]:
        m = re.search(r"(?:talk|discuss|move on|moving on|next (?:topic|item) is|let'?s look at)\s+(?:about|to|on)?\s*(?:the\s+)?([\w\- ]{3,40}?)(?:[.,!?]|$)", t, re.I)
        if m and len(m.group(1).split()) <= 5:
            return m.group(1).strip().capitalize(), keyphrases(texts, 4)
    kws = keyphrases(texts, 4)
    label = ", ".join(kws[:3]).capitalize() if kws else "General discussion"
    return label, kws


def keyphrases(texts: list[str], k: int = 4) -> list[str]:
    """KeyBERT-style labels: TF-IDF candidates re-ranked by embedding similarity to the
    topic text, with maximal marginal relevance for diversity. Falls back to TF-IDF."""
    from backend.rag.embeddings import dense_available, embed_cached

    cands = top_keywords(texts, 12)
    if len(cands) <= k or not dense_available():
        return cands[:k]
    vecs = embed_cached([" ".join(texts)] + cands)
    if vecs is None:
        return cands[:k]
    doc, cv = vecs[0], vecs[1:]
    rel = cv @ doc
    chosen: list[int] = []
    while len(chosen) < k:
        best, best_score = None, -9.0
        for i in range(len(cands)):
            if i in chosen:
                continue
            redundancy = max((float(cv[i] @ cv[j]) for j in chosen), default=0.0)
            score = 0.7 * float(rel[i]) - 0.3 * redundancy
            if score > best_score:
                best, best_score = i, score
        chosen.append(best)
    return [cands[i] for i in chosen]


def detect_topics(segments: list[Segment]) -> list[Topic]:
    if not segments:
        return []
    bounds = detect_boundaries(segments) + [len(segments)]
    topics = []
    for t_idx, (lo, hi) in enumerate(zip(bounds, bounds[1:])):
        chunk = segments[lo:hi]
        if not chunk:
            continue
        texts = [s.text for s in chunk]
        label, kws = _label(texts)
        scores = textrank(texts)
        best = sorted(np.argsort(-scores)[: min(2, len(texts))])
        summary = " ".join(f"{chunk[i].speaker_label}: {chunk[i].text}" for i in best)
        topics.append(Topic(
            topic_id=f"topic-{t_idx + 1}", label=label, keywords=kws, start_idx=chunk[0].idx, end_idx=chunk[-1].idx,
            start_time=chunk[0].start_time, end_time=chunk[-1].end_time or chunk[-1].start_time,
            summary=summary, segment_ids=[s.segment_id for s in chunk],
        ))
    return topics

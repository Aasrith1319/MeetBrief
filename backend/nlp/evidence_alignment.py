"""Claim-to-evidence alignment for generated text (workflow K, F53, F69, F70).

Abstractive models can hallucinate. Every generated sentence is aligned to the
most similar transcript segment (dense embeddings when available, otherwise
hybrid TF-IDF) and checked for "novel" names/numbers that do not occur anywhere
in the transcript. Weakly supported sentences are flagged instead of being
presented as fact.
"""
from __future__ import annotations

import re

import numpy as np

from backend.hf import models as hf
from backend.models import Segment
from backend.nlp.text_utils import split_sentences

DENSE_MIN, SPARSE_MIN = 0.45, 0.12
ENTITY_RE = re.compile(r"\b(?:[A-Z][a-zA-Z]+|\d+(?:\.\d+)?)\b")
COMMON_CAPS = {"The", "A", "An", "They", "He", "She", "It", "We", "I", "There", "This", "That", "Then", "And", "But",
               "So", "If", "Also", "In", "On", "At", "By", "For", "To", "Of", "With", "As", "Everyone", "Team", "After",
               "Before", "Both", "Each", "Their", "His", "Her", "Its", "Our", "Some", "No", "Yes", "Next", "First", "Last"}


def _novel_terms(sentence: str, transcript_low: str) -> list[str]:
    out = []
    for m in ENTITY_RE.finditer(sentence):
        w = m.group(0)
        if w in COMMON_CAPS or (m.start() == 0 and not w[0].isdigit() and w.lower() in transcript_low):
            continue
        if w.lower() not in transcript_low:
            out.append(w)
    return out


def align(text: str, segments: list[Segment]) -> list[dict]:
    sentences = [s for s in split_sentences(text) if len(s.split()) >= 3]
    if not sentences or not segments:
        return [{"sentence": s, "segment_id": None, "score": 0.0, "supported": False, "novel_terms": []} for s in sentences]
    transcript_low = " ".join(f"{s.speaker_label} {s.text}" for s in segments).lower()
    docs = [f"{s.speaker_label}: {s.text}" for s in segments]
    vecs = hf.embed(docs + sentences)
    if vecs is not None:
        seg_v, sent_v = np.asarray(vecs[: len(docs)]), np.asarray(vecs[len(docs):])
        sims = sent_v @ seg_v.T
        threshold = DENSE_MIN
    else:
        from backend.rag.embeddings import HybridIndex

        index = HybridIndex(docs)
        sims = np.stack([index.scores(s) for s in sentences])
        threshold = SPARSE_MIN
    out = []
    for i, sent in enumerate(sentences):
        j = int(np.argmax(sims[i]))
        novel = _novel_terms(sent, transcript_low)
        score = float(sims[i, j])
        out.append({"sentence": sent, "segment_id": segments[j].segment_id, "score": round(score, 3),
                    "supported": score >= threshold and not novel, "novel_terms": novel})
    return out


def render(aligned: list[dict]) -> str:
    """Sentences with citations; unsupported ones are marked for the user to verify."""
    parts = []
    for a in aligned:
        if a["supported"]:
            parts.append(f"{a['sentence']} [{a['segment_id']}]")
        elif a["novel_terms"]:
            parts.append(f"{a['sentence']} ⚠ _(not found in transcript: {', '.join(a['novel_terms'])})_")
        else:
            parts.append(f"{a['sentence']} ⚠ _(weak evidence)_" + (f" [{a['segment_id']}]" if a["segment_id"] else ""))
    return " ".join(parts)

"""Zero-shot dialogue-act classification with a multilingual NLI model (F38, F57; workflow F).

Each sentence is paired with hypotheses such as "The speaker makes a decision."
or "The speaker asks a question." and an NLI model
(MoritzLaurer/mDeBERTa-v3-base-mnli-xnli, multilingual) scores entailment.
This needs no labelled training data and works for Hindi/Telugu/English.

Measured finding: zero-shot NLI separates questions/requests/suggestions
reasonably but rarely recognises *decisions* (deciding vs. suggesting is a
pragmatic distinction). It is therefore only a second opinion next to the rules:
* it raises the confidence of rule-detected items it agrees with (never lowers it);
* it does not add new decisions — an earlier version did, and on the held-out
  transcript that only introduced false positives.
Opt in with MEETBRIEF_DIALOGUE_ACTS=hybrid (the evaluation always measures it).
"""
from __future__ import annotations

import os
from typing import Optional

from backend.hf import models as hf

# Hypothesis wording chosen by a small comparison on labelled sentences (see run_eval: dialogue_acts).
ACTS = {
    "decision": "makes a decision",
    "proposal": "suggests an idea",
    "task": "asks someone to do something",
    "question": "asks a question",
    "other": "describes a situation",
}
TEMPLATE = "The speaker {}."


def mode() -> str:
    # off by default: ~0.35 s per sentence on CPU for little measured benefit (see evaluation results)
    return os.environ.get("MEETBRIEF_DIALOGUE_ACTS", "rules").lower()


def available() -> bool:
    return mode() == "hybrid" and hf.enabled("nli")


def classify(sentences: list[str]) -> Optional[list[dict]]:
    """[{act, score, scores:{act: p}, entailment:{act: p}}] or None when the model is unavailable."""
    if not sentences or not available():
        return None
    names = list(ACTS)
    raw = hf.zero_shot(sentences, [ACTS[n] for n in names], TEMPLATE)
    if raw is None:
        return None
    out = []
    for r in raw:
        scores = dict(zip(names, r["scores"]))
        ent = dict(zip(names, r["entailment"]))
        act = max(scores, key=scores.get)
        out.append({"act": act, "score": round(scores[act], 3), "scores": scores, "entailment": ent})
    return out

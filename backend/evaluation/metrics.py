"""Dependency-free evaluation metrics: ROUGE-1/2/L F1 and precision/recall/F1."""
from __future__ import annotations

import re
from collections import Counter


def _tokens(text: str) -> list[str]:
    text = re.sub(r"\[S\d+-[0-9a-f]{6}\]", " ", text)  # drop citation markers
    text = re.sub(r"[*_~`#>|]", " ", text)
    return re.findall(r"[\wऀ-෿']+", text.lower())


def _ngrams(tokens: list[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def _f1(p: float, r: float) -> float:
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def rouge_n(candidate: str, reference: str, n: int) -> dict:
    c, r = _ngrams(_tokens(candidate), n), _ngrams(_tokens(reference), n)
    overlap = sum((c & r).values())
    p = overlap / max(sum(c.values()), 1)
    rec = overlap / max(sum(r.values()), 1)
    return {"p": p, "r": rec, "f": _f1(p, rec)}


def _lcs(a: list[str], b: list[str]) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def rouge_l(candidate: str, reference: str) -> dict:
    c, r = _tokens(candidate), _tokens(reference)
    lcs = _lcs(c, r)
    p, rec = lcs / max(len(c), 1), lcs / max(len(r), 1)
    return {"p": p, "r": rec, "f": _f1(p, rec)}


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(_f1(p, r), 3), "tp": tp, "fp": fp, "fn": fn}


def wer(hypothesis: str, reference: str) -> float:
    """Word error rate = (substitutions + deletions + insertions) / reference words (Levenshtein on words)."""
    h, r = _tokens(hypothesis), _tokens(reference)
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = cur
    return prev[-1] / max(len(r), 1)


def chrf(hypothesis: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    """chrF (Popović, 2015): character n-gram F-beta score, averaged over n = 1..6. Works for any script."""
    hyp, ref = re.sub(r"\s+", " ", hypothesis.strip()), re.sub(r"\s+", " ", reference.strip())
    precs, recs = [], []
    for k in range(1, n + 1):
        hc = Counter(hyp[i:i + k] for i in range(len(hyp) - k + 1))
        rc = Counter(ref[i:i + k] for i in range(len(ref) - k + 1))
        if not hc or not rc:
            continue
        ov = sum((hc & rc).values())
        precs.append(ov / sum(hc.values()))
        recs.append(ov / sum(rc.values()))
    if not precs:
        return 0.0
    p, r = sum(precs) / len(precs), sum(recs) / len(recs)
    return 0.0 if p + r == 0 else (1 + beta ** 2) * p * r / (beta ** 2 * p + r)


def speaker_accuracy(pred: list, gold: list) -> float:
    """Best one-to-one mapping of predicted cluster labels to gold speakers (greedy), then accuracy."""
    from collections import defaultdict

    counts: dict = defaultdict(Counter)
    for p, g in zip(pred, gold):
        counts[p][g] += 1
    used, mapping = set(), {}
    pairs = sorted(((c, p, g) for p, cs in counts.items() if p is not None for g, c in cs.items()),
                   key=lambda x: -x[0])
    for c, p, g in pairs:
        if p in mapping or g in used or p is None:
            continue
        mapping[p] = g
        used.add(g)
    return sum(mapping.get(p) == g for p, g in zip(pred, gold)) / max(len(gold), 1)

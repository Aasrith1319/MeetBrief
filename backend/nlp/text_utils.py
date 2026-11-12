"""Shared lightweight text utilities: sentence splitting, tokens, TF-IDF, TextRank."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np

STOPWORDS = set(
    """a about above after again against all also am an and any are aren't as at be because been before being
    below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during
    each few for from further get got had hadn't has hasn't have haven't having he he'd he'll he's her here here's
    hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself just let's
    like me more most mustn't my myself no nor not now of off ok okay on once only or other ought our ours
    ourselves out over own really right same say shan't she she'd she'll she's should shouldn't so some such
    sure than that that's the their theirs them themselves then there there's these they they'd they'll they're
    they've this those through to too um uh under until up us very was wasn't we we'd we'll we're we've were
    weren't what what's when when's where where's which while who who's whom why why's will with won't would
    wouldn't yeah yes you you'd you'll you're you've your yours yourself yourselves going gonna think know mean
    want need also maybe suggest suggested consider could first okay let lets said one two thing things lot well actually basically please thanks thank hi hello guys
    hai hain ka ke ki ko se mein hum aap kya bhi aur toh nahi abhi pehle karna karenge raha liye
    undi ledu manam meeru nenu inka chala""".split()
)

_SENT_RE = re.compile(r"(?<=[.!?।॥])\s+(?=[\"'“(]?[A-Z0-9ऀ-෿])")
_TOKEN_RE = re.compile(r"[\wऀ-෿']+", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2 and not t.isdigit()]


def tfidf_matrix(texts: Sequence[str]):
    """Return (matrix, vectorizer) of L2-normalised TF-IDF vectors (dense numpy)."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = [t if t.strip() else "_empty_" for t in texts]
    vec = TfidfVectorizer(
        tokenizer=content_tokens, token_pattern=None, lowercase=False, sublinear_tf=True, ngram_range=(1, 2), min_df=1
    )
    try:
        mat = vec.fit_transform(docs)
    except ValueError:  # empty vocabulary
        return np.zeros((len(docs), 1)), None
    return mat.toarray(), vec


def cosine_matrix(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = mat / norms
    return normed @ normed.T


def textrank(sentences: Sequence[str], damping: float = 0.85, iterations: int = 60) -> np.ndarray:
    """Score sentences by PageRank over a TF-IDF cosine similarity graph."""
    n = len(sentences)
    if n == 0:
        return np.zeros(0)
    if n == 1:
        return np.ones(1)
    mat, _ = tfidf_matrix(sentences)
    sim = cosine_matrix(mat)
    np.fill_diagonal(sim, 0.0)
    row_sums = sim.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    trans = sim / row_sums
    scores = np.ones(n) / n
    for _ in range(iterations):
        scores = (1 - damping) / n + damping * trans.T @ scores
    # light length prior: very short utterances ("ok", "sure") are rarely summary-worthy
    lengths = np.array([min(len(content_tokens(s)), 12) for s in sentences], dtype=float)
    return scores * (0.4 + lengths / 12.0)


def top_keywords(texts: Iterable[str], k: int = 3) -> list[str]:
    texts = list(texts)
    if not texts:
        return []
    mat, vec = tfidf_matrix(texts)
    if vec is None:
        return []
    weights = mat.sum(axis=0)
    names = vec.get_feature_names_out()
    order = np.argsort(-weights)
    picked: list[str] = []
    for i in order:
        name = names[i]
        if any(name in p or p in name for p in picked):
            continue
        picked.append(name)
        if len(picked) >= k:
            break
    return picked


def format_time(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@lru_cache(maxsize=1)
def negation_words() -> frozenset[str]:
    return frozenset({"not", "no", "never", "don't", "won't", "shouldn't", "can't", "cannot", "isn't", "aren't",
                      "wasn't", "didn't", "doesn't", "nahi", "nahin", "mat", "ledu", "kaadu", "vaddu"})


def has_negation(text: str) -> bool:
    toks = set(tokenize(text))
    return bool(toks & negation_words()) or "n't" in text.lower()

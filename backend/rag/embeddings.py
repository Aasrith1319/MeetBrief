"""Text representations for semantic search (F51).

Hybrid retrieval = sparse + dense:
* sparse: word uni/bi-gram TF-IDF + character 3-5-gram TF-IDF (robust to
  inflection, typos and romanised/mixed-language text);
* dense: multilingual sentence embeddings
  (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, local Hugging Face
  model) so paraphrases match ("lagging" ~ "slow") across languages.
The final score is the average of the sparse and dense cosine similarities; if
the dense model is unavailable the sparse score is used alone.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from backend.hf import models as hf
from backend.nlp.text_utils import content_tokens

_vec_cache: dict[str, np.ndarray] = {}


def dense_available() -> bool:
    return hf.enabled("embedding")


def embed_cached(texts: list[str]) -> Optional[np.ndarray]:
    missing = [t for t in dict.fromkeys(texts) if t not in _vec_cache]
    if missing:
        vecs = hf.embed(missing)
        if vecs is None:
            return None
        for t, v in zip(missing, vecs):
            _vec_cache[t] = np.asarray(v)
        if len(_vec_cache) > 50_000:
            _vec_cache.clear()
    return np.stack([_vec_cache[t] for t in texts]) if texts else np.zeros((0, 1))


class HybridIndex:
    """Fits on a set of documents; scores queries with cosine similarity."""

    def __init__(self, docs: Sequence[str]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.docs = [d if d.strip() else "_" for d in docs]
        self.word = TfidfVectorizer(tokenizer=content_tokens, token_pattern=None, lowercase=False,
                                    sublinear_tf=True, ngram_range=(1, 2))
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)
        try:
            self.word_m = self.word.fit_transform(self.docs)
        except ValueError:
            self.word = None
            self.word_m = None
        self.char_m = self.char.fit_transform(self.docs)
        self.dense = embed_cached(list(self.docs)) if dense_available() else None

    def scores(self, query: str) -> np.ndarray:
        n = len(self.docs)
        total = np.zeros(n)
        weight = 0.0
        if self.word is not None:
            q = self.word.transform([query])
            if q.nnz:
                total += 0.6 * (self.word_m @ q.T).toarray().ravel()
                weight += 0.6
        qc = self.char.transform([query])
        total += 0.4 * (self.char_m @ qc.T).toarray().ravel()
        weight += 0.4
        sparse = total / weight if weight else total
        if self.dense is not None:
            qd = embed_cached([query])
            if qd is not None:
                return 0.5 * sparse + 0.5 * (self.dense @ qd[0])
        return sparse

    def search(self, query: str, k: int = 5, mask: Optional[np.ndarray] = None) -> list[tuple[int, float]]:
        s = self.scores(query)
        if mask is not None:
            s = np.where(mask, s, -1.0)
        order = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in order if s[i] > 0]

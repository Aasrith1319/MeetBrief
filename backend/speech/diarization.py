"""Speaker diarization — "who spoke when" (F34; workflow D).

Embedding-based diarization with a local Hugging Face model
(microsoft/wavlm-base-plus-sv, an x-vector speaker-verification model):

1. Whisper gives speech segments with timestamps.
2. Each segment (>= MIN_SEC of audio) is embedded into a speaker vector.
3. Online clustering: a segment joins the closest existing speaker centroid
   if cosine similarity >= threshold, otherwise it starts a new speaker.
   Centroids are stored per meeting, so labels stay consistent across the
   15-second audio chunks the extension uploads.

Diarization yields generic labels (Speaker 1, Speaker 2 ...); it never reveals
real names. Very short segments are left unknown rather than guessed.
Limitations: overlapping speech and speaker changes inside one Whisper segment
are not split.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from backend.config import settings
from backend.hf import models as hf

SR = 16000
MIN_SEC = 0.8
MAX_SEC = 10.0


def diarization_available() -> dict:
    if not hf.enabled("speaker"):
        return {"available": False, "reason": hf.status()["tasks"]["speaker"]["error"]
                or "speaker model unavailable (pip install -r requirements-ml.txt)"}
    return {"available": True, "model": hf.MODELS["speaker"], "threshold": settings.speaker_threshold}


def _crop(audio: np.ndarray, start: float, end: float) -> Optional[np.ndarray]:
    if end - start < MIN_SEC:
        return None
    mid = (start + end) / 2
    if end - start > MAX_SEC:
        start, end = mid - MAX_SEC / 2, mid + MAX_SEC / 2
    wave = audio[int(start * SR): int(end * SR)]
    return wave if len(wave) >= MIN_SEC * SR else None


def assign(embeddings: np.ndarray, centroids: list[dict], threshold: float) -> tuple[list[str], list[dict]]:
    """Online clustering of L2-normalised embeddings against running centroids."""
    labels = []
    for emb in embeddings:
        best, best_sim = None, -1.0
        for c in centroids:
            sim = float(np.dot(emb, np.asarray(c["vec"])))
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            n = best["n"]
            vec = (np.asarray(best["vec"]) * n + emb) / (n + 1)
            best["vec"] = (vec / (np.linalg.norm(vec) or 1.0)).tolist()
            best["n"] = n + 1
            labels.append(best["label"])
        else:
            label = f"SPEAKER_{len(centroids):02d}"
            centroids.append({"label": label, "vec": emb.tolist(), "n": 1})
            labels.append(label)
    return labels, centroids


def diarize(audio: np.ndarray, segments: list[dict], centroids: list[dict],
            threshold: Optional[float] = None) -> tuple[list[Optional[str]], list[dict]]:
    """Return a speaker label (or None) per ASR segment and the updated centroids."""
    threshold = settings.speaker_threshold if threshold is None else threshold
    waves, idx = [], []
    for i, seg in enumerate(segments):
        w = _crop(audio, seg["start"], seg["end"])
        if w is not None:
            waves.append(w)
            idx.append(i)
    labels: list[Optional[str]] = [None] * len(segments)
    if not waves:
        return labels, centroids
    embs = hf.speaker_embeddings(waves)
    if embs is None:
        return labels, centroids
    found, centroids = assign(np.asarray(embs), centroids, threshold)
    for i, lab in zip(idx, found):
        labels[i] = lab
    return labels, centroids

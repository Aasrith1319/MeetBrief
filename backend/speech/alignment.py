"""Align ASR segments with diarization turns (workflow D step 4)."""
from __future__ import annotations

from typing import Optional


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def assign_speakers(asr_segments: list[dict], turns: list[dict], min_ratio: float = 0.5) -> list[dict]:
    """Give each ASR segment the diarization speaker with maximal temporal overlap.

    If no speaker covers at least ``min_ratio`` of the segment (overlapping
    speech, very short utterances), the speaker is left unknown and flagged.
    Word timestamps, when present, are used for a finer majority vote.
    """
    out = []
    for seg in asr_segments:
        start, end = seg["start"], seg["end"]
        duration = max(end - start, 1e-6)
        votes: dict[str, float] = {}
        units = seg.get("words") or [{"start": start, "end": end}]
        for w in units:
            for t in turns:
                ov = _overlap(w["start"], w["end"], t["start"], t["end"])
                if ov > 0:
                    votes[t["speaker"]] = votes.get(t["speaker"], 0.0) + ov
        speaker: Optional[str] = None
        flags = []
        if votes:
            speaker, best = max(votes.items(), key=lambda kv: kv[1])
            total_cov = sum(votes.values())
            if best / duration < min_ratio * 0.5 or (len(votes) > 1 and best / total_cov < 0.6):
                flags.append("speaker_uncertain")
        else:
            flags.append("speaker_unknown")
        out.append({**seg, "speaker": speaker, "flags": flags})
    return out


def friendly_label(raw: Optional[str], order: dict[str, int]) -> Optional[str]:
    """SPEAKER_00 -> 'Speaker 1' (stable within a meeting)."""
    if raw is None:
        return None
    if raw not in order:
        order[raw] = len(order) + 1
    return f"Speaker {order[raw]}"

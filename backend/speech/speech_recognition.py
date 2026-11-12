"""Automatic speech recognition for authorised meeting-tab audio (F04; workflow L).

Uses faster-whisper (multilingual Whisper, CTranslate2) when installed via
``pip install -r requirements-audio.txt``. Audio chunks are written to a
temporary file only for the duration of transcription and always deleted.
"""
from __future__ import annotations

import os
import re
import tempfile
from functools import lru_cache
from typing import Optional

from backend.config import settings


class ASRUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _model():
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise ASRUnavailable("Speech recognition requires faster-whisper: pip install -r requirements-audio.txt") from exc
    return WhisperModel(settings.whisper_model, device="auto", compute_type="int8")


def asr_available() -> dict:
    try:
        import faster_whisper  # type: ignore  # noqa: F401

        return {"available": True, "model": settings.whisper_model}
    except ImportError:
        return {"available": False, "reason": "faster-whisper not installed (pip install -r requirements-audio.txt)"}


def decode_audio(path: str, sr: int = 16000):
    """Decode any container/codec PyAV can read (webm/opus, wav, ogg, mp3...) to mono float32 at 16 kHz.

    Done here instead of faster-whisper's own decoder so the code works across PyAV versions.
    """
    import av  # type: ignore
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
    chunks = []
    with av.open(path, mode="r") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("no audio stream found")
        for frame in container.decode(stream):
            frame.pts = None
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("audio chunk contained no samples")
    return (np.concatenate(chunks).astype(np.float32) / 32768.0)


# Unicode block each Indian language is written in: Whisper sometimes writes Telugu/Kannada speech in the wrong script
SCRIPTS = {"te": (0x0C00, 0x0C7F), "kn": (0x0C80, 0x0CFF), "hi": (0x0900, 0x097F), "ta": (0x0B80, 0x0BFF),
           "ml": (0x0D00, 0x0D7F), "bn": (0x0980, 0x09FF), "mr": (0x0900, 0x097F), "gu": (0x0A80, 0x0AFF),
           "pa": (0x0A00, 0x0A7F)}
# Phrases Whisper invents on silence, notification sounds or music (kept when clearly spoken, see _keep)
HALLUCINATIONS = {"thank you", "thanks", "thank you very much", "thanks for watching", "thank you for watching",
                  "participants", "subtitles by the amara.org community", "please subscribe", "bye", "you", "okay",
                  "music", "applause", "silence"}
REPEAT_RE = re.compile(r"(.{2,12}?)\1{4,}")  # "రూతూరూతూరూతూ..." decoding loops
WINDOW_S = 30.0  # long recordings are processed per window so each part gets its own language
# Languages whose own-script text Whisper (small) gets wrong almost every time: show only the English of the speech
# (set MEETBRIEF_NATIVE_TEXT=all with a larger Whisper model, e.g. medium, to write them in their own script too)
NATIVE_UNRELIABLE = set() if os.environ.get("MEETBRIEF_NATIVE_TEXT") == "all" else {"te", "kn"}


def _keep(seg) -> bool:
    text = seg.text.strip()
    if not text or REPEAT_RE.search(text.replace(" ", "")):
        return False
    if getattr(seg, "compression_ratio", 0) > 2.4:
        return False
    no_speech, logprob = getattr(seg, "no_speech_prob", 0.0), getattr(seg, "avg_logprob", 0.0)
    if no_speech > 0.6 and logprob < -1.0:  # Whisper's own silence rule
        return False
    norm = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if norm in HALLUCINATIONS and (no_speech > 0.2 or logprob < -0.45):
        return False
    return True


def script_ok(text: str, language: str) -> bool:
    """True when `text` is written in the script its language uses (always true for unlisted languages)."""
    rng = SCRIPTS.get(language)
    if not rng:
        return True
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(rng[0] <= ord(c) <= rng[1] for c in letters) / len(letters) >= 0.6


def pick_language(model, audio) -> tuple[Optional[str], float]:
    """Whisper's language guess, limited to the meeting languages (settings.meeting_languages)."""
    try:
        _, _, probs = model.detect_language(audio, vad_filter=True)
    except Exception:  # nothing speech-like in the audio
        return None, 0.0
    allowed = settings.meeting_languages
    cands = [(lang, p) for lang, p in probs if not allowed or lang in allowed] or list(probs)
    lang, p = max(cands, key=lambda x: x[1])
    total = sum(x[1] for x in cands) or 1.0
    return lang, p / total


def _segments(model, audio, language: str, task: str, beam: int = 5) -> list:
    segs, _ = model.transcribe(audio, language=language, task=task, vad_filter=True, word_timestamps=task == "transcribe",
                               beam_size=beam, temperature=0.0,  # no temperature retries: each costs a full decode
                               condition_on_previous_text=False, hallucination_silence_threshold=2.0, max_new_tokens=160)
    return [s for s in segs if _keep(s)]


def _transcribe_window(model, audio, language: Optional[str], prob: float = 1.0) -> tuple[str, float, list[dict]]:
    lang, prob = (language, prob) if language else pick_language(model, audio)
    if not lang:
        return "und", 0.0, []
    # the original-language text is for display only (the models read the English), so a quicker greedy pass is enough
    native = [] if lang in NATIVE_UNRELIABLE else _segments(model, audio, lang, "transcribe", beam=1 if lang != "en" else 5)
    words = lambda seg: [{"start": float(w.start), "end": float(w.end), "word": w.word} for w in (seg.words or [])]
    if lang == "en":
        return lang, prob, [{"start": float(s.start), "end": float(s.end), "text": s.text.strip(), "text_en": None,
                             "confidence": float(s.avg_logprob), "words": words(s)} for s in native]
    # Not English: Whisper also translates the speech straight into English. That is far more reliable than
    # translating its transcript afterwards (Whisper often garbles Telugu/Kannada text but understands the speech).
    english = _segments(model, audio, lang, "translate")
    # Whisper splits the original and the English differently: overlapping pieces form one line, so every original
    # sentence appears once, next to all of its English
    groups: list[tuple[list, list]] = []
    for e in english:
        hit = [g for g in groups if any(n.end > e.start and n.start < e.end for n in g[1])]
        mine = [n for n in native if n.end > e.start and n.start < e.end and not any(n in g[1] for g in groups)]
        if hit:
            hit[0][0].append(e)
            hit[0][1].extend(mine)
        else:
            groups.append(([e], mine))
    out = []
    for ens, nats in groups:
        nats = sorted(nats, key=lambda n: n.start)
        original = " ".join(n.text.strip() for n in nats).strip()
        if not script_ok(original, lang):
            original = ""  # wrong script / garbled: show the English with "translated from …" instead
        text_en = " ".join(e.text.strip() for e in ens)
        out.append({"start": float(min([e.start for e in ens] + [n.start for n in nats])),
                    "end": float(max([e.end for e in ens] + [n.end for n in nats])),
                    "text": original or text_en, "text_en": text_en,
                    "confidence": float(sum(e.avg_logprob for e in ens) / len(ens)),
                    "words": [w for n in nats for w in words(n)]})
    return lang, prob, out


def language_runs(model, audio, sr: int = 16000) -> list[tuple[int, int, Optional[str], float]]:
    """Split audio on pauses and detect the language of each utterance, so a speaker switching from Kannada to
    Hindi inside one chunk gets both right. Returns runs of consecutive same-language speech:
    [(start_sample, end_sample, language, probability)]."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    spans = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=400, speech_pad_ms=200))
    if not spans:
        return []
    utts = []  # merge fragments into utterances of >= 1.5 s so each language guess has enough speech
    for sp in spans:
        if utts and (sp["start"] - utts[-1][1] < 0.3 * sr or utts[-1][1] - utts[-1][0] < 1.5 * sr):
            utts[-1][1] = sp["end"]
        else:
            utts.append([sp["start"], sp["end"]])
    runs = []
    for a, b in utts:
        lang, prob = pick_language(model, audio[a:b])
        if runs and runs[-1][2] == lang:
            runs[-1] = (runs[-1][0], b, lang, max(runs[-1][3], prob))
        else:
            runs.append((a, b, lang, prob))
    return runs


def transcribe_path(path: str, language: Optional[str] = None) -> dict:
    """Transcribe an audio/video file on disk (any container PyAV can decode).

    Each segment has "text" (what was said, in its own language and script when Whisper wrote it reliably) and
    "text_en" (Whisper's English translation of the speech; None for English)."""
    model = _model()
    audio = decode_audio(path)
    sr, langs, out = 16000, [], []
    step = int(WINDOW_S * sr)
    spans = [(0, len(audio))] if len(audio) <= step * 4 / 3 else [(i, min(i + step, len(audio))) for i in range(0, len(audio), step)]
    pieces = []
    for a, b in spans:
        if language:
            pieces.append((a, b, language, 1.0))
        else:  # one piece per run of same-language speech (padded so words at the edges are not cut)
            pad = int(0.25 * sr)
            pieces += [(max(a, a + ra - pad), min(b, a + rb + pad), lang, p)
                       for ra, rb, lang, p in language_runs(model, audio[a:b]) if lang]
    for a, b, lang_hint, p_hint in pieces:
        lang, prob, segs = _transcribe_window(model, audio[a:b], lang_hint, p_hint)
        off = a / sr
        for seg in segs:
            seg.update(start=seg["start"] + off, end=seg["end"] + off, language=lang)
            for w in seg["words"]:
                w.update(start=w["start"] + off, end=w["end"] + off)
        out += segs
        if segs:
            langs.append((lang, prob, sum(x["end"] - x["start"] for x in segs)))
    main = max(langs, key=lambda x: x[2]) if langs else ("und", 0.0, 0)
    return {"language": main[0], "language_probability": float(main[1]), "segments": out,
            "duration": len(audio) / sr, "audio": audio}


def transcribe_bytes(data: bytes, suffix: str = ".webm", language: Optional[str] = None) -> dict:
    """Return {"language", "language_probability", "segments": [{start, end, text, words}], "audio": waveform}.

    The waveform is returned in memory only (for diarization); nothing is persisted."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="meetbrief_audio_")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return transcribe_path(path, language)
    finally:
        # minimise raw-audio retention: delete immediately after processing
        try:
            os.remove(path)
        except OSError:
            pass

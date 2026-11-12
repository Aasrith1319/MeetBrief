"""Translation / target-language output (F25, F27, F28, F30, F32; workflow B).

Engine: NLLB-200 (facebook/nllb-200-distilled-600M), run locally. It covers
English, Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi and more.

Markdown-aware: headings/bullets/bold markers and [S…] evidence citations are
kept out of the model input and re-attached, so translated summaries still link
to their transcript evidence. :func:`preservation_check` then verifies that
numbers/dates survive translation (owners and deadlines must not change).
"""
from __future__ import annotations

import re
from typing import Optional

from backend.hf import models as hf
from backend.nlp.language_detection import detect_language, language_name
from backend.nlp.text_utils import split_sentences

CITE_RE = re.compile(r"\s*\[(?:S\d+-[0-9a-f]{6}(?:,\s*)?)+\]")
PREFIX_RE = re.compile(r"^(\s*(?:[-*•]|\d+[.)])\s+|\s*#{1,4}\s+)")


def _base(code: Optional[str]) -> str:
    return (code or "und").split("-")[0].lower()


_NATIVE_DIGITS = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")


def preservation_check(source: str, translated: str) -> list[str]:
    """Numbers, times and dates must survive translation (NLLB may emit native digits, e.g. Devanagari ४)."""
    src_nums = set(re.findall(r"\d+(?:[.:/]\d+)*", CITE_RE.sub("", source)))
    out_nums = set(re.findall(r"\d+(?:[.:/]\d+)*", CITE_RE.sub("", translated).translate(_NATIVE_DIGITS)))
    missing = src_nums - out_nums
    return [f"Numbers/dates possibly lost in translation: {', '.join(sorted(missing))}"] if missing else []


MARKER_RE = re.compile(r"(\s*(?:⚠\s*)?_\([^)]*\)_|\s*\[(?:S\d+-[0-9a-f]{6}(?:,\s*)?)+\]|\s*⚠️?)")
SPEAKER_RE = re.compile(r"^([\w .'\-]{1,40}?):\s+(.*)$", re.S)


def _pieces(line: str) -> tuple[str, list[str]]:
    """-> (list prefix, alternating [text, marker, text, ...]) so markers stay where they were."""
    m = PREFIX_RE.match(line)
    prefix = m.group(1) if m else ""
    return prefix, MARKER_RE.split(line[len(prefix):])


def translate(text: str, target: str, source: Optional[str] = None) -> dict:
    target_b = _base(target)
    detected = source or detect_language(CITE_RE.sub("", text)).language
    base = {"source_language": detected, "target_language": target}
    if not text.strip():
        return {**base, "text": text, "translated": False, "engine": None, "warnings": []}
    if _base(detected) == target_b and "-" not in (detected or ""):
        return {**base, "text": text, "translated": False, "engine": "identity", "warnings": []}
    src = "en" if (detected or "").endswith("-en") or _base(detected) == "und" else _base(detected)
    if target_b not in hf.NLLB_CODES or src not in hf.NLLB_CODES:
        return {**base, "text": text, "translated": False, "engine": None,
                "warnings": [f"Translation between {language_name(src)} and {language_name(target_b)} is not supported."]}

    lines = text.split("\n")
    plan = []      # per line: (prefix, pieces, {piece index: (sentences, bold, speaker)})
    flat: list[str] = []
    for line in lines:
        prefix, pieces = _pieces(line)
        jobs = {}
        for i in range(0, len(pieces), 2):  # even indices are text, odd are markers
            core = pieces[i].strip()
            if not core or not re.search(r"[^\W\d_]", core):
                continue
            bold = bool(re.fullmatch(r"\*\*[^*]+\*\*:?", core))
            core = core.strip("*").rstrip(":") if bold else core
            speaker = None
            m = SPEAKER_RE.match(core)
            if m and len(m.group(1).split()) <= 3:  # keep "Speaker: " labels untranslated so names stay intact
                speaker, core = m.group(1), m.group(2)
            sents = split_sentences(core) or [core]
            jobs[i] = (len(flat), len(sents), bold, speaker)
            flat.extend(sents)
        plan.append((prefix, pieces, jobs))
    translated = hf.translate_sentences(flat, src, target_b) if flat else []
    if translated is None:
        return {**base, "text": text, "translated": False, "engine": None,
                "warnings": [f"Translation to {language_name(target_b)} is unavailable: the NLLB model is not installed "
                             "or failed to load (pip install -r requirements-ml.txt; python -m backend.hf.download mt). "
                             "Showing the original text."]}
    out_lines = []
    for prefix, pieces, jobs in plan:
        pieces = list(pieces)
        for i, (start, n, bold, speaker) in jobs.items():
            new = " ".join(translated[start:start + n])
            if speaker:
                new = f"{speaker}: {new}"
            lead = " " if pieces[i][:1].isspace() and i else ""
            pieces[i] = lead + (f"**{new}**" if bold else new)
        out_lines.append(prefix + "".join(pieces))
    out = "\n".join(out_lines)
    return {**base, "text": out, "translated": True, "engine": hf.MODELS["mt"],
            "warnings": preservation_check(text, out)}

"""Segment-level language identification (F26) with code-switching hints (F29).

Strategy:
1. Unicode script ranges identify Indic scripts reliably (Telugu, Devanagari, ...).
2. Romanised Hindi/Telugu marker words flag code-switched "Hinglish"/"Tenglish".
3. langdetect (seeded, deterministic) handles Latin-script languages.
Short or ambiguous text is reported as "und" with low confidence rather than guessed.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from backend.nlp.text_utils import tokenize

SCRIPT_RANGES = {
    "te": (0x0C00, 0x0C7F),  # Telugu
    "hi": (0x0900, 0x097F),  # Devanagari (Hindi / Marathi / Nepali)
    "ta": (0x0B80, 0x0BFF),
    "kn": (0x0C80, 0x0CFF),
    "ml": (0x0D00, 0x0D7F),
    "bn": (0x0980, 0x09FF),
    "gu": (0x0A80, 0x0AFF),
    "pa": (0x0A00, 0x0A7F),
    "ar": (0x0600, 0x06FF),
    "zh": (0x4E00, 0x9FFF),
    "ja": (0x3040, 0x30FF),
    "ko": (0xAC00, 0xD7AF),
    "ru": (0x0400, 0x04FF),
}

ROMAN_HINDI = {"hai", "hain", "nahi", "nahin", "kya", "karo", "karna", "kar", "acha", "accha", "theek", "thik",
               "matlab", "yaar", "kuch", "bhi", "aur", "lekin", "chahiye", "hoga", "raha", "rahe", "wala",
               "kal", "abhi", "toh", "mein", "hum", "aap", "kaise", "kyun", "bahut", "jaldi", "kaam", "dekho"}
ROMAN_TELUGU = {"cheyyali", "cheddam", "ledu", "undi", "emiti", "chesanu", "kada", "anukunta", "chala",
                "baagundi", "manam", "meeru", "nenu", "avunu", "kaadu", "ippudu", "repu", "inka", "enti",
                "cheppandi", "chestanu", "vaddu", "sare", "ayyindi", "pani"}

LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam",
    "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi", "mr": "Marathi", "es": "Spanish", "fr": "French",
    "de": "German", "it": "Italian", "pt": "Portuguese", "ar": "Arabic", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "ru": "Russian", "nl": "Dutch", "und": "Undetermined",
    "hi-en": "Hindi-English (code-switched)", "te-en": "Telugu-English (code-switched)",
}


@dataclass
class LanguageResult:
    language: str
    confidence: float
    code_switched: bool = False
    scripts: dict[str, int] | None = None

    def as_dict(self) -> dict:
        return {"language": self.language, "name": LANGUAGE_NAMES.get(self.language, self.language),
                "confidence": round(self.confidence, 3), "code_switched": self.code_switched,
                "scripts": self.scripts or {}}


def _script_counts(text: str) -> Counter:
    counts: Counter = Counter()
    for ch in text:
        cp = ord(ch)
        if ch.isspace() or not ch.isalpha():
            continue
        if cp < 0x0250:
            counts["latin"] += 1
            continue
        for lang, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[lang] += 1
                break
        else:
            counts["other"] += 1
    return counts


def detect_language(text: str) -> LanguageResult:
    text = text.strip()
    if not text:
        return LanguageResult("und", 0.0)
    scripts = _script_counts(text)
    total = sum(scripts.values()) or 1
    non_latin = {k: v for k, v in scripts.items() if k not in {"latin", "other"}}
    latin = scripts.get("latin", 0)

    if non_latin:
        lang, count = max(non_latin.items(), key=lambda kv: kv[1])
        share = count / total
        mixed = latin / total > 0.2
        if mixed:
            return LanguageResult(f"{lang}-en", min(0.95, 0.5 + share / 2), True, dict(scripts))
        return LanguageResult(lang, min(0.99, 0.6 + share * 0.4), False, dict(scripts))

    tokens = tokenize(text)
    hi_hits = sum(t in ROMAN_HINDI for t in tokens)
    te_hits = sum(t in ROMAN_TELUGU for t in tokens)
    if tokens and (hi_hits >= 2 or te_hits >= 2 or (len(tokens) <= 6 and (hi_hits or te_hits))):
        lang = "te-en" if te_hits > hi_hits else "hi-en"
        ratio = max(hi_hits, te_hits) / len(tokens)
        return LanguageResult(lang, min(0.9, 0.45 + ratio), True, dict(scripts))

    if len(re.sub(r"\W", "", text)) < 12:
        return LanguageResult("und", 0.2, False, dict(scripts))
    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        best = detect_langs(text)[0]
        return LanguageResult(best.lang, float(best.prob), False, dict(scripts))
    except Exception:
        return LanguageResult("en" if latin else "und", 0.3, False, dict(scripts))


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)

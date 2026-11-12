"""Explain Again and text simplification (F16-F24; workflow C).

The output always separates:
* ``meeting_context`` — what the meeting actually said (retrieved, with segment refs)
* ``explanation``     — general explanation in the requested style/level/language:
  a curated glossary entry when the term is known, plus an explanation from a
  small instruction-tuned language model (Qwen2.5-1.5B-Instruct, local Hugging
  Face model; Flan-T5 selectable) for any term or sentence, labelled as
  model-generated general knowledge.
Non-English output is produced with NLLB-200.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.hf import models as hf
from backend.models import Segment
from backend.nlp.glossary import lookup, terms_in
from backend.nlp.language_detection import language_name
from backend.nlp.text_utils import format_time, split_sentences
from backend.nlp.translation import translate
from backend.rag.retrieval import MeetingRetriever

SIMPLE_WORDS = {
    "utilize": "use", "utilise": "use", "implement": "build", "implementation": "building", "facilitate": "help",
    "approximately": "about", "subsequently": "later", "commence": "start", "terminate": "end",
    "optimize": "improve", "optimise": "improve", "leverage": "use", "prioritize": "put first", "allocate": "give",
    "consider": "think about", "frequently": "often", "sufficient": "enough", "requirement": "need",
    "requirements": "needs", "additional": "extra", "modify": "change", "demonstrate": "show", "obtain": "get",
    "endeavor": "try", "ascertain": "find out", "methodology": "method", "functionality": "features",
    "deprecated": "no longer recommended", "bottleneck": "slowest part", "throughput": "amount handled per second",
    "latency": "delay", "scalable": "able to grow", "refactor": "clean up the code", "benchmark": "measure",
    "deploy": "release", "regression": "something that broke again", "asynchronous": "not waiting",
    "synchronous": "waiting for each step", "mitigate": "reduce", "comprehensive": "complete",
    "nevertheless": "still", "furthermore": "also", "consequently": "so", "therefore": "so", "prior to": "before",
    "in order to": "to", "with regard to": "about", "a number of": "some", "at this point in time": "now",
}


def simplify_text(text: str) -> str:
    """Rule-based lexical simplification + sentence shortening (F17)."""
    out = text
    for hard, easy in sorted(SIMPLE_WORDS.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(hard)}\b", easy, out, flags=re.I)
    sentences = []
    for s in split_sentences(out):
        # split long sentences on conjunctions
        if len(s.split()) > 18:
            parts = re.split(r",?\s+\b(?:and|but|which|because|so|while)\b\s+", s, maxsplit=2)
            parts = [p.strip().rstrip(".") for p in parts if p.strip()]
            sentences.extend(p[:1].upper() + p[1:] + "." for p in parts)
        else:
            sentences.append(s)
    return " ".join(sentences)


def _context(text: str, segments: list[Segment], segment_id: Optional[str]) -> list[Segment]:
    if not segments:
        return []
    retriever = MeetingRetriever(segments)
    picked: dict[str, Segment] = {}
    if segment_id:
        for s in retriever.neighbours(segment_id, radius=1):
            picked[s.segment_id] = s
    by_id = {s.segment_id: s for s in segments}
    for ev in retriever.retrieve(text, k=3):
        if ev.score and ev.score >= 0.1:
            picked[ev.segment_id] = by_id[ev.segment_id]
    return sorted(picked.values(), key=lambda s: s.idx)


PROMPTS_TERM = {
    "simplify": "Explain what \"{t}\" means in software/technology, in at most 4 short, simple sentences.",
    "example": "Give one practical example of \"{t}\" in software/technology, in at most 4 short sentences.",
    "step_by_step": "Explain step by step how \"{t}\" works, as at most 5 short numbered steps.",
    "detailed": "Give a precise technical explanation of \"{t}\" in at most 6 sentences.",
    "analogy": "Explain \"{t}\" with one everyday analogy, then say how the analogy maps to the real concept. "
               "At most 5 short sentences.",
}
PROMPTS_SENTENCE = {
    "simplify": "Rewrite this sentence from a meeting in simpler words and say what it means, in at most 3 short "
                "sentences: \"{t}\"",
    "example": "Explain this sentence from a meeting with a practical example, in at most 4 short sentences: \"{t}\"",
    "step_by_step": "Explain this sentence from a meeting as at most 5 short numbered steps: \"{t}\"",
    "detailed": "Explain this sentence from a meeting in technical detail, in at most 6 sentences: \"{t}\"",
    "analogy": "Explain this sentence from a meeting with an everyday analogy, in at most 4 short sentences: \"{t}\"",
}
LEVEL_PREFIX = {"beginner": "The reader is a beginner. ", "intermediate": "The reader knows the basics. ",
                "advanced": "The reader is an engineer. ", "expert": "The reader is an expert; be precise. "}
PREAMBLE_RE = re.compile(r"^\s*(?:sure|certainly|of course|absolutely|great question)[!.,]?\s*(?:here(?:'s| is)[^:\n]*[:.])?\s*",
                         re.I)


def model_explanation(text: str, style: str, difficulty: str, again: bool) -> str | None:
    is_term = len(text.split()) <= 5 and not text.rstrip().endswith((".", "?", "!"))
    template = (PROMPTS_TERM if is_term else PROMPTS_SENTENCE).get(style, PROMPTS_TERM["simplify"])
    prompt = LEVEL_PREFIX.get(difficulty, "") + template.format(t=text.strip())
    if again:
        prompt += " Use a different explanation from the usual textbook one."
    out = hf.generate(prompt, max_new_tokens=200 if style in ("detailed", "step_by_step") else 150, sample=again,
                      min_new_tokens=8)
    if not out:
        return None
    out = PREAMBLE_RE.sub("", out).strip()
    if style == "step_by_step" and not re.search(r"^\s*1[.)]", out, re.M):
        steps = [s.strip(" .") for s in re.split(r"(?<=[.!?])\s+", out) if len(s.strip()) > 3]
        if len(steps) > 1:
            return "\n".join(f"{i}. {s}." for i, s in enumerate(steps, 1))
    return out


def explain(text: str, segments: list[Segment], style: str = "simplify", difficulty: str = "beginner",
            language: str = "en", segment_id: Optional[str] = None, previous: Optional[str] = None) -> dict:
    ctx = _context(text, segments, segment_id)
    ctx_out = [{"segment_id": s.segment_id, "speaker": s.speaker_label, "start_time": s.start_time, "text": s.text} for s in ctx]
    return _local_explain(text, ctx, ctx_out, style, difficulty, language, previous)


def _local_explain(text, ctx, ctx_out, style, difficulty, language, previous) -> dict:
    key, entry = lookup(text)
    if not entry:
        found = terms_in(text)
        if found:
            key, entry = lookup(found[0])
    lines: list[str] = ["**In this meeting**"]
    if ctx:
        for s in ctx[:3]:
            lines.append(f"- {s.speaker_label} ({format_time(s.start_time)}): {s.text} [{s.segment_id}]")
    else:
        lines.append("- The captured transcript doesn't mention this directly.")
    lines.append("")
    lines.append("**Explanation**")
    attempt_alt = bool(previous)
    if entry:
        if style == "simplify":
            lines.append(entry["analogy"] if attempt_alt else entry["definition"])  # type: ignore[index]
        elif style == "example":
            lines.append(f"Example: {entry['example']}")
            if attempt_alt:
                lines.append(entry["analogy"])  # type: ignore[index]
        elif style == "analogy":
            lines.append(entry["analogy"])  # type: ignore[index]
            lines.append(f"In real terms: {entry['definition']}")
        elif style == "step_by_step":
            for i, step in enumerate(entry["steps"], 1):  # type: ignore[arg-type]
                lines.append(f"{i}. {step}")
        elif style == "detailed":
            lines.append(entry["definition"])  # type: ignore[index]
            lines.append(entry["detail"])  # type: ignore[index]
        if difficulty in ("advanced", "expert") and style != "detailed":
            lines.append(entry["detail"])  # type: ignore[index]
        if ctx and key:
            lines.append(f"How it relates here: the meeting discussed {key} in the context above — see the cited lines.")
    generated = model_explanation(text, style, difficulty, attempt_alt)
    if not entry and not generated:
        simple = simplify_text(text)
        if style == "step_by_step":
            for i, s in enumerate(split_sentences(simple) or [simple], 1):
                lines.append(f"{i}. {s}")
        else:
            lines.append(f"In simpler words: {simple}")
        lines.append("_The explanation model is not available, so this only simplifies wording "
                     "(install requirements-ml.txt and run python -m backend.hf.download gen)._")
    elif not entry:
        lines.append(generated)
    if entry and generated:
        lines.append("")
        lines.append(f"**Another explanation** _(generated by {hf.MODELS['gen'].split('/')[-1]} — general knowledge, verify)_")
        lines.append(generated)
    elif generated:
        lines.append(f"_Generated by {hf.MODELS['gen'].split('/')[-1]} from general knowledge, not from the meeting — verify._")
    out = "\n".join(lines)
    engine = "glossary" if entry else "rules"
    if generated:
        engine = f"{engine} + {hf.MODELS['gen']}" if entry else hf.MODELS["gen"]
    result = {"explanation": out, "meeting_context": ctx_out, "style": style, "difficulty": difficulty,
              "language": language, "engine": engine, "term": key}
    if language.split("-")[0] != "en":
        tr = translate(out, language, source="en")
        result["original"] = out
        result["explanation"] = tr["text"]
        result["translation"] = {k: tr[k] for k in ("translated", "engine", "warnings")}
    return result

"""Benchmark candidate explanation models for Explain Again (model selection, spec §6).

    python -m backend.evaluation.explain_benchmark [model ...]

Generates beginner explanations for meeting terms with each model using the same
prompts as the app, records latency, and writes research/explanation_benchmark.json
plus a markdown table for human rating (correct / partly / wrong).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ["MEETBRIEF_MODELS"] = "on"

from backend.hf import models as hf  # noqa: E402
from backend.nlp.simplification import model_explanation  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [("eventual consistency", "simplify"), ("load balancer", "step_by_step"), ("message queue", "example"),
         ("rollback plan", "simplify"), ("sharding", "simplify"), ("rate limiting", "analogy"),
         ("technical debt", "analogy"), ("p95 latency", "simplify"),
         ("The migration script needs a rollback plan.", "simplify")]
DEFAULT = ["google/flan-t5-large", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct"]


def run(models: list[str]) -> list[dict]:
    rows = []
    for mid in models:
        hf.MODELS["gen"] = mid
        hf._loaded.pop("gen", None)
        hf._errors.pop("gen", None)
        model_explanation("warm up", "simplify", "beginner", False)
        for text, style in ITEMS:
            t0 = time.perf_counter()
            out = model_explanation(text, style, "beginner", False)
            rows.append({"model": mid, "text": text, "style": style, "seconds": round(time.perf_counter() - t0, 1),
                         "output": out})
            print(f"[{mid}] {text} ({style}) {rows[-1]['seconds']}s\n  {out}\n", flush=True)
    return rows


if __name__ == "__main__":
    rows = run(sys.argv[1:] or DEFAULT)
    out = ROOT / "research" / "explanation_benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))

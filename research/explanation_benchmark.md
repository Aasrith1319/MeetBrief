# Explanation model benchmark (Explain Again)

Reproduce: `python -m backend.evaluation.explain_benchmark` (raw outputs in `explanation_benchmark.json`).

Setup: 9 items (8 technical terms + 1 meeting sentence), beginner level, the same concise prompts used in the app,
greedy decoding, Apple M2 (MPS) for generation. Ratings are a human judgement of factual correctness made while
building the project (correct = accurate and on-topic; partly = on-topic but with an error or rambling;
wrong = off-topic or false). Re-rate the JSON yourself for your report — the sample is small.

| Model | Params | Correct | Partly | Wrong | Typical latency |
|---|---|---|---|---|---|
| `google/flan-t5-large` | 780 M | 0 | 2 | 7 | 1–2 s |
| `Qwen/Qwen2.5-0.5B-Instruct` | 0.5 B | 2 | 4 | 3 | 2–6 s |
| **`Qwen/Qwen2.5-1.5B-Instruct`** (default) | 1.5 B | 8 | 1 | 0 | 5–15 s |

Per item (✓ correct, ~ partly, ✗ wrong):

| Item | Flan-T5-large | Qwen 0.5B | Qwen 1.5B |
|---|---|---|---|
| eventual consistency (simplify) | ✗ "a term used in software engineering" | ~ "always the same outcome" (wrong) | ✓ |
| load balancer (step by step) | ✗ "balances the load on a load cell" | ~ configuration steps, not how it works | ✓ |
| message queue (example) | ~ circular | ~ I/O example is muddled | ✓ chat-app example |
| rollback plan (simplify) | ✗ "reduce the number of bugs" | ✓ | ✓ |
| sharding (simplify) | ✗ "reduce the size of a file" | ✓ | ✓ |
| rate limiting (analogy) | ✗ liquid flow | ✗ reading articles | ~ traffic-light analogy, slightly confused |
| technical debt (analogy) | ✗ finance | ✗ student-credit analogy | ✓ house-building analogy |
| p95 latency (simplify) | ~ vague | ✗ "average time" | ✓ |
| "The migration script needs a rollback plan." | ✗ repeated verbatim | ~ | ✓ |

**Decision:** Qwen2.5-1.5B-Instruct is the default explanation model (runs on the GPU/MPS when available, CPU
otherwise ≈ 2× slower). Flan-T5-large hallucinates domain-specific meanings (e.g. "sharding" as file compression), so
it is kept only as a configurable fallback (`MEETBRIEF_GEN_MODEL=google/flan-t5-large`). Explanations are always shown
under "In this meeting" (retrieved transcript evidence) + "Explanation", and model output is labelled as general
knowledge to verify; the curated glossary is shown first when it covers the term.

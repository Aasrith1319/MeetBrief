# Evaluation

Run `python -m backend.evaluation.run_eval` — results go to `research/evaluation_results.{md,json}`.
Every text component is measured twice — **rules only** vs **with the Hugging Face models** — so the report doubles as
the model-selection benchmark the spec asks for. `--summary-models a,b,c` compares alternative summarizers.

| Component | Metric | Data |
|---|---|---|
| Decisions / proposals / revisions | precision, recall, F1; superseded accuracy | `datasets/evaluation_data/*annotations.json` |
| Action items | P/R/F1; owner and deadline accuracy on matched tasks | same |
| Unresolved questions | P/R/F1 | same |
| Q&A | answer accuracy on answerable questions; correct abstention on unanswerable ones | same |
| Summaries | ROUGE-1/2/L F1 vs. author-written references (`metrics.py`, no external deps) | same; QMSum via `--qmsum DIR` |
| Latency | analysis, summary, QA time | same |
| Hallucination control | share of abstractive sentences aligned to transcript evidence | same |
| Speech recognition | WER (`metrics.wer`) | `datasets/evaluation_data/audio/three_speakers.wav` (synthetic TTS, 3 voices) |
| Diarization | speaker accuracy after optimal label mapping; speakers found vs true | same |
| Translation | round-trip (en→hi/te→en) chrF + number preservation (proxy, no human references) | built-in sentences |

**Two sets.** `annotations.json` covers the sample transcripts that were used while developing the rules, so it is a
regression set. `heldout_annotations.json` covers a transcript written and annotated before the first evaluation run;
its numbers are the honest estimate (but it is one short synthetic meeting — do not generalise from it).

## Public datasets (not bundled)
* **QMSum** (query-based meeting summarization; includes AMI/ICSI meetings): download, verify the license, then
  `python -m backend.evaluation.run_eval --qmsum path/to/QMSum/data/ALL/test`.
* **AMI / ICSI** audio with speaker annotations: use for WER (ASR) and DER (diarization) on real meeting audio.
* Evaluate English, Telugu, Hindi and code-switched input separately; use human review for translation meaning,
  explanation clarity and factual consistency.

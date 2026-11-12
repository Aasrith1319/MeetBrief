"""Benchmark MeetBrief components: rule-based pipeline vs. Hugging Face models.

    python -m backend.evaluation.run_eval
    python -m backend.evaluation.run_eval --summary-models philschmid/bart-large-cnn-samsum,knkarthick/MEETING_SUMMARY
    python -m backend.evaluation.run_eval --qmsum PATH/QMSum/data/ALL/test

Writes research/evaluation_results.md and .json. Only measured numbers are
reported. Two transcript sets are used: the development samples (rules were
built against them) and a held-out transcript (annotated before first run).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

from backend.capture.transcript_normalizer import parse_transcript, to_segments
from backend.evaluation.metrics import chrf, prf, rouge_l, rouge_n, speaker_accuracy, wer
from backend.hf import models as hf
from backend.memory.meeting_state import build_memory
from backend.models import SegmentIn
from backend.nlp.summarization import abstractive_overview, key_sentences, summarize
from backend.rag.answer_generation import answer_question

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "datasets" / "sample_transcripts"
EVAL = ROOT / "datasets" / "evaluation_data"
SETS = {"development": EVAL / "annotations.json", "held-out": EVAL / "heldout_annotations.json"}


def set_models(on: bool) -> None:
    os.environ["MEETBRIEF_MODELS"] = "on" if on else "off"


def _kw_match(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return all(k.lower() in low for k in keywords)


def _match_items(pred: list, gold: list, text_of, gold_kw):
    used, pairs = set(), []
    for g in gold:
        for i, p in enumerate(pred):
            if i not in used and _kw_match(text_of(p), gold_kw(g)):
                used.add(i)
                pairs.append((p, g))
                break
    tp = len(pairs)
    return tp, len(pred) - tp, len(gold) - tp, pairs


def _add(acc: list, triple) -> list:
    return [a + b for a, b in zip(acc, triple)]


def _mean(xs: list) -> float | None:
    return round(statistics.mean(xs), 3) if xs else None


def evaluate_set(path: Path, use_models: bool) -> dict:
    set_models(use_models)
    data = json.loads(path.read_text())
    tot = {k: [0, 0, 0] for k in ("decisions", "proposals", "tasks", "questions")}
    owner_ok = deadline_ok = matched = sup_ok = sup_total = 0
    qa = {"answer_correct": 0, "answerable": 0, "abstain_correct": 0, "unanswerable": 0}
    rouge = {"summary_rouge1": [], "summary_rougeL": [], "overview_rouge1": [], "overview_rouge2": [], "overview_rougeL": []}
    lat = {"analyze_ms": [], "summary_ms": [], "qa_ms": []}
    support, qa_log = [], []
    for m in data["meetings"]:
        content = (SAMPLES / m["file"]).read_text()
        t0 = time.perf_counter()
        segs = to_segments("eval", parse_transcript(content, filename=m["file"]))
        mem = build_memory("eval", segs, {})
        lat["analyze_ms"].append((time.perf_counter() - t0) * 1000)

        conf = [d for d in mem.decisions if d.status in ("confirmed", "uncertain", "superseded")]
        tp, fp, fn, pairs = _match_items(conf, m["decisions"], lambda d: d.summary, lambda g: g["keywords"])
        tot["decisions"] = _add(tot["decisions"], (tp, fp, fn))
        for p, g in pairs:
            if g["status"] == "superseded":
                sup_total += 1
                sup_ok += p.status == "superseded"
        props = [d for d in mem.decisions if d.status == "proposed"]
        tot["proposals"] = _add(tot["proposals"], _match_items(props, m["proposals"], lambda d: d.summary, lambda g: g["keywords"])[:3])
        tp, fp, fn, pairs = _match_items(mem.action_items, m["tasks"], lambda t: t.task_text, lambda g: g["keywords"])
        tot["tasks"] = _add(tot["tasks"], (tp, fp, fn))
        for p, g in pairs:
            matched += 1
            owner_ok += p.owner.lower() == g["owner"].lower()
            deadline_ok += p.deadline.lower() == g["deadline"].lower()
        unresolved = [q for q in mem.open_questions if q.status == "unresolved"]
        tot["questions"] = _add(tot["questions"], _match_items(unresolved, m["unresolved_questions"], lambda q: q.text, lambda g: g)[:3])

        ref = m["reference_summary"]
        t0 = time.perf_counter()
        full = summarize(segs, mem, "catchup")["summary"]
        lat["summary_ms"].append((time.perf_counter() - t0) * 1000)
        rouge["summary_rouge1"].append(rouge_n(full, ref, 1)["f"])
        rouge["summary_rougeL"].append(rouge_l(full, ref)["f"])
        if use_models:
            ov = abstractive_overview(segs) or []
            overview = " ".join(p["raw"] for p in ov)
            for p in ov:
                support.extend(a["supported"] for a in p["aligned"])
        else:
            overview = " ".join(s for s, _ in key_sentences(segs, 4))
        if overview:
            rouge["overview_rouge1"].append(rouge_n(overview, ref, 1)["f"])
            rouge["overview_rouge2"].append(rouge_n(overview, ref, 2)["f"])
            rouge["overview_rougeL"].append(rouge_l(overview, ref)["f"])

        for item in m["qa"]:
            t0 = time.perf_counter()
            res = answer_question(item["q"], segs, mem, [])
            lat["qa_ms"].append((time.perf_counter() - t0) * 1000)
            ans = res["answer"].lower()
            if item["expect"] == "ABSTAIN":
                qa["unanswerable"] += 1
                ok = bool(res["insufficient_evidence"])
                qa["abstain_correct"] += ok
            else:
                qa["answerable"] += 1
                ok = any(e.lower() in ans for e in item["expect"])
                qa["answer_correct"] += ok
            qa_log.append({"meeting": m["file"].split("/")[-1], "question": item["q"], "expected": item["expect"],
                           "correct": bool(ok), "engine": res.get("engine"), "answer": res["answer"][:240]})
    return {
        "config": "hugging-face models" if use_models else "rules only",
        "decisions": prf(*tot["decisions"]), "revision_accuracy": f"{sup_ok}/{sup_total}",
        "proposals": prf(*tot["proposals"]), "tasks": prf(*tot["tasks"]),
        "owner_acc": round(owner_ok / matched, 3) if matched else None,
        "deadline_acc": round(deadline_ok / matched, 3) if matched else None,
        "unresolved_questions": prf(*tot["questions"]),
        "qa_answer_acc": f"{qa['answer_correct']}/{qa['answerable']}", "qa_abstain_acc": f"{qa['abstain_correct']}/{qa['unanswerable']}",
        "rouge": {k: _mean(v) for k, v in rouge.items()},
        "abstractive_sentences_supported": (f"{sum(support)}/{len(support)}" if support else None),
        "latency_ms": {k: round(statistics.mean(v), 1) for k, v in lat.items() if v},
        "qa_log": qa_log,
    }


def rule_act(sentence: str) -> str:
    """Dialogue act according to the rule-based extractors (for comparison with zero-shot NLI)."""
    from backend.models import Segment
    from backend.nlp.action_extraction import extract_action_items
    from backend.nlp.decision_extraction import classify_statement
    from backend.nlp.question_tracking import REQUEST

    kind = classify_statement(sentence)
    seg = Segment(text=sentence, segment_id="x", speaker_name="Speaker")
    if extract_action_items([seg], ["Speaker"]):
        return "task"
    if kind == "confirmed":
        return "decision"
    if kind == "proposed":
        return "proposal"
    if sentence.rstrip().endswith("?") and not REQUEST.match(sentence):
        return "question"
    return "other"


def evaluate_dialogue_acts() -> dict:
    from backend.nlp import dialogue_acts

    os.environ["MEETBRIEF_DIALOGUE_ACTS"] = "hybrid"
    items = json.loads((EVAL / "dialogue_acts.json").read_text())["items"]
    gold = [g for _, g in items]
    rules = [rule_act(s) for s, _ in items]
    out = {"n": len(items), "rules_accuracy": round(sum(p == g for p, g in zip(rules, gold)) / len(gold), 3)}
    set_models(True)
    pred = dialogue_acts.classify([s for s, _ in items])
    if pred:
        nli = [p["act"] for p in pred]
        out["nli_accuracy"] = round(sum(p == g for p, g in zip(nli, gold)) / len(gold), 3)
        per = {}
        for act in dialogue_acts.ACTS:
            idx = [i for i, g in enumerate(gold) if g == act]
            per[act] = {"rules": f"{sum(rules[i] == act for i in idx)}/{len(idx)}", "nli": f"{sum(nli[i] == act for i in idx)}/{len(idx)}"}
        out["per_act_recall"] = per
    return out


def evaluate_speech() -> dict | None:
    """ASR word error rate and diarization speaker accuracy on the synthetic 3-voice meeting."""
    from backend.speech.diarization import diarization_available, diarize
    from backend.speech.speech_recognition import asr_available, transcribe_bytes

    set_models(True)
    wav = EVAL / "audio" / "three_speakers.wav"
    gt = json.loads((EVAL / "audio" / "three_speakers.json").read_text())["turns"]
    if not asr_available()["available"] or not wav.exists():
        return None
    t0 = time.perf_counter()
    asr = transcribe_bytes(wav.read_bytes(), suffix=".wav", language="en")
    asr_s = time.perf_counter() - t0
    hyp = " ".join(s["text"] for s in asr["segments"])
    out = {"audio_seconds": round(asr["duration"], 1), "asr_seconds": round(asr_s, 1), "whisper_model": asr_available()["model"],
           "wer": round(wer(hyp, " ".join(t["text"] for t in gt)), 3), "asr_segments": len(asr["segments"])}
    if diarization_available()["available"]:
        t0 = time.perf_counter()
        labels, cents = diarize(asr["audio"], asr["segments"], [])
        out["diarization_seconds"] = round(time.perf_counter() - t0, 1)

        def gold_for(seg):
            best = max(gt, key=lambda t: max(0.0, min(seg["end"], t["end"]) - max(seg["start"], t["start"])))
            return best["speaker"]
        gold = [gold_for(s) for s in asr["segments"]]
        out.update({"speakers_true": len({t["speaker"] for t in gt}), "speakers_found": len(cents),
                    "speaker_accuracy": round(speaker_accuracy(labels, gold), 3),
                    "assignments": [[g, p] for g, p in zip(gold, labels)]})
    return out


def evaluate_translation() -> dict | None:
    """Proxy: round-trip (en -> X -> en) chrF and number preservation; no human references are used."""
    from backend.nlp.translation import preservation_check, translate

    set_models(True)
    if not hf.enabled("mt"):
        return None
    sents = ["Priya will complete the indexing changes by Friday.",
             "Let's postpone the 2.4 release to next Tuesday so David can fix the Android crash.",
             "The crash rate on Android is still at 3 percent after the last build.",
             "Karthik, please implement the lazy loading by Wednesday.",
             "We decided to use Postgres full-text search instead because it avoids a new service.",
             "Downtime should be around 20 minutes if we run the migration at night."]
    out = {}
    for lang in ("hi", "te"):
        scores, kept, t0 = [], 0, time.perf_counter()
        samples = []
        for s in sents:
            fwd = translate(s, lang, source="en")["text"]
            back = translate(fwd, "en", source=lang)["text"]
            scores.append(chrf(back, s))
            kept += not preservation_check(s, fwd)
            samples.append({"en": s, lang: fwd, "back": back})
        out[lang] = {"round_trip_chrF": round(statistics.mean(scores), 3), "numbers_preserved": f"{kept}/{len(sents)}",
                     "seconds_per_sentence": round((time.perf_counter() - t0) / (2 * len(sents)), 2), "samples": samples[:3]}
    return out


def benchmark_summarizers(model_ids: list[str]) -> list[dict]:
    """Compare abstractive summarizers on the reference summaries (overview ROUGE, support rate, latency)."""
    set_models(True)
    rows = []
    original = hf.MODELS["summary"]
    for mid in model_ids:
        hf.MODELS["summary"] = mid
        hf._loaded.pop("summary", None)
        hf._errors.pop("summary", None)
        from backend.nlp import summarization
        summarization._overview_cache.clear()  # time real generation, not cache hits
        hf.summarize_dialogue("A: hello\nB: hi, shall we start?")  # load the model before timing
        r1, rl, sup, times = [], [], [], []
        for path in SETS.values():
            for m in json.loads(path.read_text())["meetings"]:
                segs = to_segments("b", parse_transcript((SAMPLES / m["file"]).read_text(), filename=m["file"]))
                t0 = time.perf_counter()
                ov = abstractive_overview(segs)
                times.append(time.perf_counter() - t0)
                if not ov:
                    continue
                text = " ".join(p["raw"] for p in ov)
                r1.append(rouge_n(text, m["reference_summary"], 1)["f"])
                rl.append(rouge_l(text, m["reference_summary"])["f"])
                sup.extend(a["supported"] for p in ov for a in p["aligned"])
        rows.append({"model": mid, "rouge1": _mean(r1), "rougeL": _mean(rl),
                     "supported": f"{sum(sup)}/{len(sup)}" if sup else None, "seconds": _mean(times),
                     "error": hf._errors.get("summary")})
    hf.MODELS["summary"] = original
    hf._loaded.pop("summary", None)
    return rows


def evaluate_qmsum(path: Path, limit: int = 20) -> dict:
    set_models(True)
    files = sorted(path.glob("*.json"))[:limit]
    scores = {"rouge1": [], "rouge2": [], "rougeL": []}
    for f in files:
        d = json.loads(f.read_text())
        items = [SegmentIn(text=t["content"], speaker_name=t.get("speaker"), source_type="transcript")
                 for t in d.get("meeting_transcripts", []) if t.get("content", "").strip()]
        segs = to_segments("qmsum", items)
        refs = [q["answer"] for q in d.get("general_query_list", []) if "summar" in q.get("query", "").lower()]
        ov = abstractive_overview(segs)
        if not refs or not ov:
            continue
        text = " ".join(p["raw"] for p in ov)
        scores["rouge1"].append(rouge_n(text, refs[0], 1)["f"])
        scores["rouge2"].append(rouge_n(text, refs[0], 2)["f"])
        scores["rougeL"].append(rouge_l(text, refs[0])["f"])
    return {"meetings": len(scores["rouge1"]), **{k: _mean(v) for k, v in scores.items()}}


# ------------------------------------------------------------------ report
def _prf(d: dict) -> str:
    return f"{d['precision']} / {d['recall']} / {d['f1']}"


def comparison_table(rules: dict, models: dict) -> list[str]:
    rows = [
        ("Decisions P / R / F1", _prf(rules["decisions"]), _prf(models["decisions"])),
        ("Decision revisions detected", rules["revision_accuracy"], models["revision_accuracy"]),
        ("Proposals P / R / F1", _prf(rules["proposals"]), _prf(models["proposals"])),
        ("Action items P / R / F1", _prf(rules["tasks"]), _prf(models["tasks"])),
        ("Task owner accuracy", rules["owner_acc"], models["owner_acc"]),
        ("Task deadline accuracy", rules["deadline_acc"], models["deadline_acc"]),
        ("Unresolved questions P / R / F1", _prf(rules["unresolved_questions"]), _prf(models["unresolved_questions"])),
        ("Q&A answerable correct", rules["qa_answer_acc"], models["qa_answer_acc"]),
        ("Q&A unanswerable → abstained", rules["qa_abstain_acc"], models["qa_abstain_acc"]),
        ("Overview ROUGE-1 / 2 / L", f"{rules['rouge']['overview_rouge1']} / {rules['rouge']['overview_rouge2']} / {rules['rouge']['overview_rougeL']} (TextRank)",
         f"{models['rouge']['overview_rouge1']} / {models['rouge']['overview_rouge2']} / {models['rouge']['overview_rougeL']} (abstractive)"),
        ("Full catch-up ROUGE-1 / L", f"{rules['rouge']['summary_rouge1']} / {rules['rouge']['summary_rougeL']}",
         f"{models['rouge']['summary_rouge1']} / {models['rouge']['summary_rougeL']}"),
        ("Abstractive sentences evidence-supported", "–", models["abstractive_sentences_supported"] or "–"),
        ("Latency analyze / summary / QA (ms)",
         " / ".join(str(rules["latency_ms"].get(k)) for k in ("analyze_ms", "summary_ms", "qa_ms")),
         " / ".join(str(models["latency_ms"].get(k)) for k in ("analyze_ms", "summary_ms", "qa_ms"))),
    ]
    out = ["| Metric | Rules only | With Hugging Face models |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    return out


def to_markdown(res: dict) -> str:
    L = ["# MeetBrief AI — measured evaluation results", "",
         "All numbers below were produced by `python -m backend.evaluation.run_eval` on this machine "
         f"(device: {res['device']}). Datasets are small and synthetic, so treat them as a sanity check and a "
         "rules-vs-models comparison, not as general accuracy claims.", ""]
    for name in SETS:
        r = res["sets"][name]
        L += [f"## {name.capitalize()} set", "",
              ("Rules were developed against this set, so its rule-based scores are optimistic." if name == "development"
               else "Annotated before the first evaluation run. Disclosure: two changes were made after looking at "
                    "failures on this set — (1) a Q&A bug where a reply marked *possibly answers* was reported as "
                    "\"no answer\" (fixed; held-out Q&A went 3/4 → 4/4), and (2) removing NLI-added decisions, which "
                    "lowered decision precision here (0.67 → 0.50). A third change — merging vague confirmations such as "
                    "\"I can do that\" into the task they refer to, found on the audio test transcript — also removed one "
                    "false-positive task here (action-item F1 0.86 → 1.0). Treat this set as only partly unbiased."), ""]
        L += comparison_table(r["rules"], r["models"])
        h = r.get("hybrid_nli")
        if h:
            L += ["", f"With the optional NLI second opinion (`MEETBRIEF_DIALOGUE_ACTS=hybrid`): decisions "
                  f"{_prf(h['decisions'])}, analyze latency {h['latency_ms'].get('analyze_ms')} ms."]
        L += ["", "<details><summary>Q&A log (models)</summary>", "", "| Question | Expected | Correct | Engine |", "|---|---|---|---|"]
        L += [f"| {q['question']} | {q['expected']} | {'✅' if q['correct'] else '❌'} | {q['engine']} |" for q in r["models"]["qa_log"]]
        L += ["", "</details>", ""]
    if res.get("dialogue_acts"):
        d = res["dialogue_acts"]
        L += ["## Dialogue-act classification (decision / proposal / task / question / other)", "",
              f"{d['n']} hand-labelled sentences. Rules accuracy **{d['rules_accuracy']}**; zero-shot NLI "
              f"(`{hf.MODELS['nli']}`) accuracy **{d.get('nli_accuracy')}**.", ""]
        if d.get("per_act_recall"):
            L += ["| Act | Rules recall | NLI recall |", "|---|---|---|"]
            L += [f"| {a} | {v['rules']} | {v['nli']} |" for a, v in d["per_act_recall"].items()]
        L += ["", "Zero-shot NLI cannot reliably tell *deciding* from *suggesting*, so it is used only to raise the confidence "
              "of rule-extracted items, not to replace the rules.", ""]
    if res.get("summarizers"):
        L += ["## Summarization model benchmark", "", "| Model | Overview ROUGE-1 | ROUGE-L | Sentences supported | Seconds/meeting |", "|---|---|---|---|---|"]
        L += [f"| `{r['model']}` | {r['rouge1']} | {r['rougeL']} | {r['supported']} | {r['seconds']} |" for r in res["summarizers"]]
        L.append("")
    if res.get("speech"):
        s = res["speech"]
        L += ["## Speech (synthetic 3-voice meeting, macOS TTS)", "",
              f"* ASR (faster-whisper `{s['whisper_model']}`): **WER {s['wer']}** on {s['audio_seconds']} s of audio "
              f"({s['asr_seconds']} s to transcribe)."]
        if "speaker_accuracy" in s:
            L.append(f"* Diarization (WavLM x-vectors + online clustering): **speaker accuracy {s['speaker_accuracy']}**, "
                     f"{s['speakers_found']} speakers found vs {s['speakers_true']} true ({s['diarization_seconds']} s).")
        L += ["* TTS voices are far cleaner than real meetings; expect higher WER/DER on real audio.", ""]
    if res.get("translation"):
        L += ["## Translation (NLLB-200, proxy metrics)", "", "| Language | Round-trip chrF | Numbers preserved | s/sentence |", "|---|---|---|---|"]
        for lang, t in res["translation"].items():
            L.append(f"| {lang} | {t['round_trip_chrF']} | {t['numbers_preserved']} | {t['seconds_per_sentence']} |")
        L += ["", "Round-trip chrF only checks that meaning survives en→X→en; it is not a substitute for human review "
              "of Hindi/Telugu fluency.", ""]
    if res.get("qmsum"):
        L += ["## QMSum", "", json.dumps(res["qmsum"]), ""]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary-models", default="", help="comma-separated summarizer ids to benchmark")
    ap.add_argument("--qmsum", type=Path)
    ap.add_argument("--skip-speech", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "research")
    args = ap.parse_args()
    res = {"sets": {}, "device": hf.device() if hf._transformers_ok() else "cpu"}
    for name, path in SETS.items():
        res["sets"][name] = {"rules": evaluate_set(path, False), "models": evaluate_set(path, True)}
    os.environ["MEETBRIEF_DIALOGUE_ACTS"] = "hybrid"
    for name, path in SETS.items():
        res["sets"][name]["hybrid_nli"] = evaluate_set(path, True)
    os.environ.pop("MEETBRIEF_DIALOGUE_ACTS", None)
    res["dialogue_acts"] = evaluate_dialogue_acts()
    if args.summary_models:
        res["summarizers"] = benchmark_summarizers([m.strip() for m in args.summary_models.split(",") if m.strip()])
    if not args.skip_speech:
        res["speech"] = evaluate_speech()
    res["translation"] = evaluate_translation()
    if args.qmsum:
        res["qmsum"] = evaluate_qmsum(args.qmsum)
    res["models"] = hf.status()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "evaluation_results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    md = to_markdown(res)
    (args.out / "evaluation_results.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()

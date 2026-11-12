"""Local Hugging Face models used by MeetBrief AI (no external API calls).

Each task has one configurable model (override with the environment variable in
brackets). Models are lazy-loaded on first use and cached in ~/.cache/huggingface;
prefetch them all for offline demos with ``python -m backend.hf.download``.

| Task                          | Default model                                            | Env var                     |
|-------------------------------|----------------------------------------------------------|-----------------------------|
| Abstractive dialogue summary  | philschmid/bart-large-cnn-samsum                         | MEETBRIEF_SUMMARY_MODEL      |
| Machine translation           | facebook/nllb-200-distilled-600M                         | MEETBRIEF_MT_MODEL           |
| Explanations / simplification | Qwen/Qwen2.5-1.5B-Instruct (chosen over flan-t5-large, see research/explanation_benchmark.md) | MEETBRIEF_GEN_MODEL |
| Extractive QA (with no-answer)| deepset/roberta-base-squad2                              | MEETBRIEF_QA_MODEL           |
| Sentence embeddings           | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | MEETBRIEF_EMBEDDING_MODEL |
| Zero-shot dialogue acts (NLI) | MoritzLaurer/mDeBERTa-v3-base-mnli-xnli                  | MEETBRIEF_NLI_MODEL          |
| Named entity recognition      | dslim/bert-base-NER                                      | MEETBRIEF_NER_MODEL          |
| Speaker embeddings (diarization) | microsoft/wavlm-base-plus-sv                          | MEETBRIEF_SPEAKER_MODEL      |

Set ``MEETBRIEF_MODELS=off`` to run only the rule-based / statistical pipeline
(used by the fast unit tests), or disable single tasks, e.g.
``MEETBRIEF_DISABLE=nli,ner``.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from functools import lru_cache
from typing import Any, Optional

log = logging.getLogger("meetbrief.hf")

MODELS = {
    "summary": os.environ.get("MEETBRIEF_SUMMARY_MODEL", "philschmid/bart-large-cnn-samsum"),
    "mt": os.environ.get("MEETBRIEF_MT_MODEL", "facebook/nllb-200-distilled-600M"),
    "gen": os.environ.get("MEETBRIEF_GEN_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"),
    "qa": os.environ.get("MEETBRIEF_QA_MODEL", "deepset/roberta-base-squad2"),
    "embedding": os.environ.get("MEETBRIEF_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
    "nli": os.environ.get("MEETBRIEF_NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"),
    "ner": os.environ.get("MEETBRIEF_NER_MODEL", "dslim/bert-base-NER"),
    "speaker": os.environ.get("MEETBRIEF_SPEAKER_MODEL", "microsoft/wavlm-base-plus-sv"),
}
TASK_LABELS = {
    "summary": "Abstractive dialogue summarization", "mt": "Machine translation", "gen": "Explanation generation",
    "qa": "Extractive question answering", "embedding": "Sentence embeddings", "nli": "Zero-shot dialogue acts",
    "ner": "Named entity recognition", "speaker": "Speaker embeddings",
}

NLLB_CODES = {"en": "eng_Latn", "hi": "hin_Deva", "te": "tel_Telu", "ta": "tam_Taml", "kn": "kan_Knda",
              "ml": "mal_Mlym", "bn": "ben_Beng", "mr": "mar_Deva", "gu": "guj_Gujr", "pa": "pan_Guru",
              "es": "spa_Latn", "fr": "fra_Latn", "de": "deu_Latn", "it": "ita_Latn", "pt": "por_Latn",
              "zh": "zho_Hans", "ja": "jpn_Jpan", "ko": "kor_Hang", "ar": "arb_Arab", "ru": "rus_Cyrl", "nl": "nld_Latn"}

_lock = threading.RLock()
_errors: dict[str, str] = {}


def _disabled() -> set[str]:
    return {t.strip() for t in os.environ.get("MEETBRIEF_DISABLE", "").split(",") if t.strip()}


def models_enabled() -> bool:
    return os.environ.get("MEETBRIEF_MODELS", "on").lower() not in {"off", "0", "false", "no"}


@lru_cache(maxsize=1)
def _transformers_ok() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def device(task: Optional[str] = None) -> str:
    """CPU by default (deterministic, works everywhere). The explanation LLM defaults to the GPU
    (Apple MPS / CUDA) when present because autoregressive generation is the slowest step.
    Override globally with MEETBRIEF_DEVICE or per task, e.g. MEETBRIEF_GEN_DEVICE=cpu."""
    default = "auto" if task in ("gen", "mt") else "cpu"
    pref = os.environ.get(f"MEETBRIEF_{(task or '').upper()}_DEVICE") or os.environ.get("MEETBRIEF_DEVICE", default)
    if pref == "auto":
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return pref


def is_cached(model_id: str) -> bool:
    try:
        from huggingface_hub import scan_cache_dir

        return any(r.repo_id == model_id for r in scan_cache_dir().repos)
    except Exception:
        return False


def enabled(task: str) -> bool:
    """True if the task's model may be used (installed, not disabled, not previously failed)."""
    return models_enabled() and _transformers_ok() and task not in _disabled() and task not in _errors


def status() -> dict[str, Any]:
    out = {"enabled": models_enabled() and _transformers_ok(), "device": device() if _transformers_ok() else None,
           "reason": None if _transformers_ok() else "transformers/torch not installed (pip install -r requirements-ml.txt)",
           "tasks": {}}
    if not models_enabled():
        out["reason"] = "Models disabled (MEETBRIEF_MODELS=off) — rule-based pipeline only"
    for task, mid in MODELS.items():
        out["tasks"][task] = {"model": mid, "label": TASK_LABELS[task], "enabled": enabled(task),
                              "device": device(task) if _transformers_ok() else None,
                              "downloaded": is_cached(mid), "loaded": task in _loaded, "error": _errors.get(task)}
    return out


_loaded: dict[str, Any] = {}


def _load(task: str):
    if task in _loaded:
        return _loaded[task]
    with _lock:
        if task in _loaded:
            return _loaded[task]
        mid = MODELS[task]
        log.info("Loading %s model %s on %s", task, mid, device(task))
        try:
            obj = _build(task, mid)
        except Exception as exc:  # pragma: no cover - depends on network / disk
            _errors[task] = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("Could not load %s (%s); falling back to rule-based pipeline", mid, exc)
            raise
        _loaded[task] = obj
        return obj


def _quiet() -> None:
    try:
        import transformers

        transformers.logging.set_verbosity_error()
        transformers.utils.logging.disable_progress_bar()
    except Exception:
        pass


def _build(task: str, mid: str):
    import torch

    _quiet()
    from transformers import (AutoModelForQuestionAnswering, AutoModelForSeq2SeqLM, AutoModelForSequenceClassification,
                              AutoModelForTokenClassification, AutoTokenizer)

    dev = device(task)
    if task == "embedding":
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(mid, device=dev)
    if task == "speaker":
        from transformers import AutoFeatureExtractor, WavLMForXVector

        return AutoFeatureExtractor.from_pretrained(mid), WavLMForXVector.from_pretrained(mid).eval()
    tok = AutoTokenizer.from_pretrained(mid)
    if task == "gen":
        from transformers import AutoConfig, AutoModelForCausalLM

        if not AutoConfig.from_pretrained(mid).is_encoder_decoder:  # decoder-only chat model (e.g. Qwen2.5-Instruct)
            model = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32).to(dev).eval()
            torch.set_grad_enabled(False)
            return tok, model
    if task in ("summary", "mt", "gen"):
        model = AutoModelForSeq2SeqLM.from_pretrained(mid).to(dev).eval()
    elif task == "qa":
        model = AutoModelForQuestionAnswering.from_pretrained(mid).to(dev).eval()
    elif task == "nli":
        model = AutoModelForSequenceClassification.from_pretrained(mid).to(dev).eval()
    elif task == "ner":
        model = AutoModelForTokenClassification.from_pretrained(mid).to(dev).eval()
    else:
        raise KeyError(task)
    torch.set_grad_enabled(False)
    return tok, model


# A shared server may serve several rooms at once: heavy generation jobs queue here instead of all running
# together and exhausting RAM/GPU memory. Light tasks (embeddings, NER, QA) are not limited.
HEAVY = {"summary", "mt", "gen", "speaker", "nli"}
_heavy_slots = threading.BoundedSemaphore(max(1, int(os.environ.get("MEETBRIEF_MAX_MODEL_JOBS", "2"))))


def try_task(task: str, fn, *args, **kwargs) -> Optional[Any]:
    """Run ``fn`` with the loaded model; return None (and fall back) if the model is unavailable."""
    if not enabled(task):
        return None
    try:
        bundle = _load(task)
        if task in HEAVY:
            with _heavy_slots:
                return fn(bundle, *args, **kwargs)
        return fn(bundle, *args, **kwargs)
    except Exception as exc:
        if task not in _errors:
            log.warning("%s model failed: %s", task, exc)
        return None


# ------------------------------------------------------------------ tasks
def _seq2seq(bundle, text: str, max_new_tokens: int, min_new_tokens: int = 0, num_beams: int = 4,
             max_input: int = 1024, **gen_kwargs) -> str:
    import torch

    tok, model = bundle
    enc = tok(text, return_tensors="pt", truncation=True, max_length=max_input).to(model.device)
    if num_beams > 1:
        gen_kwargs.setdefault("early_stopping", True)
    with torch.inference_mode():
        out = model.generate(**enc, max_new_tokens=max_new_tokens, min_new_tokens=min_new_tokens, num_beams=num_beams,
                             no_repeat_ngram_size=3, **gen_kwargs)
    return tok.decode(out[0], skip_special_tokens=True).strip()


def token_count(task: str, text: str) -> int:
    bundle = _loaded.get(task)
    if bundle and isinstance(bundle, tuple):
        return len(bundle[0](text, add_special_tokens=False)["input_ids"])
    return int(len(text.split()) * 1.4)


def summarize_dialogue(dialogue: str, max_new_tokens: int = 160, min_new_tokens: int = 20) -> Optional[str]:
    """Abstractive summary of 'Speaker: text' lines (SAMSum format)."""
    return try_task("summary", _seq2seq, dialogue, max_new_tokens, min_new_tokens)


def _chat(bundle, prompt: str, max_new_tokens: int, sample: bool) -> str:
    import torch

    tok, model = bundle
    messages = [{"role": "system", "content": "You are a helpful teaching assistant. Explain clearly and correctly. "
                 "If you are not sure what a term means, say so instead of guessing."},
                {"role": "user", "content": prompt}]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    enc = tok(text, return_tensors="pt").to(model.device)
    kw = dict(do_sample=True, temperature=0.8, top_p=0.9) if sample else dict(do_sample=False)
    with torch.inference_mode():
        out = model.generate(**enc, max_new_tokens=max_new_tokens, repetition_penalty=1.1, **kw)
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def generate(prompt: str, max_new_tokens: int = 160, num_beams: int = 4, sample: bool = False,
             min_new_tokens: int = 0) -> Optional[str]:
    """Instruction-following generation (Flan-T5 or a small chat model). ``sample=True`` gives a different attempt."""
    if enabled("gen"):
        try:
            bundle = _load("gen")
        except Exception:
            return None
        if not getattr(bundle[1].config, "is_encoder_decoder", True):
            return try_task("gen", _chat, prompt, max_new_tokens, sample)
    if sample:
        return try_task("gen", _seq2seq, prompt, max_new_tokens, min_new_tokens, 1, 512, do_sample=True, top_p=0.9,
                        temperature=0.9, repetition_penalty=1.3)
    return try_task("gen", _seq2seq, prompt, max_new_tokens, min_new_tokens, num_beams, 512, repetition_penalty=1.3)


def _translate(bundle, sentences: list[str], src: str, tgt: str) -> list[str]:
    import torch

    tok, model = bundle
    tok.src_lang = src
    out = []
    # beam 4: beam 2 was ~35% faster but dropped Telugu round-trip chrF from 0.83 to 0.73 in run_eval
    for i in range(0, len(sentences), 16):
        batch = sentences[i:i + 16]
        enc = tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=256).to(model.device)
        with torch.inference_mode():
            gen = model.generate(**enc, forced_bos_token_id=tok.convert_tokens_to_ids(tgt), max_new_tokens=300,
                                 num_beams=4)
        out.extend(tok.batch_decode(gen, skip_special_tokens=True))
    return out


_mt_cache: dict[tuple, str] = {}


def translate_sentences(sentences: list[str], src: str, tgt: str) -> Optional[list[str]]:
    s, t = NLLB_CODES.get(src.split("-")[0]), NLLB_CODES.get(tgt.split("-")[0])
    if not s or not t or not sentences:
        return None
    todo = [x for x in dict.fromkeys(sentences) if (x, s, t) not in _mt_cache]
    if todo:
        out = try_task("mt", _translate, todo, s, t)
        if out is None:
            return None
        if len(_mt_cache) > 20_000:
            _mt_cache.clear()
        for x, y in zip(todo, out):
            _mt_cache[(x, s, t)] = y
    return [_mt_cache[(x, s, t)] for x in sentences]


def _qa(bundle, question: str, contexts: list[str]) -> list[dict]:
    """SQuAD2-style extractive QA. Returns, per context, the best span and the no-answer score."""
    import torch

    tok, model = bundle
    results = []
    for ctx in contexts:
        enc = tok(question, ctx, return_tensors="pt", truncation="only_second", max_length=384,
                  return_offsets_mapping=True)
        offsets = enc.pop("offset_mapping")[0].tolist()
        seq_ids = enc.sequence_ids(0)
        with torch.inference_mode():
            out = model(**{k: v.to(model.device) for k, v in enc.items()})
        start = out.start_logits[0].cpu()
        end = out.end_logits[0].cpu()
        null_score = float(start[0] + end[0])
        ctx_idx = [i for i, sid in enumerate(seq_ids) if sid == 1]
        best = (-1e9, None, None)
        top_s = sorted(ctx_idx, key=lambda i: -float(start[i]))[:20]
        top_e = sorted(ctx_idx, key=lambda i: -float(end[i]))[:20]
        for si in top_s:
            for ei in top_e:
                if ei < si or ei - si > 30:
                    continue
                sc = float(start[si] + end[ei])
                if sc > best[0]:
                    best = (sc, si, ei)
        if best[1] is None:
            results.append({"answer": "", "score": 0.0, "null_margin": -99.0})
            continue
        a0, a1 = offsets[best[1]][0], offsets[best[2]][1]
        probs_s = torch.softmax(start[ctx_idx], 0)
        probs_e = torch.softmax(end[ctx_idx], 0)
        conf = float(probs_s[ctx_idx.index(best[1])] * probs_e[ctx_idx.index(best[2])])
        results.append({"answer": ctx[a0:a1].strip(), "score": conf, "null_margin": best[0] - null_score})
    return results


def extractive_qa(question: str, contexts: list[str]) -> Optional[list[dict]]:
    return try_task("qa", _qa, question, contexts)


def embed(texts: list[str]):
    """Normalised sentence embeddings (numpy array) or None."""
    def run(model, texts):
        return model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return try_task("embedding", run, texts)


_nli_cache: dict[tuple, dict] = {}


def _zero_shot(bundle, texts: list[str], labels: list[str], template: str) -> list[dict]:
    import torch

    tok, model = bundle
    ent_idx = next(i for i, l in model.config.id2label.items() if l.lower().startswith("entail"))
    con_idx = next(i for i, l in model.config.id2label.items() if l.lower().startswith("contra"))
    out = []
    for text in texts:
        key = (text, tuple(labels), template)
        if key in _nli_cache:
            out.append(_nli_cache[key])
            continue
        pairs = [(text, template.format(l)) for l in labels]
        enc = tok([p[0] for p in pairs], [p[1] for p in pairs], return_tensors="pt", padding=True, truncation=True,
                  max_length=256).to(model.device)
        with torch.inference_mode():
            logits = model(**enc).logits.cpu()
        # standard zero-shot: softmax over the entailment logits of each hypothesis
        scores = torch.softmax(logits[:, ent_idx], 0).tolist()
        # independent entailment vs contradiction probability, for thresholding
        indep = torch.softmax(logits[:, [con_idx, ent_idx]], 1)[:, 1].tolist()
        res = {"labels": labels, "scores": scores, "entailment": indep}
        _nli_cache[key] = res
        out.append(res)
    return out


def zero_shot(texts: list[str], labels: list[str], template: str = "This text {}.") -> Optional[list[dict]]:
    return try_task("nli", _zero_shot, texts, labels, template)


_ner_cache: dict[str, list] = {}


def _ner(bundle, text: str) -> list[dict]:
    """Token classification aggregated to whole words (first sub-token decides the word's label)."""
    import torch

    if text in _ner_cache:
        return _ner_cache[text]
    tok, model = bundle
    enc = tok(text, return_tensors="pt", truncation=True, max_length=256, return_offsets_mapping=True)
    offsets = enc.pop("offset_mapping")[0].tolist()
    word_ids = enc.word_ids(0)
    with torch.inference_mode():
        logits = model(**{k: v.to(model.device) for k, v in enc.items()}).logits[0].cpu()
    probs = torch.softmax(logits, -1)
    words: dict[int, dict] = {}
    for ti, wid in enumerate(word_ids):
        if wid is None:
            continue
        a, b = offsets[ti]
        if wid not in words:
            p, idx = probs[ti].max(-1)
            words[wid] = {"start": a, "end": b, "label": model.config.id2label[int(idx)], "score": float(p)}
        else:
            words[wid]["end"] = b
    ents: list[dict] = []
    prev = None
    for wid in sorted(words):
        w = words[wid]
        lab = w["label"]
        if lab == "O":
            prev = None
            continue
        kind = lab.split("-")[-1]
        if prev and prev["type"] == kind and lab.startswith("I-"):
            prev["end"], prev["score"] = w["end"], min(prev["score"], w["score"])
        else:
            prev = {"type": kind, "start": w["start"], "end": w["end"], "score": w["score"]}
            ents.append(prev)
    for e in ents:
        e["text"] = text[e["start"]:e["end"]].strip(" ,.;:!?\"'“”")
    ents = [e for e in ents if e["score"] > 0.6 and len(e["text"]) > 1]
    _ner_cache[text] = ents
    return ents


def ner(text: str) -> Optional[list[dict]]:
    return try_task("ner", _ner, text)


def _speaker_embed(bundle, waves: list) -> Any:
    import numpy as np
    import torch

    fe, model = bundle
    out = []
    for w in waves:
        inputs = fe(w, sampling_rate=16000, return_tensors="pt", padding=True)
        with torch.inference_mode():
            emb = model(**inputs).embeddings[0]
        emb = torch.nn.functional.normalize(emb, dim=-1)
        out.append(emb.numpy())
    return np.stack(out) if out else np.zeros((0, 512))


def speaker_embeddings(waves: list):
    return try_task("speaker", _speaker_embed, waves)

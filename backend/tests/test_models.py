"""Integration tests with the real local Hugging Face models.

Each test is skipped when its model has not been downloaded
(python -m backend.hf.download). They are slower than the unit tests.
"""
import json
import os
from pathlib import Path

import pytest

from backend.hf import models as hf

from .conftest import load

EVAL = Path(__file__).resolve().parents[2] / "datasets" / "evaluation_data"


@pytest.fixture(autouse=True)
def models_on():
    old = os.environ.get("MEETBRIEF_MODELS")
    os.environ["MEETBRIEF_MODELS"] = "on"
    yield
    os.environ["MEETBRIEF_MODELS"] = old or "off"


def need(task: str):
    if not hf._transformers_ok() or not hf.is_cached(hf.MODELS[task]):
        pytest.skip(f"{hf.MODELS[task]} not downloaded")


def test_abstractive_summary_is_evidence_aligned():
    need("summary")
    from backend.nlp.summarization import abstractive_overview

    segs, _ = load("demo_indexing.txt")
    ov = abstractive_overview(segs)
    assert ov and ov[0]["raw"]
    assert any(a["supported"] for a in ov[0]["aligned"])
    assert "[S" in ov[0]["text"]


def test_catchup_uses_model_and_keeps_structure():
    need("summary")
    from backend.nlp.summarization import summarize

    segs, mem = load("sprint_planning.txt")
    out = summarize(segs, mem, "catchup")
    assert "Overview" in out["summary"] and "Decisions" in out["summary"]
    assert hf.MODELS["summary"] in out["engine"]


def test_translation_telugu_and_hindi():
    need("mt")
    from backend.nlp.translation import translate

    te = translate("Priya will finish the indexing changes by Friday, 12 May.", "te", source="en")
    assert te["translated"] and any("ఀ" <= c <= "౿" for c in te["text"])
    hi = translate("- Decision: postpone release 2.4 [S13-56993d]", "hi", source="en")
    assert any("ऀ" <= c <= "ॿ" for c in hi["text"])
    assert hi["text"].startswith("- ") and "[S13-56993d]" in hi["text"]  # markdown + citations preserved


def test_extractive_qa_answers_and_abstains():
    need("qa")
    from backend.rag.answer_generation import answer_question

    segs, mem = load("sprint_planning.txt")
    r = answer_question("What is the Android crash rate?", segs, mem, [])
    assert "3 percent" in r["answer"]
    r = answer_question("What color will the new checkout button be?", segs, mem, [])
    assert r["insufficient_evidence"]


def test_zero_shot_dialogue_acts(monkeypatch):
    need("nli")
    from backend.nlp import dialogue_acts

    monkeypatch.setenv("MEETBRIEF_DIALOGUE_ACTS", "hybrid")  # opt-in feature

    out = dialogue_acts.classify(["Let's go with Postgres for the search index.", "How long will the downtime be?"])
    assert out[0]["act"] in ("decision", "proposal")
    assert out[1]["act"] == "question"


def test_ner_entities():
    need("ner")
    _, mem = load("sprint_planning.txt")
    persons = {e for e, t in mem.entity_types.items() if t == "PER"}
    assert persons & set(mem.participants)
    assert "PostgreSQL" in mem.entity_types  # sub-words merged into one entity


def test_dense_retrieval_paraphrase():
    need("embedding")
    from backend.rag.retrieval import MeetingRetriever

    segs, _ = load("demo_indexing.txt")
    hits = MeetingRetriever(segs).retrieve("the database is lagging", k=1)
    assert "slow" in hits[0].text


def test_explanation_generation():
    need("gen")
    from backend.nlp.simplification import explain

    r = explain("load balancer", [], style="simplify")
    assert "glossary" in r["engine"] and hf.MODELS["gen"] in r["engine"]  # curated entry + model explanation
    r = explain("eventual consistency", [], style="simplify")
    assert hf.MODELS["gen"] in r["engine"] and "consisten" in r["explanation"].lower()


def test_diarization_on_synthetic_meeting():
    need("speaker")
    pytest.importorskip("faster_whisper")
    from backend.evaluation.metrics import speaker_accuracy
    from backend.speech.diarization import diarize
    from backend.speech.speech_recognition import transcribe_bytes

    gt = json.loads((EVAL / "audio" / "three_speakers.json").read_text())["turns"]
    asr = transcribe_bytes((EVAL / "audio" / "three_speakers.wav").read_bytes(), suffix=".wav", language="en")
    labels, cents = diarize(asr["audio"], asr["segments"], [])

    def gold(seg):
        return max(gt, key=lambda t: max(0.0, min(seg["end"], t["end"]) - max(seg["start"], t["start"])))["speaker"]
    assert len(cents) >= 2
    assert speaker_accuracy(labels, [gold(s) for s in asr["segments"]]) >= 0.6

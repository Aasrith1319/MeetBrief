"""Component tests for the NLP pipeline (transcript, extraction, QA, summaries)."""
from backend.capture.transcript_normalizer import dedupe_caption_updates, detect_format, parse_transcript, to_segments
from backend.models import SegmentIn
from backend.nlp.action_extraction import find_deadline
from backend.nlp.decision_extraction import classify_statement
from backend.nlp.language_detection import detect_language
from backend.nlp.simplification import explain, simplify_text
from backend.nlp.summarization import summarize
from backend.nlp.translation import preservation_check, translate
from backend.rag.answer_generation import answer_question
from backend.speech.alignment import assign_speakers

from .conftest import load


# ------------------------------------------------------------ transcripts
def test_parse_plain_text_clock_times(demo):
    segs, _ = demo
    assert [s.speaker_name for s in segs] == ["Rahul", "Priya", "Arjun", "Rahul", "Rahul"]
    assert segs[0].start_time == 10 * 3600 and segs[1].start_time == 10 * 3600 + 120
    assert segs[0].text.startswith("We need to improve")


def test_formats_detected():
    assert detect_format("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi") == "vtt"
    assert detect_format("1\n00:00:01,000 --> 00:00:02,000\nhi") == "srt"
    assert detect_format('{"segments": []}') == "json"
    assert detect_format("[00:00:05] Meera: hello") == "text"


def test_vtt_generic_speakers_are_ids_not_names():
    segs, memory = load("unlabeled_speakers.vtt")
    assert all(s.speaker_name is None for s in segs)
    assert {s.speaker_id for s in segs} == {"Speaker 1", "Speaker 2"}
    task = memory.action_items[0]
    assert task.owner == "Speaker 2" and "owner_identity_unknown" in task.flags


def test_json_and_srt():
    segs, memory = load("sample.json")
    assert segs[1].speaker_name == "Omar" and segs[1].start_time == 4
    segs, memory = load("sample.srt")
    assert memory.action_items[0].owner == "Priya"


def test_caption_dedupe():
    items = [SegmentIn(text=t, speaker_name="Rahul") for t in ["We need", "We need to", "We need to improve speed."]]
    out = dedupe_caption_updates(items)
    assert len(out) == 1 and out[0].text == "We need to improve speed."


def test_filler_removal():
    seg = to_segments("m", [SegmentIn(text="Um so the the database is slow", speaker_name="A")])[0]
    assert seg.text == "so the database is slow"


# --------------------------------------------------------------- language
def test_language_detection():
    assert detect_language("The database queries are slow and we should add an index.").language == "en"
    assert detect_language("ఈరోజు మనం API performance గురించి మాట్లాడదాం").language == "te-en"
    assert detect_language("అందరికీ నమస్కారం").language == "te"
    assert detect_language("नमस्ते सबको, आज की बैठक शुरू करते हैं").language == "hi"
    r = detect_language("Login bug ka main reason hai session token expire ho raha hai")
    assert r.language == "hi-en" and r.code_switched
    assert detect_language("ok").language == "und"


# -------------------------------------------------------------- extraction
def test_demo_decisions_and_tasks(demo):
    _, m = demo
    confirmed = [d for d in m.decisions if d.status == "confirmed"]
    assert len(confirmed) == 1 and "indexing first" in confirmed[0].summary.lower() and confirmed[0].speaker == "Rahul"
    assert {d.speaker for d in m.decisions if d.status == "proposed"} == {"Priya", "Arjun"}
    assert len(m.action_items) == 1
    t = m.action_items[0]
    assert (t.owner, t.deadline, t.status) == ("Priya", "Friday", "open")


def test_decision_revision(sprint):
    _, m = sprint
    old = next(d for d in m.decisions if "Friday" in d.summary and "2.4" in d.summary)
    new = next(d for d in m.decisions if "postpone" in d.summary.lower())
    assert old.status == "superseded" and old.superseded_by == new.decision_id and new.supersedes == old.decision_id


def test_sprint_tasks(sprint):
    _, m = sprint
    by_owner = {t.owner: t for t in m.action_items}
    karthik = [t for t in m.action_items if t.owner == "Karthik"]
    assert {t.task_text for t in karthik} == {"Implement the lazy loading", "Add performance metrics to the dashboard"}
    assert next(t for t in karthik if "lazy" in t.task_text).deadline == "Wednesday"
    assert by_owner["Sana"].deadline == "next Monday"
    assert by_owner["David"].deadline == "today"
    unknown = [t for t in m.action_items if t.owner == "unknown"]
    assert unknown and "release notes" in unknown[0].task_text.lower() and unknown[0].status == "uncertain"


def test_questions(sprint):
    _, m = sprint
    status = {q.text: q.status for q in m.open_questions}
    assert status["Do we know which payment providers are used most often?"] == "unresolved"
    assert status["How long will the migration downtime be?"] == "answered"


def test_topics(sprint):
    _, m = sprint
    labels = [t.label.lower() for t in m.topics]
    assert len(m.topics) >= 3
    assert any("release" in l for l in labels) and any("migration" in l for l in labels)


def test_classifier_and_deadlines():
    assert classify_statement("Let's go with Postgres.") == "confirmed"
    assert classify_statement("I suggest we use Redis.") == "proposed"
    assert classify_statement("Let's discuss the budget.") is None
    assert classify_statement("What tool should we use?") is None
    assert find_deadline("please finish it by next Friday") == "next Friday"
    assert find_deadline("due March 3rd") == "March 3rd"
    assert find_deadline("by end of the week") == "end of the week"


# ---------------------------------------------------------------- QA / RAG
def test_why_question_not_invented(demo):
    segs, m = demo
    r = answer_question("Why did the team choose indexing first?", segs, m, [])
    assert r["insufficient_evidence"] and "not explicitly stated" in r["answer"]
    assert any("indexing first" in e["text"] for e in r["evidence"])


def test_why_question_with_stated_reason(sprint):
    segs, m = sprint
    r = answer_question("Why did we choose lazy loading first?", segs, m, [])
    assert not r["insufficient_evidence"] and "because" in r["answer"]


def test_owner_and_deadline_questions(demo):
    segs, m = demo
    assert "Priya" in answer_question("Who will complete the indexing changes?", segs, m, [])["answer"]
    assert "Friday" in answer_question("When is the indexing due?", segs, m, [])["answer"]


def test_abstains_when_not_in_transcript(demo):
    segs, m = demo
    r = answer_question("What is the marketing budget for next year?", segs, m, [])
    assert r["insufficient_evidence"] and not r["evidence"]


def test_follow_up_uses_history(demo):
    segs, m = demo
    history = [{"role": "user", "content": "What did Arjun suggest about caching?"},
               {"role": "assistant", "content": "Arjun suggested caching."}]
    r = answer_question("and who decided?", segs, m, history)
    assert r["evidence"]


def test_speaker_filter(demo):
    segs, m = demo
    r = answer_question("What did Priya say?", segs, m, [])
    assert all(e["speaker"] == "Priya" for e in r["evidence"])


# ---------------------------------------------------------------- summaries
def test_catchup_summary(demo):
    segs, m = demo
    out = summarize(segs, m, "catchup")
    text = out["summary"]
    assert "Main problem" in text and "Decisions" in text and "Priya" in text and "Friday" in text
    assert out["evidence"]  # claims are linked to segments


def test_summary_modes(sprint):
    segs, m = sprint
    for mode in ["quick", "detailed", "chronological", "topic", "personalized"]:
        out = summarize(segs, m, mode, focus="technical" if mode == "personalized" else None)
        assert out["summary"] and out["engine"] == "extractive (TextRank) + rules"
    rng = summarize(segs, m, "catchup", from_time=300)
    assert rng["segments_covered"] < len(segs)


def test_summary_empty_meeting_explains_limitation():
    from backend.models import MeetingMemory

    out = summarize([], MeetingMemory(meeting_id="x"), "catchup")
    assert "cannot reconstruct" in out["note"]


def test_translation_without_engine_is_honest():
    r = translate("Priya will finish by Friday.", "te")
    assert r["translated"] is False and r["warnings"]
    assert preservation_check("Release 2.4 on 12/05", "Release on Friday") != []


# ----------------------------------------------------------------- explain
def test_explain_glossary_and_context(demo):
    segs, _ = demo
    r = explain("database indexing", segs, style="analogy")
    assert "textbook" in r["explanation"] and r["meeting_context"]
    steps = explain("indexing", segs, style="step_by_step")["explanation"]
    assert "1." in steps and "2." in steps
    again = explain("indexing", segs, style="simplify", previous="An index is ...")
    assert again["explanation"] != explain("indexing", segs, style="simplify")["explanation"]


def test_simplify_text():
    assert "use" in simplify_text("We will utilize the new methodology.")


def test_alignment():
    asr = [{"start": 0.0, "end": 2.0, "text": "hello"}, {"start": 2.0, "end": 4.0, "text": "hi there"}]
    turns = [{"start": 0.0, "end": 2.1, "speaker": "SPEAKER_00"}, {"start": 2.1, "end": 4.0, "speaker": "SPEAKER_01"}]
    out = assign_speakers(asr, turns)
    assert [o["speaker"] for o in out] == ["SPEAKER_00", "SPEAKER_01"]
    assert assign_speakers(asr, [])[0]["flags"] == ["speaker_unknown"]

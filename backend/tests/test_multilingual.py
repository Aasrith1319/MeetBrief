"""Multilingual speech: language limits, fake-line filter, English of non-English speech, per-viewer translation."""
from types import SimpleNamespace

from backend.api import service
from backend.auth import member_route_allowed
from backend.models import SegmentIn
from backend.speech import speech_recognition as sr


def seg(text, no_speech=0.1, logprob=-0.3, ratio=1.2):
    return SimpleNamespace(text=text, no_speech_prob=no_speech, avg_logprob=logprob, compression_ratio=ratio)


def test_fake_lines_are_dropped_but_real_speech_kept():
    assert not sr._keep(seg("Participants", no_speech=0.5, logprob=-0.6))
    assert not sr._keep(seg("Thank you.", no_speech=0.7))
    assert not sr._keep(seg("ರೂತೂರೂತೂರೂತೂರೂತೂರೂತೂರೂತೂ"))           # decoding loop
    assert not sr._keep(seg("", ))
    assert sr._keep(seg("Thank you.", no_speech=0.05, logprob=-0.2))  # clearly spoken
    assert sr._keep(seg("We will meet tomorrow at 4 o'clock.", no_speech=0.84, logprob=-0.77))  # quiet but real


def test_script_check_catches_wrong_script():
    assert sr.script_ok("నమస్కారం అందరికీ", "te")
    assert not sr.script_ok("अन्दर की नमस्कारम", "te")  # Telugu speech written in Devanagari
    assert sr.script_ok("सभी को नमस्ते", "hi")
    assert sr.script_ok("anything", "en")


def test_language_limited_to_meeting_languages(monkeypatch):
    monkeypatch.setattr(sr.settings, "meeting_languages", ("en", "te", "kn", "hi", "ta"))
    model = SimpleNamespace(detect_language=lambda audio, vad_filter: ("ur", 0.5, [("ur", 0.5), ("hi", 0.3), ("te", 0.1)]))
    lang, prob = sr.pick_language(model, None)
    assert lang == "hi" and 0.7 < prob < 0.8   # Urdu is not a meeting language → best allowed one, renormalised


def test_english_of_speech_feeds_analysis_and_viewers_see_translated_from(client):
    mid = client.post("/api/meetings", json={"title": "multi", "platform": "test", "source_type": "audio"}).json()["id"]
    service.ingest(mid, [
        SegmentIn(text="Ravi will handle the database work.", source_type="audio", speaker_id="Speaker 1", language="en"),
        SegmentIn(text="Ravi will be working on the database.", text_en="Ravi will be working on the database.",
                  source_type="audio", speaker_id="Speaker 2", language="te"),
        SegmentIn(text="अमित टेस्टिंग का काम देखेगा", text_en="Amit will look after the testing work.",
                  source_type="audio", speaker_id="Speaker 3", language="hi"),
    ])
    segs = client.get(f"/api/meetings/{mid}/segments").json()["segments"]
    te, hi = segs[1], segs[2]
    assert "original_unavailable" in te["flags"]                       # only the English could be written
    assert hi["text"] == "Amit will look after the testing work."       # models read the English …
    assert hi["original_text"] == "अमित टेस्टिंग का काम देखेगा"          # … the words as spoken are kept for display
    tr = client.post(f"/api/meetings/{mid}/segments/translations", json={"target": "en"}).json()["translations"]
    assert hi["segment_id"] in tr and tr[hi["segment_id"]]["from_name"] == "Hindi"
    assert tr[te["segment_id"]]["from_name"] == "Telugu" and tr[te["segment_id"]]["text"]
    assert segs[0]["segment_id"] not in tr                               # English line: already in the reader's language
    # a Hindi reader: the Hindi line is shown as spoken, not translated
    tr_hi = client.post(f"/api/meetings/{mid}/segments/translations", json={"target": "hi"}).json()["translations"]
    assert hi["segment_id"] not in tr_hi


def test_english_of_speech_matches_english_captions():
    cap = service.to_segments("m", [SegmentIn(text="Ravi will be working on the database", speaker_name="Ravi")])
    audio = [SegmentIn(text="రవి డేటాబేస్", text_en="Ravi will be working on the database.", source_type="audio",
                       language="te")]
    kept, dropped = service.merge_audio_with_captions(cap, audio)
    assert not kept and dropped == 1


def test_room_members_can_read_translations():
    assert member_route_allowed("POST", "/api/meetings/abc/segments/translations")
    assert not member_route_allowed("POST", "/api/meetings/abc/segments")

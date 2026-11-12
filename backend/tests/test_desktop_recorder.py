"""tools/desktop_recorder.py: WAV encoding and chunk upload (backend mocked)."""
import importlib.util
import io
import wave
from pathlib import Path

import httpx
import numpy as np

spec = importlib.util.spec_from_file_location("desktop_recorder", Path(__file__).resolve().parents[2] / "tools/desktop_recorder.py")
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)


def test_wav_bytes_is_16k_mono_pcm():
    samples = np.sin(np.linspace(0, 100, rec.RATE)).astype(np.float32)
    with wave.open(io.BytesIO(rec.wav_bytes(samples))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, rec.RATE, rec.RATE)


def test_chunks_are_posted_with_offsets_and_silence_skipped():
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path, request.headers.get("X-MeetBrief-Token"), request.content))
        if request.url.path == "/api/meetings":
            return httpx.Response(200, json={"id": "m1"})
        return httpx.Response(200, json={"added": [{"start_time": 0.0, "speaker_id": "Speaker 1", "text": "hi"}]})

    up = rec.Uploader("http://test", "tok", None)
    up.http = httpx.Client(base_url="http://test", headers={"X-MeetBrief-Token": "tok"}, transport=httpx.MockTransport(handler))
    assert up.create("Demo") == "m1"
    assert up.send(np.zeros(rec.RATE, np.float32), 0.0) == 0  # silence is not uploaded
    assert up.send(0.3 * np.ones(rec.RATE, np.float32), 15.0) == 1
    paths = [c[1] for c in calls]
    assert paths == ["/api/meetings", "/api/meetings/m1/audio"]
    assert all(c[2] == "tok" for c in calls)
    assert b'name="offset"' in calls[1][3] and b"15.00" in calls[1][3]

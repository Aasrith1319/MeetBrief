"""MeetBrief desktop recorder: covers meetings that run in a desktop app (Zoom/Teams/Webex desktop clients,
phone bridges, in-room calls) where the Chrome extension has no tab to read captions or audio from.

It records an input device (a microphone, or a loopback device that carries the system's audio output:
BlackHole on macOS, "Stereo Mix"/WASAPI loopback on Windows, a PulseAudio monitor source on Linux), cuts the
stream into chunks and posts each chunk to the local backend's /api/meetings/{id}/audio endpoint, where Whisper
transcribes it and speaker diarization labels it. When recording stops, the meeting is finalized (final summary).

Usage:
    python tools/desktop_recorder.py --list-devices
    python tools/desktop_recorder.py --title "Lab sync" --device "BlackHole 2ch"
    python tools/desktop_recorder.py --title "Test" --file datasets/evaluation_data/audio/three_speakers.wav

Live recording needs `pip install sounddevice`; --file mode only needs PyAV (requirements-audio.txt).
Only record meetings where every participant has agreed to being recorded.
"""
from __future__ import annotations

import argparse
import io
import os
import queue
import sys
import time
import wave
from pathlib import Path

import httpx
import numpy as np

RATE = 16000
ROOT = Path(__file__).resolve().parents[1]


def wav_bytes(samples: np.ndarray) -> bytes:
    """float32 mono [-1, 1] → 16-bit PCM WAV."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def read_file(path: str) -> np.ndarray:
    import av

    with av.open(path) as container:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=RATE)
        parts = []
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                parts.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            parts.append(out.to_ndarray().reshape(-1))
    return np.concatenate(parts).astype(np.float32) if parts else np.zeros(0, np.float32)


def default_token() -> str:
    if os.environ.get("MEETBRIEF_TOKEN"):
        return os.environ["MEETBRIEF_TOKEN"]
    data_dir = Path(os.environ.get("MEETBRIEF_DATA_DIR", ROOT / "data"))
    token_file = data_dir / "api_token.txt"
    return token_file.read_text().strip() if token_file.exists() else ""


class Uploader:
    def __init__(self, api: str, token: str, language: str | None):
        headers = {"X-MeetBrief-Token": token} if token else {}
        self.http = httpx.Client(base_url=api.rstrip("/"), headers=headers, timeout=600)
        self.language = language
        self.meeting_id = ""

    def create(self, title: str) -> str:
        r = self.http.post("/api/meetings", json={"title": title, "platform": "desktop", "source_type": "audio"})
        r.raise_for_status()
        self.meeting_id = r.json()["id"]
        return self.meeting_id

    def send(self, samples: np.ndarray, offset: float) -> int:
        if float(np.sqrt(np.mean(samples ** 2))) < 1e-4:  # silence: nothing to transcribe
            return 0
        data = {"offset": f"{offset:.2f}"}
        if self.language:
            data["language"] = self.language
        r = self.http.post(f"/api/meetings/{self.meeting_id}/audio",
                           files={"file": ("chunk.wav", wav_bytes(samples), "audio/wav")}, data=data)
        if r.status_code >= 400:
            print(f"  chunk at {offset:.0f}s rejected: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 0
        added = r.json().get("added", [])
        for seg in added:
            print(f"  [{seg['start_time']:6.1f}s] {seg.get('speaker_name') or seg.get('speaker_id') or '?'}: {seg['text']}")
        return len(added)

    def finalize(self) -> dict:
        r = self.http.post(f"/api/meetings/{self.meeting_id}/finalize", json={})
        r.raise_for_status()
        return r.json()


def list_devices() -> None:
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("Live recording needs: pip install sounddevice")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"{i:3d}  {d['name']}  ({d['max_input_channels']} ch, {int(d['default_samplerate'])} Hz)")
    print("\nTo capture what the meeting app plays, pick a loopback device (macOS: BlackHole + a Multi-Output "
          "Device; Windows: Stereo Mix / WASAPI loopback; Linux: a '.monitor' source).")


def record_live(up: Uploader, device: str | None, chunk_s: float) -> None:
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("Live recording needs: pip install sounddevice")
    q: queue.Queue = queue.Queue()

    def callback(indata, _frames, _time, status):
        if status:
            print(f"  audio: {status}", file=sys.stderr)
        q.put(indata.mean(axis=1).copy())  # down-mix to mono

    dev = int(device) if device and device.isdigit() else device
    buf, offset, need = [], 0.0, int(chunk_s * RATE)
    print("Recording… press Ctrl+C to stop and build the final summary.")
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", device=dev, callback=callback):
        try:
            while True:
                buf.append(q.get())
                if sum(len(b) for b in buf) >= need:
                    chunk = np.concatenate(buf)
                    buf = []
                    up.send(chunk, offset)
                    offset += len(chunk) / RATE
        except KeyboardInterrupt:
            pass
    if buf:
        up.send(np.concatenate(buf), offset)


def record_file(up: Uploader, path: str, chunk_s: float) -> None:
    audio = read_file(path)
    step = int(chunk_s * RATE)
    print(f"Sending {len(audio) / RATE:.1f}s of audio from {path} in {chunk_s:.0f}s chunks")
    for start in range(0, len(audio), step):
        up.send(audio[start:start + step], start / RATE)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Record a desktop meeting into MeetBrief")
    p.add_argument("--api", default=os.environ.get("MEETBRIEF_API", "http://127.0.0.1:8000"))
    p.add_argument("--token", default=None, help="API token (default: $MEETBRIEF_TOKEN or data/api_token.txt)")
    p.add_argument("--title", default=time.strftime("Desktop meeting %Y-%m-%d %H:%M"))
    p.add_argument("--meeting", default=None, help="append to an existing meeting id instead of creating one")
    p.add_argument("--device", default=None, help="input device name or index (see --list-devices)")
    p.add_argument("--file", default=None, help="send an audio/video file instead of recording (testing)")
    p.add_argument("--chunk", type=float, default=15.0, help="seconds per chunk (default 15)")
    p.add_argument("--language", default=None, help="force a Whisper language code, e.g. en, hi, te")
    p.add_argument("--no-finalize", action="store_true")
    p.add_argument("--list-devices", action="store_true")
    args = p.parse_args(argv)

    if args.list_devices:
        list_devices()
        return 0
    up = Uploader(args.api, args.token if args.token is not None else default_token(), args.language)
    try:
        if args.meeting:
            up.meeting_id = args.meeting
        else:
            print(f"Meeting {up.create(args.title)} created: {args.title}")
        if args.file:
            record_file(up, args.file, args.chunk)
        else:
            record_live(up, args.device, args.chunk)
        if not args.no_finalize:
            final = up.finalize()
            summary = final.get("summary") or final.get("final_summary", {}).get("summary") or ""
            print("\nFinal summary:\n" + (summary if isinstance(summary, str) else str(summary)))
        print(f"\nOpen it in the side panel or at {args.api.rstrip('/')}/app (meeting {up.meeting_id})")
    except httpx.HTTPError as exc:
        print(f"Backend error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

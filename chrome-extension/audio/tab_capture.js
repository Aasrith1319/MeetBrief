/* Offscreen document: records the authorised meeting tab's audio (F04, workflow L).
 * - Uses a tabCapture stream id; no microphone permission is requested.
 * - Plays the captured audio back so the user still hears the meeting.
 * - Records self-contained ~15 s WebM/Opus chunks and uploads each to the backend,
 *   which transcribes and deletes the audio immediately. Nothing is stored here. */
const CHUNK_MS = 15000;
let stream = null, ctx = null, recorder = null, session = null, running = false, paused = false;
let activeMs = 0, chunkStartedAt = 0;
let analyser = null, peak = 0, meter = null; // loudest sample in the current chunk (0 = digital silence)

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.target !== "offscreen") return false;
  (async () => {
    if (msg.type === "offscreen:start") return start(msg);
    if (msg.type === "offscreen:pause") { paused = true; if (recorder && recorder.state === "recording") recorder.stop(); return { ok: true }; }
    if (msg.type === "offscreen:resume") { paused = false; if (running) recordChunk(); return { ok: true }; }
    if (msg.type === "offscreen:stop") { stop(); return { ok: true }; }
    return { error: "unknown" };
  })().then(reply, (e) => reply({ error: String(e.message || e) }));
  return true;
});

async function start({ streamId, meetingId, apiBase, token, tabId, uploadUrl, headers, backup }) {
  if (running) stop();
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId } }, video: false,
  });
  ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(stream);
  src.connect(ctx.destination); // keep the meeting audible
  analyser = ctx.createAnalyser(); analyser.fftSize = 2048; src.connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  meter = setInterval(() => { analyser.getFloatTimeDomainData(buf); for (const v of buf) peak = Math.max(peak, Math.abs(v)); }, 200);
  // uploadUrl/headers: where chunks go (a meeting, or a shared room when this tab is the room's capturer)
  session = { meetingId, tabId, backup: !!backup, uploadUrl: uploadUrl || `${apiBase}/api/meetings/${meetingId}/audio`,
              headers: headers || (token ? { "X-MeetBrief-Token": token } : {}) };
  running = true; paused = false; activeMs = 0;
  recordChunk();
  return { ok: true };
}

function recordChunk() {
  if (!running || paused || !stream) return;
  const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
  const parts = [];
  const offset = activeMs / 1000;
  peak = 0;
  recorder = new MediaRecorder(stream, { mimeType: mime });
  recorder.ondataavailable = (e) => { if (e.data && e.data.size) parts.push(e.data); };
  recorder.onstop = () => {
    activeMs += Date.now() - chunkStartedAt;
    const blob = new Blob(parts, { type: mime });
    if (blob.size > 2000) upload(blob, offset, peak);
    if (running && !paused) recordChunk();
  };
  chunkStartedAt = Date.now();
  recorder.start();
  setTimeout(() => { if (recorder && recorder.state === "recording") recorder.stop(); }, CHUNK_MS);
}

async function upload(blob, offset, level = 0) {
  const s = session;
  if (!s) return;
  const fd = new FormData();
  fd.append("file", blob, "chunk.webm");
  fd.append("offset", String(offset));
  try {
    const res = await fetch(s.uploadUrl, { method: "POST", headers: s.headers, body: fd });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      chrome.runtime.sendMessage({ type: "offscreen:error", tabId: s.tabId, backup: s.backup, status: res.status,
                                   error: data.detail || `Transcription failed (${res.status})` });
      if (res.status === 501 || res.status === 409) stop(); // no speech model / another member records the room
      return;
    }
    const out = await res.json().catch(() => ({}));
    chrome.runtime.sendMessage({ type: "offscreen:chunk", meetingId: s.meetingId, tabId: s.tabId, level,
                                 heard: Array.isArray(out.added) ? out.added.length : null });
  } catch (e) {
    chrome.runtime.sendMessage({ type: "offscreen:error", tabId: s.tabId, error: `Backend unreachable: ${e.message}` });
  }
}

function stop() {
  running = false;
  if (recorder && recorder.state === "recording") recorder.stop();
  if (stream) stream.getTracks().forEach((t) => t.stop());
  if (ctx) ctx.close().catch(() => {});
  if (meter) clearInterval(meter);
  stream = ctx = recorder = analyser = meter = null;
}

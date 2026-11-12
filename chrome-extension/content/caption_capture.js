/* Caption capture with stabilisation and de-duplication (F02, workflow B step 3).
 *
 * Meeting platforms update a caption block progressively ("We need" → "We need to" →
 * "We need to improve…") and may rewrite recent words. A block is emitted once its text
 * has been stable for STABLE_MS, when it disappears, or when it grows past MAX_CHARS.
 * Only the new part beyond what was already emitted is sent, so no text is duplicated. */
(function () {
  // no "already loaded" guard: after an extension update the re-injected copy must replace the old class
  const STABLE_MS = 1800, POLL_MS = 700, FLUSH_MS = 3000, MAX_CHARS = 600, NO_CAPTIONS_MS = 12000;

  function commonWordPrefix(a, b) {
    const wa = a.split(" "), wb = b.split(" ");
    let i = 0;
    while (i < wa.length && i < wb.length && wa[i].toLowerCase().replace(/[^\p{L}\p{N}]/gu, "") === wb[i].toLowerCase().replace(/[^\p{L}\p{N}]/gu, "")) i++;
    return i;
  }

  class CaptionCapture {
    constructor(adapter, { onSegments, onStatus }) {
      this.adapter = adapter;
      this.onSegments = onSegments;
      const report = onStatus || (() => {});
      this.onStatus = (state, detail) => {  // report changes only, not the same state every poll
        if (state === this.lastStatus) return;
        this.lastStatus = state;
        report(state, detail);
      };
      this.blocks = new Map(); // key -> {speaker, text, emitted, firstSeen, lastChange}
      this.queue = [];
      this.running = false;
      this.paused = false;
      this.startedAt = 0;
      this.lastCaptionSeen = 0;
    }

    start() {
      if (this.running) return;
      this.running = true;
      this.paused = false;
      this.startedAt = Date.now();
      this.lastCaptionSeen = Date.now();
      this.observer = new MutationObserver(() => this.scheduleScan());
      this.observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      this.poll = setInterval(() => this.scan(), POLL_MS);
      this.flusher = setInterval(() => this.flush(), FLUSH_MS);
      this.scan();
    }

    pause() { this.finalizeAll(); this.flush(); this.paused = true; }
    resume() { this.blocks.clear(); this.paused = false; this.lastCaptionSeen = Date.now(); }

    stop() {
      if (!this.running) return;
      this.finalizeAll();
      this.flush();
      this.running = false;
      if (this.observer) this.observer.disconnect();
      clearInterval(this.poll);
      clearInterval(this.flusher);
    }

    scheduleScan() {
      if (this.scanPending) return;
      this.scanPending = true;
      setTimeout(() => { this.scanPending = false; this.scan(); }, 250);
    }

    scan() {
      if (!this.running || this.paused) return;
      const now = Date.now();
      const root = this.adapter.findCaptionRoot();
      if (!root) {
        if (now - this.lastCaptionSeen > NO_CAPTIONS_MS) this.onStatus("no_captions", this.adapter.captionsHint);
        this.finalizeAll();
        return;
      }
      const seen = new Set();
      let entries = [];
      try { entries = this.adapter.readCaptions(root); } catch (e) { console.warn("[MeetBrief] adapter error", e); }
      if (entries.length) {
        if (this.lastStatus === "no_captions") this.onStatus("capturing_captions");
        this.lastCaptionSeen = now;
      }
      for (const { key, speaker, text } of entries) {
        seen.add(key);
        const b = this.blocks.get(key);
        if (!b) { this.blocks.set(key, { speaker, text, emitted: "", firstSeen: now, lastChange: now, emittedAt: now }); continue; }
        if (b.text !== text) { b.text = text; b.lastChange = now; if (speaker) b.speaker = speaker; }
        if ((now - b.lastChange >= STABLE_MS && b.text !== b.emitted) || b.text.length - b.emitted.length > MAX_CHARS) this.emit(b, now);
      }
      for (const [key, b] of this.blocks) {
        if (!seen.has(key)) { this.emit(b, now); this.blocks.delete(key); }
      }
    }

    emit(b, now) {
      const text = b.text.trim();
      if (!text || text === b.emitted) return;
      let delta = text;
      if (b.emitted) {
        const shared = commonWordPrefix(b.emitted, text);
        const emittedWords = b.emitted.split(" ").length;
        if (shared >= emittedWords * 0.7) delta = text.split(" ").slice(Math.max(shared, emittedWords)).join(" ");
        else delta = text; // platform rewrote the caption substantially
      }
      if (delta.trim()) {
        this.queue.push({
          text: delta.trim(), speaker_name: b.speaker || null, source_type: "caption",
          start_time: ((b.emitted ? b.emittedAt : b.firstSeen) - this.startedAt) / 1000 + (this.offset || 0),
          end_time: (now - this.startedAt) / 1000 + (this.offset || 0),
        });
      }
      b.emitted = text;
      b.emittedAt = now;
    }

    finalizeAll() { const now = Date.now(); for (const b of this.blocks.values()) this.emit(b, now); }

    flush() {
      if (!this.queue.length) return;
      const batch = this.queue.splice(0, this.queue.length);
      this.onSegments(batch);
    }
  }

  window.MeetBriefCaptionCapture = CaptionCapture;
})();

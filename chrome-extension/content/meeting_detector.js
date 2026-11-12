/* Detects supported meeting pages (F01), notices when the user joins / leaves the call, and
 * bridges caption capture to the service worker. Join/leave drive the optional automatic mode:
 * join → capture starts, leave (or tab close) → capture stops and a final summary is built. */
(function () {
  // An earlier copy may still sit in this tab from before the extension was reloaded; it is orphaned (its
  // chrome.runtime is gone), so only a live copy blocks this one.
  if (window.__meetbriefDetector && window.__meetbriefAlive && window.__meetbriefAlive()) return;
  window.__meetbriefDetector = true;
  window.__meetbriefAlive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (_) { return false; } };
  const old = document.getElementById("meetbrief-status");
  if (old) old.remove();
  const adapter = window.MeetBriefAdapters.detect();
  if (!adapter) return;
  let capture = null;
  let inCall = false;
  let joinedAt = 0;

  const safe = (fn, fallback) => { try { return fn(); } catch (_) { return fallback; } };
  const alive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (_) { return false; } };
  const info = () => ({
    platform: adapter.name, platformId: adapter.id, experimental: !!adapter.experimental,
    title: adapter.meetingTitle(), inMeeting: safe(() => adapter.isInMeeting(), false),
    captionsVisible: !!safe(() => adapter.findCaptionRoot(), null), hint: adapter.captionsHint, url: location.origin + location.pathname,
    meetingKey: safe(() => adapter.meetingKey && adapter.meetingKey(), null),
  });
  const send = (msg) => {
    if (!alive()) return; // orphaned copy (extension reloaded): sendMessage would throw synchronously
    try { chrome.runtime.sendMessage(msg).catch(() => {}); } catch (_) { /* context invalidated */ }
  };

  // ---- on-page status label: shows whether MeetBrief has picked up this meeting (built with DOM APIs only,
  // no innerHTML / <style>, so the meeting page's CSP and Trusted Types rules don't block it)
  const indicator = (() => {
    const COLORS = { info: "#64748b", warn: "#d97706", ok: "#4f46e5", rec: "#e11d48" };
    let host = null, dot = null, label = null, hidden = false;
    function build() {
      host = document.createElement("div");
      host.id = "meetbrief-status";
      Object.assign(host.style, { position: "fixed", left: "12px", bottom: "84px", zIndex: "2147483647",
        display: "flex", alignItems: "center", gap: "6px", maxWidth: "min(560px, calc(100vw - 24px))", padding: "5px 6px 5px 10px",
        borderRadius: "999px", background: "rgba(17,24,39,.88)", color: "#f8fafc",
        font: "500 12px/1.3 system-ui, -apple-system, Segoe UI, sans-serif", boxShadow: "0 2px 8px rgba(0,0,0,.35)",
        cursor: "default", userSelect: "none" });
      dot = document.createElement("span");
      Object.assign(dot.style, { width: "8px", height: "8px", borderRadius: "50%", flex: "0 0 auto" });
      label = document.createElement("span");
      Object.assign(label.style, { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" });
      const close = document.createElement("button");
      close.textContent = "×";
      close.title = "Hide (MeetBrief keeps working)";
      Object.assign(close.style, { border: "0", background: "transparent", color: "#cbd5e1", font: "14px/1 system-ui",
        cursor: "pointer", padding: "0 4px" });
      close.addEventListener("click", () => { hidden = true; host.remove(); });
      host.append(dot, label, close);
      host.title = "MeetBrief status";
    }
    return {
      set(text, level = "info") {
        if (!window.__meetbriefAlive || !alive()) { if (host) host.remove(); return; } // orphaned copy: stay silent
        if (hidden) return;
        if (!host) build();
        if (!host.isConnected && document.body) document.body.appendChild(host);
        label.textContent = "MeetBrief: " + text;
        host.title = "MeetBrief: " + text;
        dot.style.background = COLORS[level] || COLORS.info;
      },
    };
  })();

  send({ type: "meeting:detected", info: info() });
  indicator.set(`${adapter.name} page detected · join the call to start`);

  // ---- join / leave detection (polling is robust to Meet's frequent DOM rewrites)
  let ticks = 0;
  let missing = 0; // consecutive checks without call controls: Meet hides its toolbar when the mouse is idle
  let joinedManually = false; // the user pressed Start while our call detection did not recognise the call
  function joined(manual) {
    inCall = true;
    joinedManually = manual;
    joinedAt = Date.now();
    indicator.set("In the call · connecting…");
    send({ type: "meeting:joined", info: { ...info(), manual } });
  }
  function checkCall() {
    const now = safe(() => adapter.isInMeeting(), false);
    if (now && joinedManually) joinedManually = false; // detection caught up: use it from now on
    // hasEnded reads the whole page text (forces layout), so check it only every 5th tick (10 s)
    missing = now ? 0 : missing + 1;
    // the "you left / call ended" page text only counts once the call controls are gone too
    const ended = inCall && !now && ++ticks % 2 === 0 ? safe(() => adapter.hasEnded && adapter.hasEnded(), false) : false;
    if (!inCall && now) {
      joined(false);
    } else if (inCall && (ended || (missing >= 3 && !joinedManually))) {
      // ignore flicker right after joining while Meet rebuilds the toolbar
      if (Date.now() - joinedAt < 4000) return;
      inCall = false;
      if (capture) { capture.stop(); capture = null; }
      indicator.set("You left the call · building the final summary", "ok");
      send({ type: "meeting:left", info: info() });
    }
  }
  setInterval(checkCall, 2000);
  checkCall();

  // shared-room heartbeat: lets the server pick one capturer and notice who is still in the call
  setInterval(() => { if (inCall) send({ type: "room:tick", info: info() }); }, 10000);

  // Early Join: the service worker opened this tab for a scheduled meeting → join with mic/camera off
  let autoJoinTimer = null;
  function startAutoJoin() {
    if (autoJoinTimer || !adapter.autoJoin) return;
    const t0 = Date.now();
    autoJoinTimer = setInterval(() => {
      if (safe(() => adapter.isInMeeting(), false) || Date.now() - t0 > 120000) {
        clearInterval(autoJoinTimer);
        autoJoinTimer = null;
        return;
      }
      safe(() => adapter.autoJoin(), false);
    }, 2500);
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    switch (msg.type) {
      case "mm:ping":
        reply(info());
        break;
      case "mm:status":
        indicator.set(msg.text, msg.level);
        reply({ ok: true });
        break;
      case "mm:autojoin":
        startAutoJoin();
        reply({ ok: true, ...info() });
        break;
      case "mm:start": {
        // Start pressed on a meeting page whose call screen we did not recognise: treat it as joined, so the
        // room / Share flow and heartbeats still run
        if (!inCall && adapter.meetingKey && safe(() => adapter.meetingKey(), null)) joined(true);
        if (msg.enableCaptions && !safe(() => adapter.findCaptionRoot(), null) && adapter.enableCaptions) {
          safe(() => adapter.enableCaptions(), false);
        }
        if (!capture) {
          capture = new window.MeetBriefCaptionCapture(adapter, {
            onSegments: (segments) => send({ type: "segments", segments }),
            onStatus: (state, detail) => send({ type: "capture:status", state, detail }),
          });
          capture.offset = msg.offset || 0;
        }
        capture.start();
        // captions may take a moment to appear after being switched on
        setTimeout(() => reply({ ok: true, ...info() }), msg.enableCaptions ? 1500 : 0);
        return true;
      }
      case "mm:pause":
        if (capture) capture.pause();
        reply({ ok: true });
        break;
      case "mm:resume":
        if (capture) capture.resume();
        reply({ ok: true });
        break;
      case "mm:stop":
        if (capture) { capture.stop(); capture = null; }
        reply({ ok: true });
        break;
      default:
        return false;
    }
    return true;
  });

  window.addEventListener("pagehide", () => {
    if (capture) capture.stop();
    if (inCall) send({ type: "meeting:left", info: info() });
  });
})();

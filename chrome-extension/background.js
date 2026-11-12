/* MeetBrief AI service worker.
 * - capture state machine (captions / tab audio), REC badge, notifications
 * - automatic meeting mode (join → capture, leave → final summary)
 * - shared rooms: Share prompt, auto-join the room of the same meeting link, one capturer at a time,
 *   "what you missed" for late joiners
 * - Early Join: open scheduled meetings at their start time and join with mic/camera off
 * State lives in chrome.storage because MV3 service workers sleep. */
importScripts("lib/identity.js");

const DEFAULT_BASE = "http://127.0.0.1:8000";
const OFFSCREEN_URL = "audio/offscreen.html";

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => {});
  chrome.contextMenus.create({ id: "mm-explain", title: "Explain with MeetBrief", contexts: ["selection"] });
  chrome.contextMenus.create({ id: "mm-audio", title: "Add tab audio to MeetBrief", contexts: ["page"],
    documentUrlPatterns: chrome.runtime.getManifest().content_scripts[0].matches });
  rescheduleAll();
  injectIntoOpenMeetingTabs();
});

/** Chrome does not add content scripts to tabs that were already open when the extension was installed or
 * reloaded, so meeting tabs opened earlier would stay invisible to MeetBrief until refreshed. */
async function injectIntoOpenMeetingTabs() {
  const cs = chrome.runtime.getManifest().content_scripts[0];
  const tabs = await chrome.tabs.query({ url: cs.matches }).catch(() => []);
  for (const tab of tabs) {
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: cs.js }).catch(() => {});
  }
}
chrome.runtime.onStartup.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => {});
  rescheduleAll();
});

// ------------------------------------------------------------------ helpers
async function conn() {
  const { apiBase, token } = await chrome.storage.local.get(["apiBase", "token"]);
  return { apiBase: (apiBase || DEFAULT_BASE).replace(/\/+$/, ""), token: token || "" };
}

async function backend(path, { method = "GET", body } = {}) {
  const { apiBase, token } = await conn();
  const ident = await MMIdentity.headers();
  const res = await fetch(apiBase + path, {
    method, headers: { "Content-Type": "application/json", ...(token ? { "X-MeetBrief-Token": token } : {}), ...ident },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.detail || `Backend error ${res.status}`); e.status = res.status; throw e; }
  return data;
}

async function prefs() {
  try { return await backend("/api/preferences"); } catch (_) { return {}; }
}

async function signedIn() {
  return Object.keys(await MMIdentity.headers()).length > 0;
}

async function getStates() { return (await chrome.storage.session.get("captures")).captures || {}; }
async function getState(tabId) { return (await getStates())[tabId] || { state: "idle", tabId }; }
let stateQueue = Promise.resolve();
/** All writes to the per-tab state map go through one queue, so concurrent handlers can't overwrite each other. */
function setState(tabId, patch) {
  const run = stateQueue.then(() => writeState(tabId, patch));
  stateQueue = run.catch(() => {});
  return run;
}
function removeState(tabId) {
  const run = stateQueue.then(async () => {
    const all = await getStates();
    delete all[tabId];
    await chrome.storage.session.set({ captures: all });
  });
  stateQueue = run.catch(() => {});
  return run;
}
async function writeState(tabId, patch) {
  const all = await getStates();
  const next = { ...(all[tabId] || { tabId }), ...patch, tabId, updatedAt: Date.now() };
  all[tabId] = next;
  await chrome.storage.session.set({ captures: all });
  // visible capture indicator on the toolbar icon (F07 / F71)
  const active = String(next.state).startsWith("capturing") || next.state === "no_captions";
  const text = active ? "REC" : next.state === "room_standby" ? "ROOM" : next.state === "paused" ? "II" : next.state === "ended" ? "✓" : next.platform ? "•" : "";
  chrome.action.setBadgeText({ tabId, text }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ tabId, color: active ? "#e11d48" : next.state === "room_standby" ? "#4f46e5" : next.state === "ended" ? "#14804a" : "#b45309" }).catch(() => {});
  chrome.action.setTitle({ tabId, title: `MeetBrief — ${statusLine(next)}` }).catch(() => {});
  chrome.tabs.sendMessage(tabId, { type: "mm:status", text: statusLine(next), level: statusLevel(next) }).catch(() => {});
  chrome.runtime.sendMessage({ type: "capture:state", state: next }).catch(() => {});
  if (next.meetingId && patch.state && !next.room) backend(`/api/meetings/${next.meetingId}`, { method: "PATCH", body: { capture_state: patch.state } }).catch(() => {});
  return next;
}

/** One-line status shown on the meeting page and as the toolbar tooltip. */
function statusLine(st) {
  const room = st.room;
  const roomName = room ? `room “${room.title || "meeting"}” (link registered)` : "";
  if (String(st.state).startsWith("capturing")) {
    const src = st.mode === "audio" ? "" : st.audioBackup ? " · captions + tab audio"
      : st.audioPending ? " · click the MeetBrief toolbar icon (or Alt+Shift+A) to add tab audio" : "";
    return (room ? `Capturing for ${roomName} · ${room.members || 1} member${room.members === 1 ? "" : "s"}` : "Capturing this meeting · live summary is building") + src;
  }
  switch (st.state) {
    case "room_standby": return `In ${roomName} · another member is capturing`;
    case "no_captions": return st.audioBackup ? "No captions · recording tab audio instead (turn on CC for names)"
      : "Waiting for captions · turn on CC, or click the MeetBrief toolbar icon to use tab audio";
    case "paused": return "Paused";
    case "ended": return "Meeting ended · summary ready";
    case "stopped": return "Stopped";
    default: return st.detail || (st.platform ? `${st.platform} detected` : "Ready");
  }
}
function statusLevel(st) {
  if (String(st.state).startsWith("capturing")) return "rec";
  if (st.state === "room_standby" || st.state === "ended") return "ok";
  return /not running|unavailable|failed|error|press Start|Confirm|off\b|Click Share/i.test(st.detail || "") ? "warn" : "info";
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}

async function pingContent(tabId) {
  try { return await chrome.tabs.sendMessage(tabId, { type: "mm:ping" }); } catch (_) { return null; }
}

async function ensureMeeting(tabId, info, isPrivate, sourceType) {
  const st = await getState(tabId);
  if (st.meetingId && st.url === info.url && st.state !== "ended" && !st.room) {
    try { await backend(`/api/meetings/${st.meetingId}`); return st.meetingId; } catch (_) { /* deleted: create new */ }
  }
  const m = await backend("/api/meetings", { method: "POST", body: {
    title: `${info.title || info.platform} — ${new Date().toLocaleString()}`, platform: info.platformId || "unknown",
    private: !!isPrivate, source_type: sourceType, url: info.url } });
  return m.id;
}

function notify(id, title, message, buttons) {
  chrome.notifications.create(id, { type: "basic", iconUrl: "icons/icon128.png", title, message, priority: 1,
    ...(buttons ? { buttons, requireInteraction: true } : {}) }, () => void chrome.runtime.lastError);
}

// -------------------------------------------------------------- offscreen
async function ensureOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  if (contexts.length) return;
  await chrome.offscreen.createDocument({ url: OFFSCREEN_URL, reasons: ["USER_MEDIA"],
    justification: "Record audio of the meeting tab the user explicitly chose, for transcription." });
}
async function closeOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  if (contexts.length) await chrome.offscreen.closeDocument().catch(() => {});
}

// ------------------------------------------------------- tab-audio backup
/** Hybrid capture: record the tab's audio next to the captions; the server keeps only what captions missed.
 * Chrome allows tab capture only after the user invoked MeetBrief on the tab (icon / side panel / button), so an
 * automatic start may fail until then — it is retried when the side panel opens. */
async function audioTarget(tabId) {
  const st = await getState(tabId);
  const { apiBase, token } = await conn();
  const headers = { ...(token ? { "X-MeetBrief-Token": token } : {}), ...(await MMIdentity.headers()) };
  const url = st.room ? `${apiBase}/api/rooms/${st.room.id}/audio` : `${apiBase}/api/meetings/${st.meetingId}/audio`;
  return { url, headers, st };
}

async function startAudioBackup(tabId, givenStreamId = null) {
  const st0 = await getState(tabId);
  const p = await prefs();
  if (p.audio_backup === false || st0.mode === "audio" || !st0.meetingId) return { ok: false };
  if (st0.room && st0.room.role !== "capturer") return { ok: false };
  if (st0.audioBackup) return { ok: true };
  // Chrome allows one tab-audio recorder per extension: never steal it from another meeting tab
  const others = Object.values(await getStates()).filter((x) => x.tabId !== tabId && (x.audioBackup || (x.mode === "audio" && String(x.state).startsWith("capturing"))));
  if (others.length) {
    await setState(tabId, { audioBackup: false, audioPending: false, detail: "Tab audio is already being recorded in another meeting tab — captions only here" });
    return { ok: false };
  }
  try {
    // a stream id from the side panel (requested inside the user's click) always works; asking from here only
    // works if Chrome considers the extension invoked on this tab
    const streamId = givenStreamId || await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
    await ensureOffscreen();
    const { url, headers, st } = await audioTarget(tabId);
    const res = await chrome.runtime.sendMessage({ type: "offscreen:start", target: "offscreen", streamId, uploadUrl: url,
      headers, meetingId: st.meetingId, tabId, backup: true });
    if (res && res.error) throw new Error(res.error);
    await setState(tabId, { audioBackup: true, audioPending: false, audioError: "" });
    return { ok: true };
  } catch (e) {
    await setState(tabId, { audioBackup: false, audioPending: true, audioError: String(e.message || e) });
    return { error: String(e.message || e) };
  }
}

async function stopAudioBackup(tabId) {
  const st = await getState(tabId);
  if (!st.audioBackup && !st.audioPending) return;
  if (st.audioBackup) {
    await chrome.runtime.sendMessage({ type: "offscreen:stop", target: "offscreen" }).catch(() => {});
    await closeOffscreen();
  }
  await setState(tabId, { audioBackup: false, audioPending: false });
}

// ------------------------------------------------------------ capture ops
async function startCaptions(tabId, { isPrivate = false, auto = false, meetingId = null, streamId = null } = {}) {
  const info = await pingContent(tabId);
  if (!info) {
    await setState(tabId, { state: "unsupported", detail: "Open a Google Meet (or experimental Zoom/Teams web) meeting tab." });
    return { error: "This tab is not a supported meeting page." };
  }
  const mid = meetingId || await ensureMeeting(tabId, info, isPrivate, "caption");
  const st = await getState(tabId);
  const p = auto ? await prefs() : {};
  const res = await chrome.tabs.sendMessage(tabId, { type: "mm:start", offset: st.offset || 0,
    enableCaptions: auto ? p.auto_enable_captions !== false : false }).catch(() => ({}));
  const visible = (res && res.captionsVisible) || info.captionsVisible;
  await setState(tabId, { state: visible ? "capturing_captions" : "no_captions", mode: "captions", meetingId: mid,
    platform: info.platform, url: info.url, auto, detail: visible ? (st.room ? "Capturing for the room" : auto ? "Started automatically" : "") : info.hint,
    startedAt: Date.now() });
  await startAudioBackup(tabId, streamId);
  return { ok: true, meetingId: mid };
}

async function startAudio(tabId, { isPrivate = false, streamId: givenStreamId = null } = {}) {
  const tab = await chrome.tabs.get(tabId);
  const info = await pingContent(tabId);
  await setState(tabId, { state: "waiting_authorization", mode: "audio", detail: "Authorize tab audio capture" });
  try {
    const pageInfo = info || { title: tab.title, platform: new URL(tab.url).hostname, platformId: "tab_audio", url: tab.url };
    const meetingId = await ensureMeeting(tabId, pageInfo, isPrivate, "audio");
    const streamId = givenStreamId || await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
    await ensureOffscreen();
    const { apiBase, token } = await conn();
    const headers = { ...(token ? { "X-MeetBrief-Token": token } : {}), ...(await MMIdentity.headers()) };
    const res = await chrome.runtime.sendMessage({ type: "offscreen:start", target: "offscreen", streamId, meetingId, tabId,
      uploadUrl: `${apiBase}/api/meetings/${meetingId}/audio`, headers });
    if (res && res.error) throw new Error(res.error);
    await setState(tabId, { state: "capturing_audio", mode: "audio", meetingId, platform: pageInfo.platform, url: pageInfo.url,
      detail: "Only this tab's audio is processed", startedAt: Date.now() });
    return { ok: true, meetingId };
  } catch (e) {
    await setState(tabId, { state: "error", detail: String(e.message || e) });
    return { error: `Tab audio capture failed: ${e.message || e}. Open the side panel from the toolbar icon on the meeting tab and try again.` };
  }
}

async function controlCapture(tabId, action) {
  const st = await getState(tabId);
  if (st.mode === "audio") {
    await chrome.runtime.sendMessage({ type: `offscreen:${action}`, target: "offscreen" }).catch(() => {});
    if (action === "stop") await closeOffscreen();
  } else {
    await chrome.tabs.sendMessage(tabId, { type: `mm:${action}` }).catch(() => {});
    if (st.audioBackup) {
      if (action === "stop") await stopAudioBackup(tabId);
      else await chrome.runtime.sendMessage({ type: `offscreen:${action}`, target: "offscreen" }).catch(() => {});
    }
  }
  const map = { pause: "paused", resume: st.mode === "audio" ? "capturing_audio" : "capturing_captions", stop: "stopped" };
  const elapsed = st.startedAt ? (Date.now() - st.startedAt) / 1000 : 0;
  await setState(tabId, { state: map[action], detail: "", offset: action === "stop" ? (st.offset || 0) + elapsed : st.offset });
  return { ok: true };
}

// ----------------------------------------------------------------- rooms
async function applyRole(tabId, role, room) {
  let st = await getState(tabId);
  if ((st.audioBackup || st.audioPending) && (role !== "capturer" || !st.room || st.room.id !== room.id)) {
    await stopAudioBackup(tabId);  // standby members don't record; a newly joined room needs the room's upload URL
    st = await getState(tabId);
  }
  const capturing = String(st.state).startsWith("capturing") || st.state === "no_captions";
  const roomInfo = { id: room.id, meetingId: room.meeting_id, role, title: room.title, sharedBy: room.shared_by,
    capturer: room.capturer, members: (room.members || []).filter((m) => m.status === "approved").length,
    sharer: !!(room.me && room.me.role === "sharer"), missed: room.me ? room.me.missed_seconds : (st.room && st.room.missed) || 0 };
  if (role === "capturer" && !capturing) {
    await setState(tabId, { room: roomInfo, meetingId: room.meeting_id });
    await startCaptions(tabId, { auto: true, meetingId: room.meeting_id });
  } else if (role === "capturer") {
    await setState(tabId, { room: roomInfo, meetingId: room.meeting_id });
    const now = await getState(tabId);
    if (!now.audioBackup && !now.audioPending) await startAudioBackup(tabId);  // pending → retried when the panel opens
  } else if (role === "standby") {
    if (capturing) await chrome.tabs.sendMessage(tabId, { type: "mm:stop" }).catch(() => {});
    await setState(tabId, { room: roomInfo, meetingId: room.meeting_id, state: "room_standby",
      detail: room.capturer ? `${room.capturer} is capturing for the room` : "Waiting for a capturer" });
  } else {
    await setState(tabId, { room: roomInfo });
  }
}

/** Not in a room yet: someone else in the same meeting may have shared it after we joined, so look again. */
async function lookForRoom(tabId, info) {
  if (!info || !info.meetingKey || !(await signedIn())) return;
  try {
    const look = await backend(`/api/rooms/lookup?key=${encodeURIComponent(info.meetingKey)}`);
    if (!look.exists) return;
    chrome.notifications.clear(`mm-share:${tabId}`);
    await chrome.storage.session.remove(`pendingShare:${tabId}`);
    await joinRoom(tabId, look.id, info);
  } catch (_) { /* backend restarting: try again on the next tick */ }
}

async function heartbeat(tabId, info) {
  const st = await getState(tabId);
  if (!st.room) return lookForRoom(tabId, info);
  try {
    const hb = await backend(`/api/rooms/${st.room.id}/heartbeat`, { method: "POST",
      body: { in_call: true, captions_visible: !!(info && info.captionsVisible) } });
    if (hb.role === "ended") {
      await chrome.tabs.sendMessage(tabId, { type: "mm:stop" }).catch(() => {});
      await setState(tabId, { state: "ended", detail: "The room was ended by the sharer" });
      return;
    }
    await applyRole(tabId, hb.role, hb.room);
  } catch (e) {
    await setState(tabId, { detail: `Room unreachable: ${e.message}` });
  }
}

async function joinRoom(tabId, roomId, info) {
  const room = await backend(`/api/rooms/${roomId}/join`, { method: "POST", body: { in_call: true } });
  if (room.me && room.me.status === "pending") {
    await setState(tabId, { room: { id: room.id, role: "pending", title: room.title }, state: "idle",
      detail: `Waiting for ${room.shared_by || "the sharer"} to approve you` });
    notify(`mm-pending:${tabId}`, "Waiting for approval", `${room.shared_by || "The sharer"} must approve you before you can see the room.`);
    return room;
  }
  await applyRole(tabId, "standby", room);
  await heartbeat(tabId, info);
  const missed = room.me ? room.me.missed_seconds : 0;
  if (missed > 60) {
    notify(`mm-late:${room.meeting_id}:${tabId}`, `You joined ${Math.round(missed / 60)} min late — catch-up ready`,
      `${room.title}: shared by ${room.shared_by}. Click to see what you missed.`);
  } else {
    notify(`mm-room:${room.meeting_id}:${tabId}`, "Joined the MeetBrief room", `${room.title}: shared by ${room.shared_by}. Live summary is on.`);
  }
  return room;
}

async function shareRoom(tabId, info) {
  const room = await backend("/api/rooms/share", { method: "POST", body: { meeting_key: info.meetingKey, platform: info.platformId,
    title: info.title || info.platform, url: info.url, in_call: true } });
  await applyRole(tabId, room.me && room.me.capturer ? "capturer" : "standby", room);
  await heartbeat(tabId, info);
  notify(`mm-shared:${room.meeting_id}:${tabId}`, "Meeting shared with MeetBrief",
    "Members who join later will get everything from now on. Click to open the live summary.");
  return room;
}

async function leaveRoom(tabId) {
  const st = await getState(tabId);
  if (!st.room) return null;
  try { return await backend(`/api/rooms/${st.room.id}/leave`, { method: "POST", body: {} }); } catch (_) { return null; }
}

/** In a call: join the meeting's room if it exists, otherwise offer to share it (or auto-share Early Join meetings). */
async function onJoinedCall(tabId, info) {
  const st = await getState(tabId);
  if (st.room && st.room.role !== "pending") return { ok: true };
  const early = await isEarlyTab(tabId);
  try {
    await backend("/api/health");
  } catch (_) {
    notify(`mm-nobackend:${tabId}`, "MeetBrief: meeting detected, but the backend is not running",
      "Start it in Terminal:  cd ~/nlp && ./run.sh   — then reload the meeting tab.");
    await setState(tabId, { platform: info.platform, detail: "Backend not running — start ./run.sh" });
    return { ok: false };
  }
  await setState(tabId, { inCall: true, platform: info.platform });
  const isSignedIn = await signedIn();
  const signInHint = info.meetingKey && !isSignedIn ? " To share it as a room, set your name in Settings → Account." : "";
  if (signInHint) await setState(tabId, { platform: info.platform, detail: "In the call · rooms off: set your name in Settings → Account" });
  if (info.meetingKey && isSignedIn) {
    try {
      const look = await backend(`/api/rooms/lookup?key=${encodeURIComponent(info.meetingKey)}`);
      if (look.exists) return { ok: true, room: await joinRoom(tabId, look.id, info) };
      const p = await prefs();
      if (early ? early.autoShare !== false : p.auto_share) return { ok: true, room: await shareRoom(tabId, info) };
      await chrome.storage.session.set({ [`pendingShare:${tabId}`]: info });
      await setState(tabId, { platform: info.platform, detail: "Meeting link not shared yet · Click Share on the MeetBrief notification" });
      notify(`mm-share:${tabId}`, "Share this meeting with MeetBrief?",
        `${info.title || info.platform}: members who join late will get everything said from now on.`,
        [{ title: "Share" }, { title: "Not now" }]);
    } catch (e) {
      await setState(tabId, { detail: `Rooms unavailable: ${e.message}` });
    }
  }
  // capture was started by hand (Start captions): only the room part above was needed
  if (info.manual) return { ok: true };
  // no room: local capture (automatic mode or Early Join)
  const p = await prefs();
  if ((early || (p.auto_capture && p.consent_acknowledged)) && !String(st.state).startsWith("capturing")) {
    const r = await startCaptions(tabId, { isPrivate: !!p.private_mode_default, auto: true });
    if (r.ok) notify(`mm-started:${tabId}`, early ? `MeetBrief joined “${early.title}” for you` : "MeetBrief is capturing this meeting",
      `${info.title || info.platform}: live summary is building. Click to open the side panel.${signInHint}`);
    return r;
  }
  await setState(tabId, { state: st.state === "idle" || !st.state ? "idle" : st.state, platform: info.platform,
    detail: `In a ${info.platform} call — press Start captions` });
  if (!String(st.state).startsWith("capturing")) {
    const why = !p.auto_capture ? "Automatic mode is off" : "Confirm the one-time recording consent first";
    notify(`mm-detected:${tabId}`, `MeetBrief: ${info.platform} meeting detected`,
      `${why}. Click to open MeetBrief and press Start captions (or turn on Automatic meeting mode in Settings).${signInHint}`);
  }
  return { ok: false };
}

/** Meeting over (left the call / closed the tab): stop capture, leave the room, build the final summary. */
async function endMeeting(tabId, { tabClosed = false } = {}) {
  const st = await getState(tabId);
  const active = String(st.state).startsWith("capturing") || ["paused", "no_captions", "room_standby"].includes(st.state);
  if (!st.meetingId || !active) return;
  if (st.mode === "audio" || st.audioBackup) {
    await chrome.runtime.sendMessage({ type: "offscreen:stop", target: "offscreen" }).catch(() => {});
    await closeOffscreen();
    if (st.audioBackup && !tabClosed) await setState(tabId, { audioBackup: false, audioPending: false });
  }
  if (st.mode !== "audio" && !tabClosed) {
    await chrome.tabs.sendMessage(tabId, { type: "mm:stop" }).catch(() => {});
  }
  await new Promise((r) => setTimeout(r, 3500)); // let the last caption batch arrive
  let result = null;
  if (st.room) {
    const left = await leaveRoom(tabId);
    if (left && left.room_ended) result = { summary: left.summary, counts: null };
  } else {
    try { result = await backend(`/api/meetings/${st.meetingId}/finalize`, { method: "POST", body: {} }); } catch (_) { /* backend down */ }
  }
  if (!tabClosed) await setState(tabId, { state: "ended", detail: st.room ? "You left — the room continues for others" : "Meeting ended — final summary ready" });
  chrome.runtime.sendMessage({ type: "meeting:finalized", meetingId: st.meetingId, result }).catch(() => {});
  const counts = result && result.counts ? `${result.counts.decisions} decisions · ${result.counts.action_items} action items · ${result.counts.segments} lines` : "";
  notify(`mm-ended:${st.meetingId}:${tabId}`, "Meeting ended — summary ready", counts || "Open MeetBrief to see the recap.");
}

// ------------------------------------------------------------ Early Join
function platformOf(url) {
  try {
    const u = new URL(url);
    if (u.hostname === "meet.google.com") return "google_meet";
    if (/(^|\.)zoom\.us$/.test(u.hostname)) return "zoom_web";
    if (u.hostname === "teams.microsoft.com" || u.hostname === "teams.live.com") return "teams_web";
  } catch (_) { /* invalid */ }
  return null;
}

/** Open meetings in the browser version of each app (desktop apps cannot be captured by an extension). */
function webJoinUrl(url) {
  const u = new URL(url);
  const zoom = url.match(/zoom\.us\/j\/(\d{9,12})/);
  const pwd = u.searchParams.get("pwd");
  if (zoom) return `https://app.zoom.us/wc/join/${zoom[1]}${pwd ? `?pwd=${encodeURIComponent(pwd)}` : ""}`;
  return url;
}

async function schedules() { return (await chrome.storage.local.get("schedules")).schedules || []; }

async function rescheduleAll() {
  const now = Date.now();
  const list = (await schedules()).filter((s) => s.start > now - 3 * 3600 * 1000);
  await chrome.storage.local.set({ schedules: list });
  for (const s of list) {
    if (s.start - 60000 > now) chrome.alarms.create(`early:${s.id}`, { when: s.start - 60000 });
  }
}

async function isEarlyTab(tabId) {
  const key = `early-tab:${tabId}`;
  return (await chrome.storage.session.get(key))[key] || null;
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (!alarm.name.startsWith("early:")) return;
  const id = alarm.name.slice(6);
  const s = (await schedules()).find((x) => x.id === id);
  if (!s) return;
  const tab = await chrome.tabs.create({ url: webJoinUrl(s.url), active: false });
  await chrome.storage.session.set({ [`early-tab:${tab.id}`]: s });
  notify(`mm-early:${tab.id}`, `Joining “${s.title}” for you`, "MeetBrief opened the meeting with your mic and camera off. Click to watch.");
});

chrome.tabs.onUpdated.addListener(async (tabId, change) => {
  if (change.status !== "complete" || !(await isEarlyTab(tabId))) return;
  for (let i = 0; i < 5; i++) {  // content script may need a moment
    try { await chrome.tabs.sendMessage(tabId, { type: "mm:autojoin" }); return; } catch (_) { await new Promise((r) => setTimeout(r, 1500)); }
  }
});

// -------------------------------------------------------------- messaging
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.target === "offscreen") return false; // handled by the offscreen document
  (async () => {
    const tabFor = async () => (await activeTab())?.id;
    switch (msg.type) {
      case "capture:get": {
        const id = await tabFor();
        if (!id) return { state: "idle" };
        return getState(id);
      }
      case "audio:backup": {  // "+ Add tab audio" in the side panel, with a stream id obtained inside the click
        const id = await tabFor();
        if (!id) return { error: "No active tab." };
        const cur = await getState(id);
        if (!String(cur.state).startsWith("capturing") && cur.state !== "no_captions") return { error: "Start capturing first." };
        if (cur.room && cur.room.role !== "capturer") return { error: "Only the member who captures the room records audio." };
        return startAudioBackup(id, msg.streamId);
      }
      case "capture:start": {
        const id = await tabFor();
        if (!id) return { error: "No active tab." };
        const cur = await getState(id);
        if (cur.room && cur.room.role !== "pending") {
          // in a shared room there is one transcript: never start a second capture or a separate meeting
          if (cur.room.role !== "capturer") {
            return { error: `${cur.room.capturer || "Another member"} is capturing for this room — you are on standby and already see the same live summary.` };
          }
          if (msg.mode === "audio") return { error: "In a shared room the capturer's captions are used; tab audio is not available here." };
          return startCaptions(id, { auto: true, meetingId: cur.room.meetingId, streamId: msg.streamId });
        }
        return msg.mode === "audio" ? startAudio(id, { isPrivate: msg.private, streamId: msg.streamId })
          : startCaptions(id, { isPrivate: msg.private, streamId: msg.streamId });
      }
      case "capture:pause": return controlCapture(await tabFor(), "pause");
      case "capture:resume": return controlCapture(await tabFor(), "resume");
      case "capture:stop": return controlCapture(await tabFor(), "stop");
      case "room:share": {
        const id = await tabFor();
        const info = id && await pingContent(id);
        const cur = id && await getState(id);
        const capturingHere = cur && (String(cur.state).startsWith("capturing") || cur.state === "no_captions" || cur.inCall);
        if (!info || !(info.inMeeting || capturingHere)) return { error: "Join the meeting first, then share it." };
        if (!info.meetingKey) return { error: "This meeting app does not expose a meeting link MeetBrief can use." };
        if (!(await signedIn())) return { error: "Sign in first (Settings → Account)." };
        return { ok: true, room: await shareRoom(id, info) };
      }
      case "room:end": {
        const id = await tabFor();
        const st = id && await getState(id);
        if (!st || !st.room) return { error: "Not in a room." };
        const r = await backend(`/api/rooms/${st.room.id}/end`, { method: "POST", body: {} });
        await chrome.tabs.sendMessage(id, { type: "mm:stop" }).catch(() => {});
        await setState(id, { state: "ended", detail: "Room ended" });
        return r;
      }
      case "schedule:list": return { schedules: await schedules() };
      case "schedule:add": {
        const platform = platformOf(msg.url || "");
        if (!platform) return { error: "Paste a Google Meet, Zoom or Microsoft Teams meeting link." };
        const start = Number(msg.start);
        if (!start || start < Date.now() - 60000) return { error: "Pick a start time in the future." };
        const s = { id: Math.random().toString(36).slice(2, 10), url: msg.url, title: (msg.title || "Meeting").slice(0, 120),
          start, platform, autoShare: msg.autoShare !== false };
        const list = [...(await schedules()), s].sort((a, b) => a.start - b.start);
        await chrome.storage.local.set({ schedules: list });
        chrome.alarms.create(`early:${s.id}`, { when: Math.max(Date.now() + 1000, start - 60000) });
        return { ok: true, schedules: list };
      }
      case "schedule:remove": {
        const list = (await schedules()).filter((s) => s.id !== msg.id);
        await chrome.storage.local.set({ schedules: list });
        chrome.alarms.clear(`early:${msg.id}`);
        return { ok: true, schedules: list };
      }
      case "meeting:detected":
        if (sender.tab) {
          const st = await getState(sender.tab.id);
          if (!st.state || ["idle", "unsupported", "ended", "stopped"].includes(st.state))
            await setState(sender.tab.id, { state: "idle", platform: msg.info.platform, detail: msg.info.inMeeting ? `${msg.info.platform} call detected` : `${msg.info.platform} page detected · join the call to start` });
        }
        return { ok: true };
      case "meeting:joined":
        return sender.tab ? onJoinedCall(sender.tab.id, msg.info) : { ok: false };
      case "room:tick":
        if (sender.tab) await heartbeat(sender.tab.id, msg.info);
        return { ok: true };
      case "meeting:left":
        if (sender.tab) {
          await endMeeting(sender.tab.id);
          await setState(sender.tab.id, { room: null, inCall: false });
        }
        return { ok: true };
      case "capture:status":
        if (sender.tab) {
          const st = await getState(sender.tab.id);
          if (!["ended", "stopped", "room_standby"].includes(st.state)) await setState(sender.tab.id, { state: msg.state, detail: msg.detail || "" });
        }
        return { ok: true };
      case "segments": {
        const tabId = sender.tab && sender.tab.id;
        const st = await getState(tabId);
        if (!st.meetingId || ["paused", "stopped", "room_standby", "ended"].includes(st.state)) return { ok: false };
        const path = st.room ? `/api/rooms/${st.room.id}/segments` : `/api/meetings/${st.meetingId}/segments`;
        try {
          const res = await backend(path, { method: "POST", body: { segments: msg.segments } });
          if (st.state === "no_captions") await setState(tabId, { state: "capturing_captions", detail: "" });
          chrome.runtime.sendMessage({ type: "segments:added", meetingId: st.meetingId, count: res.count }).catch(() => {});
          return { ok: true };
        } catch (e) {
          if (e.status === 409 && st.room) { // another member became the capturer → stand by
            await chrome.tabs.sendMessage(tabId, { type: "mm:stop" }).catch(() => {});
            await heartbeat(tabId, null);
          } else {
            await setState(tabId, { detail: `Backend unreachable: ${e.message}` });
          }
          return { error: e.message };
        }
      }
      case "offscreen:chunk": {
        chrome.runtime.sendMessage({ type: "segments:added", meetingId: msg.meetingId }).catch(() => {});
        if (msg.tabId) {  // tell the user whether the tab is actually playing sound (their own voice never is)
          const level = Number(msg.level) || 0;
          await setState(msg.tabId, { audioLevel: level, audioDetail: level < 0.005
            ? "Tab audio is silent — nobody else is speaking (your own voice is never in the tab's audio)"
            : `Tab audio heard (level ${Math.round(level * 100)}%)` });
          console.log("[MeetBrief] tab audio chunk level", level.toFixed(4), "segments", msg.heard);
        }
        return { ok: true };
      }
      case "offscreen:error": {
        if (!msg.tabId) return { ok: true };
        if (msg.backup) {  // captions keep running; only the audio backup is affected
          const stopped = msg.status === 501 || msg.status === 409;
          await setState(msg.tabId, { ...(stopped ? { audioBackup: false } : {}), detail: `Tab-audio backup: ${msg.error}` });
        } else {
          await setState(msg.tabId, { state: "error", detail: msg.error });
        }
        return { ok: true };
      }
      default: return { error: "unknown message" };
    }
  })().then(reply, (e) => reply({ error: String(e.message || e) }));
  return true;
});

// meeting tab closed → leave the room / final summary, forget the tab state
chrome.tabs.onRemoved.addListener(async (tabId) => {
  await endMeeting(tabId, { tabClosed: true });
  await removeState(tabId);
  await chrome.storage.session.remove([`early-tab:${tabId}`, `pendingShare:${tabId}`]);
});

// Share prompt buttons
chrome.notifications.onButtonClicked.addListener(async (id, index) => {
  if (!id.startsWith("mm-share:")) return;
  const tabId = Number(id.split(":")[1]);
  const key = `pendingShare:${tabId}`;
  const info = (await chrome.storage.session.get(key))[key];
  chrome.notifications.clear(id);
  await chrome.storage.session.remove(key);
  if (index === 0 && info) {
    try { await shareRoom(tabId, info); } catch (e) { notify(`mm-err:${tabId}`, "Could not share the meeting", e.message); }
  }
});

// clicking a MeetBrief notification opens the side panel on that tab (a click is a user gesture)
chrome.notifications.onClicked.addListener(async (id) => {
  const tabId = Number(id.split(":").pop());
  try {
    const tab = await chrome.tabs.get(tabId);
    await chrome.windows.update(tab.windowId, { focused: true });
    await chrome.tabs.update(tabId, { active: true });
    await chrome.sidePanel.open({ tabId });
  } catch (_) {
    const win = await chrome.windows.getLastFocused().catch(() => null);
    if (win) chrome.sidePanel.open({ windowId: win.id }).catch(() => {});
  }
  if (!id.startsWith("mm-share:")) chrome.notifications.clear(id);
});

// Chrome hands out a tab's audio only after the user invoked the extension ON that tab: the toolbar icon, the
// keyboard shortcut or the right-click menu (a click inside the side panel does not count). Each of those adds
// the audio backup straight away; the grant lasts until the tab navigates, so later automatic starts work too.
async function invokedOnTab(tab) {
  if (!tab || !tab.id) return;
  const st = await getState(tab.id);
  if ((String(st.state).startsWith("capturing") || st.state === "no_captions") && st.mode !== "audio" && !st.audioBackup) {
    const r = await startAudioBackup(tab.id);
    if (r && r.error) notify(`mm-audio:${tab.id}`, "Tab audio could not start", r.error);
  }
}
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});  // first, while the click still counts as a gesture
  invokedOnTab(tab);
});
chrome.commands.onCommand.addListener((cmd, tab) => {
  if (cmd === "add-tab-audio") invokedOnTab(tab);
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "mm-audio") { if (tab) chrome.sidePanel.open({ tabId: tab.id }).catch(() => {}); return invokedOnTab(tab); }
  if (info.menuItemId !== "mm-explain" || !info.selectionText) return;
  await chrome.storage.session.set({ pendingExplain: info.selectionText.slice(0, 4000) });
  if (tab) chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
});

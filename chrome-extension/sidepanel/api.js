/* MeetBrief AI — API client shared by the side panel and the standalone web app.
 * In the extension, connection settings live in chrome.storage.local.
 * In the web app (served by the backend at /app/), they are injected as window.MEETBRIEF_CONFIG.
 */
(function () {
  const isExtension = typeof chrome !== "undefined" && !!(chrome.runtime && chrome.runtime.id);
  const DEFAULT_BASE = "http://127.0.0.1:8000";

  const store = {
    async get(keys) {
      if (isExtension && chrome.storage) return chrome.storage.local.get(keys);
      const out = {};
      for (const k of keys) {
        try { const v = localStorage.getItem("mm_" + k); if (v !== null) out[k] = JSON.parse(v); } catch (_) { /* storage blocked */ }
      }
      return out;
    },
    async set(obj) {
      if (isExtension && chrome.storage) return chrome.storage.local.set(obj);
      for (const [k, v] of Object.entries(obj)) {
        try { localStorage.setItem("mm_" + k, JSON.stringify(v)); } catch (_) { /* storage blocked */ }
      }
    },
  };

  const config = { apiBase: DEFAULT_BASE, token: "", standalone: !isExtension };

  async function loadConfig() {
    if (window.MEETBRIEF_CONFIG) {
      Object.assign(config, window.MEETBRIEF_CONFIG);
    } else {
      const saved = await store.get(["apiBase", "token"]);
      if (saved.apiBase) config.apiBase = saved.apiBase;
      if (saved.token) config.token = saved.token;
    }
    return config;
  }

  async function saveConnection(apiBase, token) {
    config.apiBase = (apiBase || DEFAULT_BASE).replace(/\/+$/, "");
    config.token = token || "";
    await store.set({ apiBase: config.apiBase, token: config.token });
  }

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  async function request(path, { method = "GET", body, form, raw } = {}) {
    const headers = {};
    if (config.token) headers["X-MeetBrief-Token"] = config.token;
    // shared rooms: identify the user (Google sign-in or test identity) — extension only
    if (isExtension && window.MMIdentity) Object.assign(headers, await window.MMIdentity.headers());
    let payload;
    if (form) payload = form;
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    let res;
    try {
      res = await fetch(config.apiBase + path, { method, headers, body: payload });
    } catch (e) {
      throw new ApiError(0, `Cannot reach the MeetBrief backend at ${config.apiBase || window.location.origin}. Is it running?`);
    }
    if (raw) {
      if (!res.ok) throw new ApiError(res.status, await res.text());
      return res;
    }
    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
    if (!res.ok) {
      const detail = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText;
      throw new ApiError(res.status, detail);
    }
    return data;
  }

  const api = {
    health: () => request("/api/health"),
    privacy: () => request("/api/privacy"),
    prefs: () => request("/api/preferences"),
    savePrefs: (values) => request("/api/preferences", { method: "PUT", body: { values } }),
    meetings: (q) => request("/api/meetings" + (q ? `?q=${encodeURIComponent(q)}` : "")),
    createMeeting: (m) => request("/api/meetings", { method: "POST", body: m }),
    meeting: (id) => request(`/api/meetings/${id}`),
    updateMeeting: (id, fields) => request(`/api/meetings/${id}`, { method: "PATCH", body: fields }),
    deleteMeeting: (id) => request(`/api/meetings/${id}`, { method: "DELETE" }),
    deleteTranscript: (id) => request(`/api/meetings/${id}/transcript`, { method: "DELETE" }),
    deleteAll: () => request("/api/data", { method: "DELETE" }),
    upload: (file, { title, isPrivate, meetingId } = {}) => {
      const fd = new FormData();
      fd.append("file", file);
      if (title) fd.append("title", title);
      fd.append("private", isPrivate ? "true" : "false");
      if (meetingId) fd.append("meeting_id", meetingId);
      return request("/api/upload", { method: "POST", form: fd });
    },
    uploadRecording: (file, { title, isPrivate } = {}) => {
      const fd = new FormData();
      fd.append("file", file);
      if (title) fd.append("title", title);
      fd.append("private", isPrivate ? "true" : "false");
      return request("/api/upload-recording", { method: "POST", form: fd });
    },
    addSegments: (id, segments) => request(`/api/meetings/${id}/segments`, { method: "POST", body: { segments } }),
    segments: (id, { q, speaker } = {}) => {
      const p = new URLSearchParams();
      if (q) p.set("q", q);
      if (speaker) p.set("speaker", speaker);
      return request(`/api/meetings/${id}/segments?${p}`);
    },
    memory: (id) => request(`/api/meetings/${id}/memory`),
    summary: (id, body) => request(`/api/meetings/${id}/summary`, { method: "POST", body }),
    explain: (id, body) => request(id ? `/api/meetings/${id}/explain` : "/api/explain", { method: "POST", body }),
    ask: (id, body) => request(`/api/meetings/${id}/ask`, { method: "POST", body }),
    segmentTranslations: (id, target, segment_ids) =>
      request(`/api/meetings/${id}/segments/translations`, { method: "POST", body: { target, segment_ids } }),
    translate: (text, target_language) => request("/api/translate", { method: "POST", body: { text, target_language } }),
    speakers: (id) => request(`/api/meetings/${id}/speakers`),
    mapSpeaker: (id, speaker_id, speaker_name) => request(`/api/meetings/${id}/speakers`, { method: "PUT", body: { speaker_id, speaker_name } }),
    decisions: (id) => request(`/api/meetings/${id}/decisions`),
    tasks: (id) => request(`/api/meetings/${id}/tasks`),
    updateTask: (id, taskId, fields) => request(`/api/meetings/${id}/tasks/${taskId}`, { method: "PATCH", body: fields }),
    timeline: (id) => request(`/api/meetings/${id}/timeline`),
    notes: (id) => request(`/api/meetings/${id}/notes`),
    addNote: (id, text, segment_id) => request(`/api/meetings/${id}/notes`, { method: "POST", body: { text, segment_id } }),
    deleteNote: (id, noteId) => request(`/api/meetings/${id}/notes/${noteId}`, { method: "DELETE" }),
    exportFile: (id, format, language) => request(`/api/meetings/${id}/export?format=${format}&language=${encodeURIComponent(language || "en")}`, { raw: true }),
    me: () => request("/api/me"),
    room: (id) => request(`/api/rooms/${id}`),
    roomCatchup: (id, language) => request(`/api/rooms/${id}/catchup?language=${encodeURIComponent(language || "en")}`),
    roomApprove: (id, email) => request(`/api/rooms/${id}/approve`, { method: "POST", body: { email } }),
    importTranscript: (provider, body) => request(`/api/import/${provider}`, { method: "POST", body }),
    searchHistory: (q) => request(`/api/search?q=${encodeURIComponent(q)}`),
  };

  window.MM = { api, config, loadConfig, saveConnection, store, isExtension, ApiError };
})();

/* MeetBrief AI side panel / web app. All transcript-derived text is treated as untrusted and HTML-escaped. */
(function () {
  const { api, config, loadConfig, saveConnection, store, isExtension } = window.MM;
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const LANGUAGES = [
    ["en", "English"], ["hi", "हिन्दी Hindi"], ["te", "తెలుగు Telugu"], ["ta", "தமிழ் Tamil"], ["kn", "ಕನ್ನಡ Kannada"],
    ["ml", "മലയാളം Malayalam"], ["bn", "বাংলা Bengali"], ["mr", "मराठी Marathi"], ["es", "Español"], ["fr", "Français"],
    ["de", "Deutsch"], ["zh", "中文"], ["ja", "日本語"], ["ar", "العربية"],
  ];

  const state = {
    meetingId: null, meetings: [], memory: null, prefs: {}, chat: [], lastExplanation: null,
    capture: { state: "idle", source: null, meetingId: null, tabId: null }, liveTimer: null, health: null,
  };

  // ------------------------------------------------------------- helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtTime = (sec) => {
    if (sec === null || sec === undefined) return "--:--";
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };
  const chips = (html) => html.replace(/\[((?:S\d+-[0-9a-f]{6}(?:,\s*)?)+)\]/g, (_, ids) =>
    ids.split(/,\s*/).map((id) => `<button class="chip" data-seg="${id}" title="Show source">${id.split("-")[0]}</button>`).join(" "));

  function md(text) {
    // minimal, safe markdown: escape first, then format
    const lines = esc(text).split("\n");
    let html = "", list = null;
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    for (let raw of lines) {
      const line = raw.replace(/\s+$/, "");
      let m;
      const inline = (s) => chips(s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/~~(.+?)~~/g, "<s>$1</s>")
        .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<i>$2</i>").replace(/_(.+?)_/g, "<i>$1</i>").replace(/`(.+?)`/g, "<code>$1</code>"));
      if (!line.trim()) { close(); continue; }
      if ((m = line.match(/^\s*#{1,4}\s+(.*)$/)) || (m = line.match(/^\*\*([^*]+)\*\*:?$/))) { close(); html += `<div class="h">${inline(m[1])}</div>`; continue; }
      if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; continue; }
      if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; continue; }
      close(); html += `<p>${inline(line)}</p>`;
    }
    close();
    return html;
  }

  let toastTimer;
  function toast(msg, ms = 3500) {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), ms);
  }
  const loading = (el, msg = "Working…") => { el.hidden = false; el.innerHTML = `<span class="spinner"></span> <span class="muted">${esc(msg)}</span>`; };
  const showError = (el, e) => { el.hidden = false; el.innerHTML = `<div class="note-box">${esc(e.message || e)}</div>`; };
  const needMeeting = (el) => {
    if (state.meetingId) return false;
    el.innerHTML = `<p class="empty">No meeting selected. Upload a transcript or start capture on a supported meeting page.</p>`;
    return true;
  };
  const statusPill = (s) => `<span class="pill ${esc(s)}">${esc(s)}</span>`;

  // ---------------------------------------------------------- navigation
  function activateTab(name) {
    $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
    store.set({ lastTab: name });
    const loaders = { speakers: renderSpeakers, decisions: renderDecisions, actions: renderActions, timeline: renderTimeline,
      transcript: () => renderTranscript(), notes: renderNotes, settings: renderSettings };
    if (loaders[name]) loaders[name]();
  }

  document.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip[data-seg]");
    if (chip) { e.preventDefault(); jumpToSegment(chip.dataset.seg); }
  });

  async function jumpToSegment(segId) {
    activateTab("transcript");
    await renderTranscript();
    const el = document.getElementById(`seg-${segId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("flash");
      setTimeout(() => el.classList.remove("flash"), 2500);
    } else toast("That segment is no longer available.");
  }

  // ------------------------------------------------------------ meetings
  async function loadMeetings(selectId) {
    try {
      state.meetings = await api.meetings();
    } catch (e) {
      // 401 = the server was reached but does not know who this is: that is a sign-in step, not a connection problem
      const signIn = e.status === 401;
      $("#meetingSelect").innerHTML = `<option>${signIn ? "Connected — enter your name in Settings → Account" : "Backend not connected"}</option>`;
      toast(signIn ? "Connected. Now go to Settings → Account, enter your name and email, and press “Use this identity”." : e.message, 8000);
      return;
    }
    const sel = $("#meetingSelect");
    sel.innerHTML = state.meetings.length
      ? state.meetings.map((m) => `<option value="${esc(m.id)}">${m.private ? "🔒 " : ""}${esc(m.title)} (${m.segment_count})</option>`).join("")
      : `<option value="">No meetings yet — upload a transcript</option>`;
    // a remembered meeting may have been deleted (or lives on another backend): fall back to the newest one
    const exists = (id) => id && state.meetings.some((m) => m.id === id);
    const target = [selectId, state.meetingId, state.meetings[0] && state.meetings[0].id].find(exists);
    if (target) { sel.value = target; await selectMeeting(target); }
    else { state.meetingId = null; $("#segmentCount").textContent = ""; }
  }

  async function selectMeeting(id) {
    state.meetingId = id || null;
    state.chat = [];
    renderChat();
    await store.set({ lastMeeting: id });
    await refreshMemory();
    const active = $(".tabs button.active").dataset.tab;
    if (active !== "catchup") activateTab(active);
  }

  async function refreshMemory() {
    if (!state.meetingId) return;
    try {
      const { meeting, memory } = await api.memory(state.meetingId);
      state.memory = memory;
      $("#segmentCount").textContent = `${meeting.segment_count} segments${meeting.private ? " · private" : ""}`;
      const cur = memory.current_topic;
      const ct = $("#currentTopic");
      ct.hidden = !cur;
      if (cur) ct.innerHTML = `Current topic (likely): <b>${esc(cur.label)}</b> <span class="chip" data-seg="${esc(cur.segment_ids[0])}">from ${fmtTime(cur.start_time)}</span>`;
      const sp = $("#askSpeaker"), prev = sp.value;
      sp.innerHTML = `<option value="">All speakers</option>` + memory.participants.map((p) => `<option>${esc(p)}</option>`).join("");
      sp.value = prev;
      $("#suggested").innerHTML = memory.suggested_questions.length
        ? `<span class="muted small">Suggested questions:</span>` + memory.suggested_questions.map((q) => `<button data-q="${esc(q)}">${esc(q)}</button>`).join("")
        : "";
    } catch (e) { toast(e.message); }
  }

  $("#meetingSelect").addEventListener("change", (e) => selectMeeting(e.target.value));
  $("#refreshBtn").addEventListener("click", async () => { await loadMeetings(state.meetingId); activateTab($(".tabs button.active").dataset.tab); });

  $("#uploadInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const isRecording = /\.(mp3|m4a|mp4|wav|webm|ogg|oga|opus|mkv|mov|aac|flac)$/i.test(file.name);
    toast(`Uploading ${file.name}…`, 8000);
    try {
      if (isRecording) {
        const res = await api.uploadRecording(file, { isPrivate: $("#privateUpload").checked });
        await loadMeetings(res.meeting.id);
        activateTab("catchup");
        $("#summaryOut").innerHTML = `<span class="spinner"></span> <span class="muted">Transcribing the recording and separating speakers… this can take a few minutes for a long meeting.</span>`;
        await waitForRecording(res.meeting.id);
      } else {
        const res = await api.upload(file, { isPrivate: $("#privateUpload").checked });
        toast(`Imported ${res.added} segments from ${file.name}`);
        await loadMeetings(res.meeting.id);
        activateTab("catchup");
        generateSummary();
      }
    } catch (err) { toast(`Upload failed: ${err.message}`, 6000); }
    e.target.value = "";
  });

  async function waitForRecording(id) {
    for (let i = 0; i < 720; i++) {  // up to ~1 hour
      await new Promise((r) => setTimeout(r, 5000));
      let m;
      try { m = await api.meeting(id); } catch (_) { continue; }
      if (m.capture_state === "ready") {
        toast(`Recording transcribed: ${m.segment_count} segments`);
        await loadMeetings(id);
        $("#summaryMode").value = "catchup";
        return generateSummary();
      }
      if (String(m.capture_state).startsWith("error")) {
        $("#summaryOut").innerHTML = `<div class="note-box">${esc(m.capture_state)}</div>`;
        return;
      }
    }
  }

  function setLive(on) {
    const box = $("#liveSummary");
    if (box.checked === on) return;
    box.checked = on;
    box.dispatchEvent(new Event("change"));
  }

  // --------------------------------------------------------- catch me up
  $("#summaryMode").addEventListener("change", (e) => { $("#summaryFocus").hidden = e.target.value !== "personalized"; });
  $("#summaryBtn").addEventListener("click", () => generateSummary());
  $("#suggested").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-q]");
    if (!b) return;
    activateTab("ask");
    $("#askInput").value = b.dataset.q;
    $("#askForm").requestSubmit();
  });
  $("#liveSummary").addEventListener("change", (e) => {
    clearInterval(state.liveTimer);
    if (e.target.checked) { generateSummary(true); state.liveTimer = setInterval(() => generateSummary(true), 15000); }
  });

  async function generateSummary(quiet = false) {
    const out = $("#summaryOut");
    if (needMeeting(out)) return;
    if (!quiet) loading(out, "Summarizing…");
    const mins = parseFloat($("#sinceMinutes").value);
    let from_time = null;
    if (!isNaN(mins) && mins > 0) {
      const segs = (await api.segments(state.meetingId)).segments;
      const last = segs.length ? (segs[segs.length - 1].start_time ?? null) : null;
      if (last !== null) from_time = Math.max(0, last - mins * 60);
    }
    try {
      const body = { mode: $("#summaryMode").value, language: $("#summaryLang").value, from_time };
      if (body.mode === "personalized") body.focus = $("#summaryFocus").value;
      const res = await api.summary(state.meetingId, body);
      let html = md(res.summary);
      if (res.note) html = `<div class="note-box">${esc(res.note)}</div>` + html;
      if (res.translation && res.translation.warnings && res.translation.warnings.length)
        html += `<div class="note-box">${res.translation.warnings.map(esc).join("<br>")}</div>`;
      html += `<div class="meta muted small">${esc(res.engine)} · ${res.segments_covered} segments · ${res.latency_ms ?? "?"} ms</div>`;
      out.innerHTML = html;
      if (quiet) refreshMemory();
    } catch (e) { showError(out, e); }
  }

  // ------------------------------------------------------- explain again
  async function doExplain(again = false) {
    const out = $("#explainOut");
    const text = $("#explainText").value.trim();
    if (!text) { toast("Enter or select some text to explain."); return; }
    loading(out, "Explaining…");
    try {
      const res = await api.explain(state.meetingId, {
        text, style: $("#explainStyle").value, difficulty: $("#explainLevel").value, language: $("#explainLang").value,
        previous_explanation: again ? state.lastExplanation : null,
      });
      state.lastExplanation = res.explanation;
      let html = md(res.explanation);
      if (res.translation && res.translation.warnings.length) html += `<div class="note-box">${res.translation.warnings.map(esc).join("<br>")}</div>`;
      html += `<div class="meta muted small">${esc(res.engine)}${res.term ? " · glossary: " + esc(res.term) : ""}</div>`;
      out.innerHTML = html;
      $("#explainAgainBtn").disabled = false;
    } catch (e) { showError(out, e); }
  }
  $("#explainBtn").addEventListener("click", () => doExplain(false));
  $("#explainAgainBtn").addEventListener("click", () => doExplain(true));

  // ------------------------------------------------------------- ask ai
  function renderChat() {
    const box = $("#chat");
    if (!state.chat.length) {
      box.innerHTML = `<p class="empty">Ask anything about the meeting. Answers are grounded in the transcript and cite their sources; if the transcript doesn't say, MeetBrief will tell you.</p>`;
      return;
    }
    box.innerHTML = state.chat.map((m) => {
      if (m.role === "user") return `<div class="msg user">${esc(m.content)}</div>`;
      if (m.pending) return `<div class="msg bot"><span class="spinner"></span></div>`;
      const ev = (m.evidence || []).map((e) => `<div><button class="chip" data-seg="${esc(e.segment_id)}">${esc(e.segment_id.split("-")[0])}</button> ${esc(e.speaker)} · ${fmtTime(e.start_time)}: “${esc(e.text)}”</div>`).join("");
      const conf = m.insufficient ? `<span class="pill warn">insufficient evidence</span>` : `<span class="pill">${esc(m.confidence)} confidence</span>`;
      return `<div class="msg bot">${md(m.content)}${ev ? `<div class="evidence">${ev}</div>` : ""}<div class="meta">${conf} · ${esc(m.engine || "")}</div></div>`;
    }).join("");
    box.scrollTop = box.scrollHeight;
  }

  $("#askForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("#askInput").value.trim();
    if (!q) return;
    if (!state.meetingId) { toast("Select or upload a meeting first."); return; }
    const history = state.chat.filter((m) => !m.pending).map((m) => ({ role: m.role, content: m.content.slice(0, 4000) }));
    state.chat.push({ role: "user", content: q }, { role: "assistant", pending: true, content: "" });
    $("#askInput").value = "";
    renderChat();
    try {
      const res = await api.ask(state.meetingId, { question: q, language: $("#askLang").value, history: history.slice(-10),
        speaker: $("#askSpeaker").value || null });
      state.chat[state.chat.length - 1] = { role: "assistant", content: res.answer, evidence: res.evidence,
        confidence: res.confidence, insufficient: res.insufficient_evidence, engine: res.engine };
    } catch (err) {
      state.chat[state.chat.length - 1] = { role: "assistant", content: `Error: ${err.message}`, evidence: [], confidence: "none", insufficient: true };
    }
    renderChat();
  });
  $("#clearChatBtn").addEventListener("click", () => { state.chat = []; renderChat(); });

  // ------------------------------------------------------ who said what
  async function renderSpeakers() {
    const out = $("#speakersOut");
    if (needMeeting(out)) return;
    loading(out);
    try {
      const { speakers } = await api.speakers(state.meetingId);
      if (!speakers.length) { out.innerHTML = `<p class="empty">No speech captured yet.</p>`; return; }
      out.innerHTML = `<div class="list">` + speakers.map((s) => {
        const pts = s.key_points.map((p) => `<li>${esc(p.text)} <button class="chip" data-seg="${esc(p.segment_id)}">${fmtTime(p.start_time)}</button></li>`).join("");
        const sug = s.suggestions.map((p) => `<li>${esc(p.text)} <button class="chip" data-seg="${esc(p.segment_id)}">${fmtTime(p.start_time)}</button></li>`).join("");
        const decs = s.decisions.filter((d) => d.status !== "proposed").map((d) => `<li>${statusPill(d.status)} ${esc(d.summary)} <button class="chip" data-seg="${esc(d.evidence_segments[0])}">src</button></li>`).join("");
        const owned = s.tasks_owned.map((t) => `<li>${esc(t.task_text)} — ${esc(t.deadline)} <button class="chip" data-seg="${esc(t.evidence_segments[0])}">src</button></li>`).join("");
        const assigned = s.tasks_assigned.map((t) => `<li>${esc(t.task_text)} → ${esc(t.owner)} <button class="chip" data-seg="${esc(t.evidence_segments[0])}">src</button></li>`).join("");
        const qs = s.questions.map((q) => `<li>${esc(q.text)} ${statusPill(q.status)}</li>`).join("");
        const mapper = s.identity_known ? "" :
          `<div class="note-box">${esc(s.identity_note)}<div class="row mt4"><input data-map="${esc(s.speaker_id || s.speaker)}" placeholder="Participant name"><button class="btn small" data-map-btn="${esc(s.speaker_id || s.speaker)}">Map</button></div></div>`;
        return `<div class="item"><div class="speaker-head"><span class="title">${esc(s.speaker)}</span><span class="muted small">${s.segment_count} turns · ${Math.round(s.word_share * 100)}% of words</span></div>
          <div class="bar"><span data-width="${Math.round(s.word_share * 100)}"></span></div>${mapper}
          ${pts ? `<div class="small"><b>Key points</b><ul>${pts}</ul></div>` : ""}
          ${sug ? `<div class="small"><b>Suggestions</b><ul>${sug}</ul></div>` : ""}
          ${decs ? `<div class="small"><b>Decisions made</b><ul>${decs}</ul></div>` : ""}
          ${owned ? `<div class="small"><b>Tasks owned</b><ul>${owned}</ul></div>` : ""}
          ${assigned ? `<div class="small"><b>Tasks assigned to others</b><ul>${assigned}</ul></div>` : ""}
          ${qs ? `<div class="small"><b>Questions asked</b><ul>${qs}</ul></div>` : ""}</div>`;
      }).join("") + `</div>`;
      // widths set through the CSSOM: allowed by a strict CSP, unlike style="" attributes
      out.querySelectorAll("[data-width]").forEach((el) => { el.style.width = `${Number(el.dataset.width) || 0}%`; });
    } catch (e) { showError(out, e); }
  }
  $("#speakersOut").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-map-btn]");
    if (!b) return;
    const id = b.dataset.mapBtn;
    const input = $(`input[data-map="${CSS.escape(id)}"]`);
    if (!input.value.trim()) return;
    try { await api.mapSpeaker(state.meetingId, id, input.value.trim()); toast(`Mapped ${id} → ${input.value.trim()} (user-confirmed)`); renderSpeakers(); refreshMemory(); }
    catch (err) { toast(err.message); }
  });

  // ----------------------------------------------------------- decisions
  async function renderDecisions() {
    const out = $("#decisionsOut");
    if (needMeeting(out)) return;
    loading(out);
    try {
      const d = await api.decisions(state.meetingId);
      const item = (x) => `<div class="item"><div class="top"><span class="title">${esc(x.summary)}</span>${statusPill(x.status)}</div>
        <div class="sub">${esc(x.speaker || "unknown speaker")} · ${fmtTime(x.timestamp)} ${x.topic ? "· " + esc(x.topic) : ""} <button class="chip" data-seg="${esc(x.evidence_segments[0])}">source</button>
        ${x.source === "model" ? `<span class="pill warn" title="Found by the zero-shot NLI model, not by the rules — verify">model-detected</span>` : ""}
        <span class="muted" title="Extraction confidence">conf ${Math.round((x.confidence || 0) * 100)}%</span>
        ${x.supersedes ? `<span class="pill warn">revises an earlier decision</span>` : ""}${x.superseded_by ? `<span class="pill">superseded</span>` : ""}</div></div>`;
      const confirmed = d.decisions.filter((x) => ["confirmed", "uncertain"].includes(x.status));
      const proposed = d.decisions.filter((x) => x.status === "proposed");
      const superseded = d.decisions.filter((x) => x.status === "superseded");
      const open = d.open_questions.filter((q) => q.status !== "answered");
      let html = `<h3>Confirmed decisions</h3>` + (confirmed.length ? `<div class="list">${confirmed.map(item).join("")}</div>` : `<p class="empty">None identified.</p>`);
      if (d.changes.length) html += `<h3>Decision changes</h3><div class="list">` + d.changes.map((c) =>
        `<div class="item"><div><s>${esc(c.from)}</s> → <b>${esc(c.to)}</b></div><div class="sub">${c.evidence_segments.map((s) => `<button class="chip" data-seg="${esc(s)}">${esc(s.split("-")[0])}</button>`).join(" ")}</div></div>`).join("") + `</div>`;
      if (superseded.length) html += `<h3>Superseded (history kept)</h3><div class="list">${superseded.map(item).join("")}</div>`;
      html += `<h3>Proposals / options discussed</h3>` + (proposed.length ? `<div class="list">${proposed.map(item).join("")}</div>` : `<p class="empty">None.</p>`);
      html += `<h3>Unresolved questions</h3>` + (open.length ? `<div class="list">${open.map((q) =>
        `<div class="item"><div class="top"><span>${esc(q.text)}</span>${statusPill(q.status)}</div><div class="sub">${esc(q.asked_by || "unknown")} · ${fmtTime(q.timestamp)} <button class="chip" data-seg="${esc(q.evidence_segments[0])}">source</button></div></div>`).join("")}</div>` : `<p class="empty">None detected.</p>`);
      const conflicts = d.contradictions.filter((c) => c.kind === "potential_contradiction");
      if (conflicts.length) html += `<h3>Potential contradictions (verify)</h3><div class="list">` + conflicts.map((c) =>
        `<div class="item"><div class="small">${esc(c.description)}</div><div class="sub">${c.evidence_segments.map((s) => `<button class="chip" data-seg="${esc(s)}">${esc(s.split("-")[0])}</button>`).join(" ")}</div></div>`).join("") + `</div>`;
      out.innerHTML = html;
    } catch (e) { showError(out, e); }
  }

  // --------------------------------------------------------- action items
  async function renderActions() {
    const out = $("#actionsOut");
    if (needMeeting(out)) return;
    loading(out);
    try {
      const { tasks } = await api.tasks(state.meetingId);
      if (!tasks.length) { out.innerHTML = `<p class="empty">No action items identified yet.</p>`; return; }
      out.innerHTML = `<div class="list">` + tasks.map((t) => {
        const warn = [t.owner === "unknown" ? "owner not stated" : "", t.deadline === "unspecified" ? "deadline not stated" : ""].filter(Boolean);
        return `<div class="item ${t.status === "completed" ? "done" : ""}" data-task="${esc(t.task_id)}">
          <div class="top"><label class="check"><input type="checkbox" data-done ${t.status === "completed" ? "checked" : ""}> <span class="title">${esc(t.task_text)}</span></label>${statusPill(t.status)}</div>
          <div class="sub">Owner: <b>${esc(t.owner)}</b>${t.owner_source === "user" ? " (edited)" : ""} · Deadline: <b>${esc(t.deadline)}</b> · by ${esc(t.assigned_by || "unknown")} <button class="chip" data-seg="${esc(t.evidence_segments[0])}">source</button></div>
          ${warn.length ? `<div class="warn-text">⚠ ${warn.join(", ")} in the transcript</div>` : ""}
          ${(t.flags || []).includes("owner_not_verified") ? `<div class="warn-text">⚠ “${esc(t.owner)}” is not a known participant or recognised person — verify the owner</div>` : ""}
          ${(t.flags || []).includes("owner_identity_unknown") ? `<div class="warn-text">⚠ owner is a generic speaker label — map it in Who Said What?</div>` : ""}
          ${(t.flags || []).filter((f) => f.startsWith("confirmed_by:")).map((f) => `<div class="muted small">✓ confirmed by ${esc(f.slice(13))} — that speaker may be ${esc(t.owner)}; map it in Who Said What? if so</div>`).join("")}
          <div class="row"><input data-owner placeholder="Correct owner" value=""><input data-deadline placeholder="Correct deadline"><button class="btn small" data-save>Save</button></div></div>`;
      }).join("") + `</div>`;
    } catch (e) { showError(out, e); }
  }
  $("#actionsOut").addEventListener("change", async (e) => {
    if (!e.target.matches("[data-done]")) return;
    const id = e.target.closest("[data-task]").dataset.task;
    try { await api.updateTask(state.meetingId, id, { status: e.target.checked ? "completed" : "open" }); renderActions(); }
    catch (err) { toast(err.message); }
  });
  $("#actionsOut").addEventListener("click", async (e) => {
    if (!e.target.matches("[data-save]")) return;
    const box = e.target.closest("[data-task]");
    const owner = box.querySelector("[data-owner]").value.trim(), deadline = box.querySelector("[data-deadline]").value.trim();
    if (!owner && !deadline) return;
    try { await api.updateTask(state.meetingId, box.dataset.task, { owner: owner || null, deadline: deadline || null }); toast("Task corrected"); renderActions(); }
    catch (err) { toast(err.message); }
  });

  // ------------------------------------------------------------ timeline
  async function renderTimeline() {
    const out = $("#timelineOut");
    if (needMeeting(out)) return;
    loading(out);
    try {
      const { events } = await api.timeline(state.meetingId);
      if (!events.length) { out.innerHTML = `<p class="empty">Nothing yet.</p>`; return; }
      const label = { topic: "Topic", decision: "Decision", task: "Task", question: "Question" };
      const ents = (state.memory && state.memory.entities) || [];
      const types = (state.memory && state.memory.entity_types) || {};
      const entHtml = ents.length ? `<div class="suggested"><span class="muted small">Mentioned (NER):</span>${ents.map((e) =>
        `<span class="pill" title="${esc(types[e] || "")}">${esc(e)}${types[e] ? " · " + esc(types[e]) : ""}</span>`).join("")}</div>` : "";
      out.innerHTML = entHtml + `<p class="muted small">Topic boundaries are likely shifts in discussion, not decisions.</p><div class="timeline">` + events.map((ev) =>
        `<div class="tl ${ev.type}"><span class="time">${fmtTime(ev.time)}</span>${ev.type === "topic" ? esc(ev.label) : `<b>${label[ev.type]}</b> ${ev.type === "task" ? "(" + esc(ev.label) + ") " : ev.type !== "topic" ? statusPill(ev.label) + " " : ""}${esc(ev.text)}`}
          <button class="chip" data-seg="${esc(ev.segment_id)}">src</button></div>`).join("") + `</div>`;
    } catch (e) { showError(out, e); }
  }

  // ---------------------------------------------------------- transcript
  // Every viewer reads the transcript in their own language ("Read in", remembered per browser). Lines spoken in
  // another language are shown translated, tagged "Translated from <language>", with the original underneath.
  const LANG_NAME = Object.fromEntries(LANGUAGES.map(([c, n]) => [c, n.split(" ").pop()]));
  const langName = (c) => LANG_NAME[(c || "").split("-")[0]] || c;
  const readLang = () => $("#transLang").value || "en";
  async function renderTranscript(query) {
    const out = $("#transcriptOut");
    if (needMeeting(out)) return;
    try {
      const res = await api.segments(state.meetingId, { q: query });
      const segs = res.segments;
      if (!segs.length) { out.innerHTML = `<p class="empty">${query ? "No matching passages." : "No transcript yet."}</p>`; return; }
      let trs = {};
      try {
        const ids = segs.map((s) => s.segment_id).filter(Boolean).slice(-300);
        trs = (await api.segmentTranslations(state.meetingId, readLang(), ids)).translations || {};
      } catch (_) { /* translation is a convenience: show the transcript as spoken */ }
      const showOrig = $("#showOriginal").checked;
      out.innerHTML = (res.semantic ? `<p class="muted small">Top passages by meaning for “${esc(query)}”</p>` : "") + segs.map((s) => {
        const unknown = !s.speaker_name;
        const who = s.speaker_name || s.speaker_id || s.speaker || "Unknown speaker";
        const spoken = s.original_text || s.text;  // the words as said (s.text is the English when original_text is set)
        const onlyEnglish = (s.flags || []).includes("original_unavailable");
        const tr = trs[s.segment_id];
        let body;
        if (tr && tr.text) {
          body = `<div>${esc(tr.text)}</div>` + (showOrig && !onlyEnglish ? `<div class="orig">${esc(spoken)}</div>` : "");
        } else {
          body = `<div>${esc(spoken)}</div>` + (tr && tr.error ? `<div class="orig">⚠ ${esc(tr.error)}</div>` : "");
        }
        const tag = tr && tr.text ? `<span class="trtag" title="${esc(tr.engine || "")}">Translated from ${esc(tr.from_name || langName(tr.from))}</span>`
          : (s.language ? `<span class="lang">${esc(langName(s.language))}</span>` : "");
        return `<div class="seg" id="seg-${esc(s.segment_id)}" data-text="${esc(spoken)}"><span class="t">${fmtTime(s.start_time)}</span>
          <div><span class="who ${unknown && !s.speaker ? "unknown" : ""}">${esc(who)}</span>${tag}
          ${(s.flags || []).includes("code_switched") ? `<span class="lang">mixed</span>` : ""}${s.score ? `<span class="lang">score ${s.score}</span>` : ""}
          <span class="actions"><a data-explain>explain</a><a data-note="${esc(s.segment_id)}">note</a></span>
          ${body}</div></div>`;
      }).join("");
    } catch (e) { showError(out, e); }
  }
  $("#transLang").addEventListener("change", () => {
    try { localStorage.setItem("meetbrief.readLang", readLang()); } catch (_) {}
    renderTranscript();
  });
  $("#showOriginal").addEventListener("change", () => renderTranscript());
  let transcriptTimer = null;
  const refreshTranscriptSoon = () => {  // live meeting: keep the open transcript current
    if (!$("#view-transcript").classList.contains("active") || $("#searchInput").value.trim()) return;
    clearTimeout(transcriptTimer);
    transcriptTimer = setTimeout(() => renderTranscript(), 1500);
  };
  $("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); renderTranscript($("#searchInput").value.trim() || undefined); });
  $("#transcriptOut").addEventListener("click", async (e) => {
    const seg = e.target.closest(".seg");
    if (!seg) return;
    if (e.target.matches("[data-explain]")) { $("#explainText").value = seg.dataset.text; activateTab("explain"); doExplain(); }
    if (e.target.matches("[data-note]")) {
      const text = prompt("Personal note for this segment:");
      if (text) { await api.addNote(state.meetingId, text, e.target.dataset.note); toast("Note saved"); }
    }
  });

  // --------------------------------------------------------------- notes
  async function renderNotes() {
    const out = $("#notesOut");
    if (needMeeting(out)) return;
    try {
      const notes = await api.notes(state.meetingId);
      out.innerHTML = notes.length ? `<div class="list">` + notes.map((n) =>
        `<div class="item"><div class="top"><span>${esc(n.text)}</span><button class="btn small danger" data-del="${esc(n.id)}">✕</button></div>
         ${n.segment_id ? `<div class="sub"><button class="chip" data-seg="${esc(n.segment_id)}">linked segment</button></div>` : ""}</div>`).join("") + `</div>`
        : `<p class="empty">No notes yet.</p>`;
    } catch (e) { showError(out, e); }
  }
  $("#noteForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#noteInput").value.trim();
    if (!text || !state.meetingId) return;
    await api.addNote(state.meetingId, text, null);
    $("#noteInput").value = "";
    renderNotes();
  });
  $("#notesOut").addEventListener("click", async (e) => {
    const id = e.target.dataset.del;
    if (id) { await api.deleteNote(state.meetingId, id); renderNotes(); }
  });
  $$(".export").forEach((b) => b.addEventListener("click", async () => {
    if (!state.meetingId) return toast("Select a meeting first.");
    try {
      const res = await api.exportFile(state.meetingId, b.dataset.format, $("#summaryLang").value);
      const blob = await res.blob();
      const name = (res.headers.get("Content-Disposition") || "").match(/filename="(.+?)"/);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name ? name[1] : `meeting.${b.dataset.format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (err) { toast(`Export failed: ${err.message}`); }
  }));
  $("#historyForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("#historyInput").value.trim();
    if (q.length < 2) return;
    const out = $("#historyOut");
    try {
      const rows = await api.searchHistory(q);
      out.innerHTML = rows.length ? `<div class="list">` + rows.map((r) =>
        `<div class="item small"><div class="sub"><b>${esc(r.title)}</b> · ${esc(r.speaker_name || r.speaker_id || "unknown")} · ${fmtTime(r.start_time)}</div><div>${esc(r.text)}</div>
        <div><button class="btn small" data-open="${esc(r.meeting_id)}" data-seg-open="${esc(r.segment_id)}">Open</button></div></div>`).join("") + `</div>` : `<p class="empty">No matches.</p>`;
    } catch (err) { showError(out, err); }
  });
  $("#historyOut").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-open]");
    if (!b) return;
    $("#meetingSelect").value = b.dataset.open;
    await selectMeeting(b.dataset.open);
    jumpToSegment(b.dataset.segOpen);
  });

  // ------------------------------------------------------------ settings
  async function renderSettings() {
    $("#apiBase").value = config.apiBase;
    $("#apiToken").value = config.token;
    $("#apiBaseField").hidden = $("#tokenField").hidden = !isExtension;
    try {
      const prefs = await api.prefs();
      state.prefs = prefs;
      $("#prefSummaryLang").value = prefs.summary_language;
      $("#prefExplainLang").value = prefs.explanation_language;
      $("#prefDetail").value = prefs.detail_level;
      $("#prefDifficulty").value = prefs.difficulty;
      $("#prefRetention").value = prefs.retention_days;
      $("#prefPrivate").checked = !!prefs.private_mode_default;
      $("#prefAuto").checked = !!prefs.auto_capture;
      $("#prefAutoShare").checked = !!prefs.auto_share;
      renderAccount();
      $("#prefAutoCC").checked = prefs.auto_enable_captions !== false;
      $("#prefAudioBackup").checked = prefs.audio_backup !== false;
      const p = await api.privacy();
      $("#consentOut").innerHTML = `<b>Capture &amp; consent</b><p>${esc(p.summary)}</p><ul>${p.points.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        <p class="muted">All processing is local to your machine — no external AI service is used.</p>`;
      const h = await api.health();
      const rows = Object.entries(h.models.tasks || {}).map(([task, t]) =>
        `<tr><td>${esc(t.label)}</td><td><code>${esc(t.model)}</code></td><td>${t.error ? "⚠ error" : t.loaded ? "loaded" : t.downloaded ? "downloaded" : "not downloaded"}</td></tr>`).join("");
      $("#modelsOut").innerHTML = `<table class="models"><tr><th>Task</th><th>Hugging Face model</th><th>Status</th></tr>${rows}
        <tr><td>Speech recognition</td><td><code>faster-whisper ${esc((h.asr && h.asr.model) || "")}</code></td><td>${h.asr.available ? "available" : "not installed"}</td></tr></table>
        <p class="muted small">Device: ${esc(h.models.device || "-")}. ${h.models.enabled ? "" : esc(h.models.reason || "")} Download all with <code>python -m backend.hf.download</code>.</p>`;
      $("#healthOut").textContent = JSON.stringify(h, null, 2);
    } catch (e) { $("#healthOut").textContent = e.message; }
  }
  $("#signInBtn").addEventListener("click", async () => {
    try { await MMIdentity.signIn(); toast("Signed in"); } catch (e) { toast(e.message, 6000); }
    renderAccount();
  });
  $("#signOutBtn").addEventListener("click", async () => { await MMIdentity.signOut(); renderAccount(); });
  $("#devSave").addEventListener("click", async () => {
    const name = $("#devName").value.trim(), email = $("#devEmail").value.trim();
    if (!name || !/^[^@\s]+@[^@\s]+$/.test(email)) { toast("Enter a name and a valid email"); return; }
    await store.set({ devName: name, devEmail: email });
    await renderAccount();
    await loadMeetings();  // connects straight away, no refresh needed
    toast(`Saved. You are ${name}.`);
  });

  // import the platform's official transcript
  $("#importProvider").addEventListener("change", (e) => { $("#importTokenField").hidden = e.target.value === "google_meet"; });
  $("#importBtn").addEventListener("click", async () => {
    const provider = $("#importProvider").value, ref = $("#importRef").value.trim();
    const status = $("#importStatus");
    if (!ref) { status.textContent = "Enter the meeting link"; return; }
    let token = $("#importToken").value.trim();
    if (provider === "google_meet") {
      if (!isExtension || !window.MMIdentity) { status.textContent = "Google import needs the Chrome extension"; return; }
      token = await MMIdentity.googleToken({ interactive: true, scopes: ["https://www.googleapis.com/auth/meetings.space.readonly"] });
      if (!token) { status.textContent = "Google sign-in is not configured or was cancelled"; return; }
    }
    if (!token) { status.textContent = "Paste an access token"; return; }
    status.textContent = "Importing…";
    try {
      const res = await api.importTranscript(provider, { meeting_ref: ref, access_token: token, meeting_id: state.meetingId || null });
      $("#importToken").value = "";
      status.textContent = `Imported ${res.added} lines ✓`;
      await loadMeetings(res.meeting.id);
      activateTab("catchup");
      $("#summaryMode").value = "catchup";
      generateSummary();
    } catch (e) { status.textContent = e.message; }
  });

  $("#saveConn").addEventListener("click", async () => {
    await saveConnection($("#apiBase").value.trim(), $("#apiToken").value.trim());
    try { await api.meetings(); $("#connStatus").textContent = "Connected ✓"; await init(true); }
    catch (e) { $("#connStatus").textContent = e.message; }
  });
  $("#savePrefs").addEventListener("click", async () => {
    try {
      state.prefs = await api.savePrefs({
        summary_language: $("#prefSummaryLang").value, explanation_language: $("#prefExplainLang").value,
        detail_level: $("#prefDetail").value, difficulty: $("#prefDifficulty").value,
        retention_days: parseInt($("#prefRetention").value || "0", 10), private_mode_default: $("#prefPrivate").checked,
        auto_capture: $("#prefAuto").checked, auto_enable_captions: $("#prefAutoCC").checked,
        audio_backup: $("#prefAudioBackup").checked,
        auto_share: $("#prefAutoShare").checked,
        ...($("#prefAuto").checked ? { consent_acknowledged: true } : {}),
      });
      applyPrefs();
      $("#prefsStatus").textContent = "Saved ✓";
    } catch (e) { $("#prefsStatus").textContent = e.message; }
  });
  $("#deleteTranscriptBtn").addEventListener("click", async () => {
    if (!state.meetingId || !confirm("Delete this meeting's transcript and derived memory? Notes are kept.")) return;
    await api.deleteTranscript(state.meetingId); toast("Transcript deleted"); loadMeetings(state.meetingId);
  });
  $("#deleteMeetingBtn").addEventListener("click", async () => {
    if (!state.meetingId || !confirm("Permanently delete this meeting, its transcript and notes?")) return;
    await api.deleteMeeting(state.meetingId); state.meetingId = null; toast("Meeting deleted"); loadMeetings();
  });
  $("#deleteAllBtn").addEventListener("click", async () => {
    if (!confirm("Permanently delete ALL meetings and notes stored by MeetBrief?")) return;
    const r = await api.deleteAll(); state.meetingId = null; toast(`Deleted ${r.deleted_meetings} meetings`); loadMeetings();
  });

  async function renderAccount() {
    if (!isExtension || !window.MMIdentity) {
      $("#accountOut").textContent = "Shared rooms need the Chrome extension.";
      $("#redirectUri").parentElement.hidden = true;           // extension-only settings mean nothing in the web app
      $("#prefAutoShare").closest("label").hidden = true;
      return;
    }
    const info = await MMIdentity.serverInfo(true);
    $("#redirectUri").textContent = MMIdentity.redirectUrl();
    $("#googleRow").hidden = !info.google_client_id;
    $("#devRow").hidden = !info.dev_identities;
    let me = null;
    try { me = await api.me(); } catch (_) { /* not signed in */ }
    state.signedIn = !!(me && me.email);
    if (!info.google_client_id && !info.dev_identities) {
      $("#accountOut").innerHTML = `Shared rooms are <b>off</b> on this server. To enable them, start it with
        <code>MEETBRIEF_GOOGLE_CLIENT_ID</code> (see docs/ROOMS.md).`;
    } else {
      $("#accountOut").innerHTML = state.signedIn
        ? `Signed in as <b>${esc(me.name)}</b> (${esc(me.email)})${me.verified ? " ✓ Google" : " · test identity"}`
        : "Not signed in — sign in so MeetBrief can recognise you in shared rooms.";
    }
    renderRoom(state.capture);
  }

  function applyPrefs() {
    const p = state.prefs;
    if (!p) return;
    $("#summaryLang").value = p.summary_language || "en";
    $("#askLang").value = p.summary_language || "en";
    $("#explainLang").value = p.explanation_language || "en";
    $("#explainLevel").value = p.difficulty || "beginner";
    if (["quick", "catchup", "detailed"].includes(p.detail_level)) $("#summaryMode").value = p.detail_level;
    $("#privateUpload").checked = !!p.private_mode_default;
  }

  // ------------------------------------------------------- live capture
  const CAPTURE_TEXT = {
    idle: "Not capturing", waiting_authorization: "Waiting for authorization", capturing_captions: "Capturing captions",
    capturing_audio: "Processing tab audio", paused: "Paused", stopped: "Stopped", no_captions: "Captions not found",
    unsupported: "Not a supported meeting page", error: "Capture error", ended: "Meeting ended — final summary ready",
    room_standby: "Following the shared room",
  };
  function renderCapture(c) {
    state.capture = c || state.capture;
    const s = state.capture.state || "idle";
    const dot = $("#captureDot");
    dot.className = "dot " + (s.startsWith("capturing") ? "active" : s === "paused" ? "paused" : s === "waiting_authorization" ? "waiting" : "idle");
    $("#captureText").textContent = (CAPTURE_TEXT[s] || s) + (state.capture.audioBackup && (s.startsWith("capturing") || s === "no_captions") ? " — using tab audio" : "")
      + (state.capture.auto && s.startsWith("capturing") ? " (automatic)" : "");
    $("#captureSource").textContent = [state.capture.detail || (state.capture.platform ? `on ${state.capture.platform}` : ""),
      state.capture.audioBackup && state.capture.audioDetail ? state.capture.audioDetail : ""].filter(Boolean).join(" · ");
    const active = s.startsWith("capturing"), paused = s === "paused";
    $("#startCaptionsBtn").hidden = active || paused;
    $("#pauseBtn").hidden = !active;
    $("#resumeBtn").hidden = !paused;
    $("#stopBtn").hidden = !(active || paused);
    const cs = state.capture;
    $("#addAudioBtn").hidden = !((active || s === "no_captions") && cs.mode !== "audio" && !cs.audioBackup
      && !(state.prefs && state.prefs.audio_backup === false) && !(cs.room && cs.room.role !== "capturer"));
    renderRoom(state.capture);
  }

  // ------------------------------------------------------------- rooms
  function renderRoom(c) {
    const r = c && c.room;
    const banner = $("#roomBanner");
    banner.hidden = !r;
    const inCall = c && !["ended", "unsupported", "idle"].includes(c.state);
    $("#shareRoomBtn").hidden = !!r || !isExtension || !state.signedIn || !(c && (c.inCall || String(c.state).startsWith("capturing") || c.state === "no_captions"));
    if (!r) return;
    $("#roomTitle").textContent = r.title || "Shared room";
    $("#roomMeta").textContent = r.role === "pending" ? "waiting for approval" : `shared by ${r.sharedBy || "?"} · ${r.members || 1} member${r.members === 1 ? "" : "s"}`;
    $("#roomCapturer").textContent = r.role === "capturer" ? "You are capturing for the room" : r.capturer ? `${r.capturer} is capturing` : "";
    $("#roomEndBtn").hidden = !r.sharer || !inCall;
    $("#roomCatchupBtn").hidden = r.role === "pending";
  }

  async function showRoomCatchup(roomId) {
    const out = $("#summaryOut");
    activateTab("catchup");
    loading(out, "Building your catch-up…");
    try {
      const res = await api.roomCatchup(roomId, $("#summaryLang").value);
      out.innerHTML = `<div class="note-box">${esc(res.note)}</div>` + md(res.summary) +
        `<div class="meta muted small">${esc(res.engine)} · shared by ${esc(res.room.shared_by)}</div>`;
    } catch (e) { showError(out, e); }
  }

  function initExtensionCapture() {
    if (!isExtension) { $("#captureText").textContent = "Web app mode — upload a transcript (live capture needs the Chrome extension)"; return; }
    $("#liveControls").hidden = false;
    const send = (type, extra = {}) => chrome.runtime.sendMessage({ type, ...extra });
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "capture:state") {
        const prev = state.capture.state;
        renderCapture(msg.state);
        if (msg.state.meetingId && msg.state.meetingId !== state.meetingId) loadMeetings(msg.state.meetingId);
        const r = msg.state.room;
        if (r && r.id && r.role !== "pending" && state.shownCatchup !== r.id) {
          state.shownCatchup = r.id;
          if (r.missed > 60) { setLive(false); showRoomCatchup(r.id); return; }
        }
        // capture just started → keep a live catch-up running in the panel
        if (String(msg.state.state).startsWith("capturing") && !String(prev).startsWith("capturing")) {
          $("#summaryMode").value = "catchup";
          activateTab("catchup");
          setLive(true);
        }
        if (["stopped", "ended"].includes(msg.state.state)) setLive(false);
      }
      if (msg.type === "meeting:finalized") {
        setLive(false);
        if (msg.meetingId !== state.meetingId) loadMeetings(msg.meetingId);
        activateTab("catchup");
        $("#summaryMode").value = "catchup";
        if (msg.result && msg.result.summary) {
          $("#summaryOut").innerHTML = `<div class="note-box">Meeting ended — final recap</div>` + md(msg.result.summary);
        } else generateSummary();
        toast("Meeting ended — final summary ready", 6000);
      }
      if (msg.type === "segments:added" && msg.meetingId === state.meetingId) { refreshMemory(); refreshTranscriptSoon(); }
    });
    send("capture:get").then((c) => {
      if (!c) return;
      renderCapture(c);
      // panel opened during an ongoing capture (e.g. from the notification): show the live recap
      if (String(c.state).startsWith("capturing")) {
        if (c.meetingId) loadMeetings(c.meetingId);
        $("#summaryMode").value = "catchup";
        activateTab("catchup");
        setLive(true);
      }
    });
    const consentOk = async () => {
      if (state.prefs.consent_acknowledged) return true;
      const ok = confirm("Before capturing: make sure you are allowed to capture this meeting and that participants are informed. " +
        "MeetBrief processes captions (or tab audio if you choose it) of this tab only. Continue?");
      if (ok) {
        const auto = confirm("Turn on automatic mode? MeetBrief will start capturing captions whenever you join a Google Meet call " +
          "(switching Meet captions on if needed) and stop with a final summary when you leave. You can change this in Settings.");
        state.prefs = await api.savePrefs({ consent_acknowledged: true, auto_capture: auto });
      }
      return ok;
    };
    // Chrome hands out a tab-audio stream only in direct response to a click in an extension page, so the stream
    // is requested first thing in the click handler (before any dialog or network call), then passed on.
    const grabTabAudio = () => new Promise((resolve) => {
      try {
        chrome.tabCapture.getMediaStreamId({}, (id) =>
          resolve(chrome.runtime.lastError || !id ? { error: (chrome.runtime.lastError || {}).message || "no stream" } : { streamId: id }));
      } catch (e) { resolve({ error: String(e.message || e) }); }
    });
    const audioWanted = () => !state.prefs || state.prefs.audio_backup !== false;
    $("#startCaptionsBtn").addEventListener("click", async () => {
      const audio = audioWanted() ? grabTabAudio() : Promise.resolve({});
      if (!(await consentOk())) return;
      const a = await audio;
      const r = await send("capture:start", { mode: "captions", private: $("#privateUpload").checked, language: $("#summaryLang").value,
        streamId: a.streamId, audioError: a.error });
      if (r && r.error) toast(r.error, 6000);
      else if (audioWanted() && !(await send("capture:get")).audioBackup) toast("Captions started, tab audio not yet. " + AUDIO_HOW, 12000);
      else toast(audioWanted() ? "Capturing captions + tab audio" : "Capturing captions (tab audio is off in Settings)");
    });
    const AUDIO_HOW = "Chrome only allows tab audio after you click the MeetBrief icon in the toolbar (pin it from the puzzle-piece menu), "
      + "press Alt+Shift+A, or right-click the meeting page → “Add tab audio to MeetBrief”. Do one of those once on the Meet tab.";
    $("#addAudioBtn").addEventListener("click", async () => {
      const a = await grabTabAudio();
      // no stream from the panel → the background may still have the grant (icon clicked earlier on this tab)
      const r = await send("audio:backup", a.streamId ? { streamId: a.streamId } : {});
      if (r && r.error) toast(AUDIO_HOW, 12000); else toast("Tab audio added — Whisper fills in what captions miss");
    });
    $("#shareRoomBtn").addEventListener("click", async () => {
      const r = await send("room:share");
      if (r && r.error) toast(r.error, 6000); else toast("Meeting shared — late joiners will get everything from now on");
    });
    $("#roomEndBtn").addEventListener("click", async () => {
      if (!confirm("End the room for everyone? Capture stops and the final summary is built.")) return;
      const r = await send("room:end");
      if (r && r.error) toast(r.error, 6000); else { toast("Room ended"); if (r.summary) $("#summaryOut").innerHTML = md(r.summary); }
    });
    $("#roomCatchupBtn").addEventListener("click", () => state.capture.room && showRoomCatchup(state.capture.room.id));

    // Schedule (Early Join)
    const renderSchedules = (list) => {
      $("#schedList").innerHTML = list.length ? list.map((s) =>
        `<div class="item"><div class="top"><span class="title">${esc(s.title)}</span><button class="btn small danger" data-sched="${esc(s.id)}">✕</button></div>
         <div class="sub">${esc(new Date(s.start).toLocaleString())} · ${esc(s.platform)}${s.autoShare ? " · shared room" : ""}</div></div>`).join("")
        : `<p class="empty">No meetings scheduled.</p>`;
    };
    const loadSchedules = async () => renderSchedules((await send("schedule:list")).schedules || []);
    $("#schedAdd").addEventListener("click", async () => {
      const start = new Date($("#schedStart").value).getTime();
      const r = await send("schedule:add", { url: $("#schedUrl").value.trim(), title: $("#schedTitle").value.trim(), start,
        autoShare: $("#schedShare").checked });
      if (r.error) { $("#schedStatus").textContent = r.error; return; }
      $("#schedStatus").textContent = "Scheduled ✓ — MeetBrief will join 1 minute early";
      renderSchedules(r.schedules);
    });
    $("#schedList").addEventListener("click", async (e) => {
      const id = e.target.dataset.sched;
      if (id) renderSchedules((await send("schedule:remove", { id })).schedules || []);
    });
    loadSchedules();

    $("#pauseBtn").addEventListener("click", () => send("capture:pause"));
    $("#resumeBtn").addEventListener("click", () => send("capture:resume"));
    $("#stopBtn").addEventListener("click", () => send("capture:stop"));

    // Explain Again requested from the page context menu
    const takePending = async () => {
      const { pendingExplain } = await chrome.storage.session.get("pendingExplain");
      if (pendingExplain) {
        await chrome.storage.session.remove("pendingExplain");
        $("#explainText").value = pendingExplain;
        activateTab("explain");
        doExplain();
      }
    };
    chrome.storage.onChanged.addListener((changes, area) => { if (area === "session" && changes.pendingExplain && changes.pendingExplain.newValue) takePending(); });
    takePending();
  }

  // ---------------------------------------------------------------- init
  async function init(reload = false) {
    await loadConfig();
    $$(".lang-select").forEach((sel) => { sel.innerHTML = LANGUAGES.map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join(""); });
    try { const saved = localStorage.getItem("meetbrief.readLang"); if (saved) $("#transLang").value = saved; } catch (_) {}
    try {
      state.health = await api.health();
      const m = state.health.models;
      const ready = Object.values(m.tasks || {}).filter((t) => t.enabled && t.downloaded).length;
      const total = Object.keys(m.tasks || {}).length;
      const badge = $("#engineBadge");
      badge.textContent = m.enabled ? `HF models ${ready}/${total}` : "Rules only";
      badge.className = "badge " + (m.enabled && ready ? "ok" : "muted");
      badge.title = m.enabled ? "Local Hugging Face models (no external API)" : String(m.reason || "");
      state.prefs = await api.prefs();
      applyPrefs();
    } catch (e) {
      $("#engineBadge").textContent = "offline";
      toast(e.status === 401 ? "Backend token missing/invalid — set it in Settings." : e.message, 7000);
      if (!reload) activateTab("settings");
      return;
    }
    const { lastMeeting, lastTab } = await store.get(["lastMeeting", "lastTab"]);
    await loadMeetings(lastMeeting);
    if (!reload) {
      $$(".tabs button").forEach((b) => b.addEventListener("click", () => activateTab(b.dataset.tab)));
      initExtensionCapture();
      if (isExtension) renderAccount();
      renderChat();
      if (lastTab && lastTab !== "settings") activateTab(lastTab);
    }
  }

  // tab buttons must work even if init fails early
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => { if (!state.health) activateTab(b.dataset.tab); }));
  init();
})();

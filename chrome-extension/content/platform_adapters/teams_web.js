/* Microsoft Teams web adapter (experimental). Reads live captions when turned on. */
(function () {
  const A = window.MeetBriefAdapters;
  A.register({
    id: "teams_web",
    name: "Microsoft Teams (web)",
    experimental: true,
    matches: (loc) => loc.hostname === "teams.microsoft.com" || loc.hostname === "teams.live.com",
    isInMeeting: () => !!document.querySelector('[data-tid="call-hangup"], #hangup-button, [data-tid="hangup-main-btn"]'),
    meetingTitle: () => A.clean((document.querySelector('[data-tid="call-title"], [data-tid="meeting-title"]') || {}).innerText) || "Teams meeting",
    // The meeting thread id is in the join link; Teams changes the URL once in the call, so remember it.
    meetingKey: () => {
      const decoded = decodeURIComponent(window.location.href);
      const m = decoded.match(/(19:meeting_[A-Za-z0-9_-]+@thread\.v2)/);
      try {
        if (m) sessionStorage.setItem("meetbrief_teams_key", m[1]);
        const saved = m ? m[1] : sessionStorage.getItem("meetbrief_teams_key");
        return saved ? `teams_web:${saved.replace(/[^\w\-.@]/g, "_").slice(0, 110)}` : null;
      } catch (_) { return m ? `teams_web:${m[1].replace(/[^\w\-.@]/g, "_").slice(0, 110)}` : null; }
    },
    autoJoin() {
      const cont = A.findButton(/continue on this browser|use the web app instead/i);
      if (cont) { cont.click(); return false; }
      for (const rx of [/mute microphone|turn off microphone/i, /turn camera off|turn off camera/i]) { const b = A.findButton(rx); if (b) b.click(); }
      const join = A.findButton(/^\s*join now\s*$/i);
      if (join) { join.click(); return true; }
      return false;
    },
    captionsHint: "In Teams, choose More → Language and speech → Turn on live captions.",
    findCaptionRoot: () => A.query(document, ['[data-tid="closed-caption-v2-window-wrapper"]', '[data-tid="closed-captions-renderer"]', ".ui-chat"]),
    readCaptions(root) {
      const items = A.queryAll(root, ['[data-tid="closed-caption-message"]', ".fui-ChatMessageCompact", ".ui-chat__item"]);
      return items.map((it) => ({
        key: A.nodeKey(it),
        speaker: A.clean((it.querySelector('[data-tid="author"], .ui-chat__message__author') || {}).innerText) || null,
        text: A.clean((it.querySelector('[data-tid="closed-caption-text"], .ui-chat__message__content') || it).innerText),
      })).filter((c) => c.text);
    },
  });
})();

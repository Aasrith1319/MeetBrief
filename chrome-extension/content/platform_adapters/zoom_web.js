/* Zoom web client adapter (experimental). Reads the live-transcript panel when it is open
 * (it includes speaker names), otherwise the caption overlay (no speaker names). */
(function () {
  const A = window.MeetBriefAdapters;
  A.register({
    id: "zoom_web",
    name: "Zoom (web client)",
    experimental: true,
    matches: (loc) => /(^|\.)zoom\.us$/.test(loc.hostname) && /\/wc\//.test(loc.pathname),
    isInMeeting: () => !!document.querySelector("#wc-container-left, .meeting-client, #foot-bar"),
    meetingTitle: () => A.clean((document.querySelector(".meeting-info-icon__meeting-topic, .meeting-topic") || {}).innerText) || "Zoom meeting",
    meetingKey: () => {
      const m = window.location.pathname.match(/\/wc\/(?:join\/)?(\d{9,12})/);
      return m ? `zoom_web:${m[1]}` : null;
    },
    autoJoin() {
      for (const rx of [/^\s*mute\s*$/i, /stop video/i]) { const b = A.findButton(rx); if (b) b.click(); }
      const join = A.findButton(/^\s*join\s*$/i);
      if (join) { join.click(); return true; }
      return false;
    },
    captionsHint: "In Zoom, enable Captions / Show full transcript so MeetBrief can read them.",
    findCaptionRoot: () => A.query(document, [".lt-full-transcript__list", "#live-transcription-subtitle", ".live-transcription-subtitle__box"]),
    readCaptions(root) {
      const items = A.queryAll(root, [".lt-full-transcript__item"]);
      if (items.length) {
        return items.map((it) => ({
          key: A.nodeKey(it),
          speaker: A.clean((it.querySelector(".lt-full-transcript__display-name") || {}).innerText) || null,
          text: A.clean((it.querySelector(".lt-full-transcript__message") || it).innerText),
        })).filter((c) => c.text);
      }
      const lines = A.queryAll(root, [".live-transcription-subtitle__item", "span"]);
      const els = lines.length ? lines : [root];
      return els.map((el) => ({ key: A.nodeKey(el), speaker: null, text: A.clean(el.innerText) })).filter((c) => c.text);
    },
  });
})();

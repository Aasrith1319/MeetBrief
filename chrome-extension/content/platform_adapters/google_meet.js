/* Google Meet adapter (primary, tested platform).
 * Requires the user to turn on captions (CC) in Meet. Meet shows captions in a region
 * whose blocks contain the speaker's name and the (progressively updated) caption text. */
(function () {
  const A = window.MeetBriefAdapters;
  const ROOT_SELECTORS = [
    'div[role="region"][aria-label*="aption" i]',   // "Captions" (English UI)
    'div[jsname="dsyhDe"]',
    'div[jscontroller="KPn5nb"]',
    ".a4cQT",
    ".iOzk7",
  ];
  const BLOCK_SELECTORS = [".nMcdL", ".TBMuR", 'div[jsname="tgaKEf"]', ":scope > div > div", ":scope > div"];
  const NAME_SELECTORS = [".NWpY1d", ".KcIKyf", ".zs7s8d", ".jxFHg"];
  const TEXT_SELECTORS = [".ygicle", ".bh44bd", ".iTTPOb", ".VbkSUe"];

  // Meeting code from the URL. Meet uses both meet.google.com/abc-defg-hij and meet.google.com/meet/abc-defg-hij
  // (and may add ?authuser=… or a trailing path), so the code may appear anywhere in the path.
  function meetingCode() {
    const m = window.location.pathname.match(/(?:^|\/)([a-z]{3}-[a-z]{4}-[a-z]{3})(?=$|[/?#])/);
    return m ? m[1] : null;
  }

  // Text of a caption block without the buttons and icon glyphs Meet places inside the captions area
  // (e.g. "Summarise", "close", settings): those must never be mistaken for speech.
  const CONTROL_SEL = 'button, [role="button"], .google-material-icons, .material-icons-extended, .google-symbols, i';
  function spokenText(el) {
    if (!el) return "";
    let text = el.innerText || "";
    for (const c of el.querySelectorAll(CONTROL_SEL)) {
      const t = (c.innerText || c.textContent || "").trim();
      if (t) text = text.replace(t, " ");
    }
    return A.clean(text);
  }

  function leaveButton() {
    const byLabel = document.querySelector('[aria-label*="leave call" i], [data-tooltip*="leave call" i], button[jsname="CQylAd"]');
    if (byLabel) return byLabel;
    return Array.from(document.querySelectorAll("button i, button span")).find((el) => A.clean(el.textContent) === "call_end") || null;
  }

  A.register({
    id: "google_meet",
    name: "Google Meet",
    matches: (loc) => loc.hostname === "meet.google.com",
    // In a call = meeting-code URL + a visible "leave call" control. The material icon name
    // "call_end" is language-independent, so this also works in Telugu/Hindi/other Meet UIs.
    // Fallback signal that does not depend on the UI language or icon font: participant video tiles, which
    // only exist inside the call (not on the pre-join screen).
    isInMeeting: () => !!meetingCode()
      && (!!leaveButton() || !!document.querySelector("[data-participant-id], [data-requested-participant-id]")),
    hasEnded: () => {
      const t = (document.body && document.body.innerText) || "";
      return /you(?:'ve| have)? left the (?:meeting|call)|the (?:call|meeting) has ended|you were removed from the meeting/i.test(t)
        || !!document.querySelector('[data-call-ended="true"]');
    },
    /** Room key from the link: same meeting → same MeetBrief room for every member. */
    meetingKey: () => {
      const code = meetingCode();
      return code ? `google_meet:${code}` : null;
    },
    /** Early Join: on the pre-join screen turn mic + camera off and press Join. Returns true once clicked. */
    autoJoin() {
      for (const rx of [/turn off microphone/i, /turn off camera/i]) {
        const b = A.findButton(rx);
        if (b) b.click();
      }
      const join = A.findButton(/^\s*(join now|ask to join|join|switch here)\s*$/i);
      if (join) { join.click(); return true; }
      return false;
    },
    enableCaptions() {
      // Click Meet's captions toggle if captions are off (opt-in automatic mode only)
      const btn = Array.from(document.querySelectorAll("button")).find((b) => {
        const label = (b.getAttribute("aria-label") || b.getAttribute("data-tooltip") || "").toLowerCase();
        const icon = A.clean((b.querySelector("i, span.google-material-icons, span.material-icons-extended") || {}).textContent);
        return (/caption/.test(label) && b.getAttribute("aria-pressed") !== "true") || icon === "closed_caption_off";
      });
      if (btn) { btn.click(); return true; }
      return false;
    },
    meetingTitle: () => {
      const t = document.querySelector("[data-meeting-title]");
      return (t && t.getAttribute("data-meeting-title")) || document.title.replace(/^Meet\s*[-–]\s*/, "") || "Google Meet";
    },
    captionsHint: "Turn on captions in Google Meet (CC button or press c) so MeetBrief can read them.",
    findCaptionRoot: () => A.query(document, ROOT_SELECTORS),
    readCaptions(root) {
      let blocks = [];
      for (const sel of BLOCK_SELECTORS) {
        try { blocks = Array.from(root.querySelectorAll(sel)); } catch (_) { blocks = []; }
        blocks = blocks.filter((b) => !b.closest('button, [role="button"]') && spokenText(b).length > 0);
        if (blocks.length) break;
      }
      return blocks.map((block) => {
        const nameEl = A.query(block, NAME_SELECTORS);
        const textEl = A.query(block, TEXT_SELECTORS);
        let speaker = nameEl ? spokenText(nameEl) : null;
        let text = textEl ? spokenText(textEl) : null;
        if (!text) ({ speaker, text } = A.splitBlock(block, spokenText(block)));
        return { key: A.nodeKey(block), speaker: speaker || null, text: A.clean(text) };
      }).filter((c) => c.text && /[\p{L}\p{N}]/u.test(c.text));
    },
  });
})();

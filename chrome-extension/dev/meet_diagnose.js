// MeetBrief diagnostic for a live Google Meet call. Read-only: it does not click or change anything.
// Paste into the Meet tab's DevTools console (View → Developer → JavaScript Console) while captions are ON
// and someone is speaking. The result is copied to your clipboard; paste it back to the assistant.
(() => {
  const short = (el) => el && {
    tag: el.tagName.toLowerCase(), cls: String(el.className || "").slice(0, 80), role: el.getAttribute("role"),
    label: el.getAttribute("aria-label"), live: el.getAttribute("aria-live"), jsname: el.getAttribute("jsname"),
    text: (el.innerText || "").trim().slice(0, 60), kids: el.children.length,
  };
  const btns = [...document.querySelectorAll("button")];
  const cc = btns.filter((b) => /caption|subtit|cc\b/i.test((b.getAttribute("aria-label") || "") + (b.getAttribute("data-tooltip") || ""))
    || /closed_caption/.test(b.innerText));
  const leave = btns.filter((b) => /leave|end call/i.test(b.getAttribute("aria-label") || "") || /call_end/.test(b.innerText));
  const regions = [...document.querySelectorAll('[role="region"], [aria-live]')].map(short);
  // the caption area usually sits near the bottom and holds the most recently changed text
  const lowText = [...document.querySelectorAll("div")].filter((d) => {
    const r = d.getBoundingClientRect();
    return r.top > innerHeight * 0.5 && r.height < innerHeight * 0.4 && d.children.length >= 1 && (d.innerText || "").trim().length > 15;
  }).slice(-12).map((d) => ({ ...short(d), path: [d.parentElement, d.parentElement?.parentElement].map((p) => p && String(p.className).slice(0, 40)) }));
  const out = {
    url: location.pathname, lang: document.documentElement.lang, title: document.title,
    ccButtons: cc.map((b) => ({ label: b.getAttribute("aria-label"), pressed: b.getAttribute("aria-pressed"), icon: b.innerText.trim().slice(0, 30) })),
    leaveButtons: leave.map((b) => b.getAttribute("aria-label")),
    meetbriefLabel: document.getElementById("meetbrief-status")?.innerText || null,
    regions, lowText,
  };
  if (typeof copy === "function") copy(JSON.stringify(out, null, 1));  // DevTools console helper
  console.log("MeetBrief diagnostic copied to clipboard:", out);
  return "Copied — paste it to the assistant";
})();

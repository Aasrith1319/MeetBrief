/* Platform adapter registry. Each adapter converts one meeting platform's accessible
 * captions into a common {key, speaker, text} form so the rest of the pipeline is
 * platform-independent (architectural rule 5.3). Selectors are isolated here because
 * meeting UIs change often; keep adapters small and easy to update. */
(function () {
  // re-created on every injection (fresh registry), so an updated extension's adapters replace the old ones
  const adapters = [];
  let nextKey = 1;
  const keys = new WeakMap();

  window.MeetBriefAdapters = {
    register(adapter) { adapters.push(adapter); },
    detect(loc = window.location) { return adapters.find((a) => a.matches(loc)) || null; },
    all: () => adapters.slice(),
    /** Stable id for a caption DOM node across mutations. */
    nodeKey(node) {
      if (!keys.has(node)) keys.set(node, `n${nextKey++}`);
      return keys.get(node);
    },
    /** First element matching any selector. */
    query(root, selectors) {
      for (const sel of selectors) {
        try { const el = root.querySelector(sel); if (el) return el; } catch (_) { /* invalid selector on this page */ }
      }
      return null;
    },
    queryAll(root, selectors) {
      for (const sel of selectors) {
        try { const els = root.querySelectorAll(sel); if (els.length) return Array.from(els); } catch (_) { /* ignore */ }
      }
      return [];
    },
    clean(text) { return (text || "").replace(/\s+/g, " ").trim(); },
    /** First visible <button> whose text or aria-label matches. */
    findButton(rx, root = document) {
      return Array.from(root.querySelectorAll("button, [role=button]")).find((b) => {
        const labels = [b.innerText, b.getAttribute("aria-label"), b.getAttribute("data-tooltip")].filter(Boolean);
        return labels.some((l) => rx.test(l.trim())) && b.offsetParent !== null && !b.disabled;
      }) || null;
    },
    /** Heuristic split of a caption block's innerText into speaker + text. */
    splitBlock(block, cleaned) {
      let lines = (block.innerText || "").split("\n").map((s) => s.trim()).filter(Boolean);
      // keep only lines that survived control/icon removal (cleaned = block text without buttons)
      if (cleaned !== undefined) lines = lines.filter((l) => cleaned.includes(l));
      if (lines.length >= 2 && lines[0].length <= 40 && lines[0].split(" ").length <= 4 && !/[.?!,]$/.test(lines[0])) {
        return { speaker: lines[0], text: lines.slice(1).join(" ") };
      }
      return { speaker: null, text: lines.join(" ") };
    },
  };
})();

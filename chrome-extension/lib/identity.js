/* MeetBrief identity for shared rooms (used by the side panel and the service worker).
 *
 * Google sign-in uses chrome.identity.launchWebAuthFlow with the OAuth client id published by the MeetBrief
 * server (/api/health → rooms.google_client_id), so nothing in the manifest has to be edited. The server
 * verifies every token with Google. If the server runs in test mode (MEETBRIEF_ROOMS_DEV_AUTH=1) a typed
 * "Name <email>" dev identity can be used instead — for trying rooms with two Chrome profiles on one laptop.
 */
(function (g) {
  const DEFAULT_BASE = "http://127.0.0.1:8000";
  const BASE_SCOPES = ["openid", "email", "profile"];
  let infoCache = { at: 0, base: null, data: null };

  async function apiBase() {
    const { apiBase } = await chrome.storage.local.get(["apiBase"]);
    return (apiBase || DEFAULT_BASE).replace(/\/+$/, "");
  }

  async function serverInfo(force = false) {
    const base = await apiBase();
    if (!force && infoCache.data && infoCache.base === base && Date.now() - infoCache.at < 60000) return infoCache.data;
    try {
      const res = await fetch(base + "/api/health");
      const data = await res.json();
      infoCache = { at: Date.now(), base, data: data.rooms || {} };
    } catch (_) {
      return {}; // server unreachable (e.g. restarting): don't remember the failure
    }
    return infoCache.data;
  }

  function scopeKey(scopes) { return "gtoken:" + [...new Set(scopes)].sort().join(" "); }

  /** Google OAuth access token for the given scopes, or null. Interactive shows Google's consent window. */
  async function googleToken({ interactive = false, scopes = [] } = {}) {
    const info = await serverInfo();
    if (!info.google_client_id) return null;
    const all = [...BASE_SCOPES, ...scopes];
    const key = scopeKey(all);
    const cached = (await chrome.storage.session.get(key))[key];
    if (cached && cached.exp > Date.now() + 60000) return cached.token;
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.search = new URLSearchParams({
      client_id: info.google_client_id, response_type: "token", redirect_uri: chrome.identity.getRedirectURL(),
      scope: all.join(" "), include_granted_scopes: "true", prompt: interactive ? "select_account" : "none",
    }).toString();
    try {
      const redirect = await chrome.identity.launchWebAuthFlow({ url: url.toString(), interactive });
      const params = new URLSearchParams(new URL(redirect).hash.slice(1));
      const token = params.get("access_token");
      if (!token) return null;
      const exp = Date.now() + (parseInt(params.get("expires_in") || "3600", 10) * 1000);
      await chrome.storage.session.set({ [key]: { token, exp } });
      return token;
    } catch (_) {
      return null; // not signed in yet (non-interactive) or user closed the window
    }
  }

  async function devIdentity() {
    const { devName, devEmail } = await chrome.storage.local.get(["devName", "devEmail"]);
    return devName && devEmail ? `${devName} <${devEmail}>` : null;
  }

  /** Headers that identify this user to the MeetBrief server (empty if not signed in). */
  async function headers({ interactive = false } = {}) {
    const info = await serverInfo();
    if (info.google_client_id) {
      const token = await googleToken({ interactive });
      if (token) return { Authorization: `Bearer ${token}` };
    }
    // A saved test identity is always sent: the server ignores it unless it runs with MEETBRIEF_ROOMS_DEV_AUTH=1,
    // so a slow or failed /api/health check can no longer make a signed-in user look signed out.
    const dev = await devIdentity();
    if (dev) return { "X-MeetBrief-Dev-User": dev };
    return {};
  }

  async function signIn() {
    const info = await serverInfo(true);
    if (info.google_client_id) {
      const t = await googleToken({ interactive: true });
      if (!t) throw new Error("Google sign-in was cancelled or failed");
      return true;
    }
    if (info.dev_identities) throw new Error("This server uses test identities: enter a name and email below");
    throw new Error("Shared rooms are not enabled on this MeetBrief server (set MEETBRIEF_GOOGLE_CLIENT_ID)");
  }

  async function signOut() {
    const all = await chrome.storage.session.get(null);
    const keys = Object.keys(all).filter((k) => k.startsWith("gtoken:"));
    await chrome.storage.session.remove(keys);
    await chrome.storage.local.remove(["devName", "devEmail"]);
  }

  g.MMIdentity = { serverInfo, googleToken, headers, signIn, signOut, devIdentity, redirectUrl: () => chrome.identity.getRedirectURL() };
})(typeof self !== "undefined" ? self : window);
